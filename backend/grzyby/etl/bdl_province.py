"""Import BDL dla całego województwa (ArcGIS REST usług BDL; licencja CC BY 4.0 wg dane.gov.pl, zbiór 629).

Kolejność: nadleśnictwa ∩ województwo → wydzielenia LP (jednostka = nadleśnictwo) → wydzielenia poza LP
(jednostka = kafel 0,25°) → siedliska leśne (kafel) → przypisanie gleby/uwilgotnienia do wydzieleń →
zakazy wstępu. Każdy obiekt zachowujemy, jeśli PRZECINA granicę województwa; zapisujemy udział jego
powierzchni w województwie (w_wojewodztwie_frac).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from pyproj import Transformer
from shapely import wkb
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from shapely.prepared import prep

from ..config import load_yaml
from ..db import connect, import_run
from .arcgis import envelope_params, esri_to_shapely, fix_geometry, query_pages, read_stage, stage_unit, tiles
from .bdl_codes import site_type, species
from .http import HttpClient

log = logging.getLogger(__name__)
SRC = "bdl_rest"
TO4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform


def _s(v):
    return v.strip() if isinstance(v, str) else v


def part_share(code) -> float | None:
    """part_cd → udział w ułamku. Kody liczbowe 1–10 = dziesiąte części (słownik f_part_dic w paczce BDL);
    kody opisowe (np. PJD, MJS — pojedynczo/miejscami) nie mają wartości liczbowej → None."""
    c = _s(code)
    if c and c.isdigit() and 1 <= int(c) <= 10:
        return int(c) / 10
    return None


def province(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT ST_AsBinary(ST_Union(geom)) FROM ref.wojewodztwo")
        g = cur.fetchone()[0]
    if g is None:
        raise RuntimeError("Brak granicy województwa — uruchom najpierw import PRG")
    return wkb.loads(bytes(g))


def import_nadlesnictwa(conn, client, cfg, prov) -> list[dict]:
    b = cfg["bdl_rest"]
    bounds = shp_transform(TO4326, prov).bounds
    feats = list(query_pages(client, b["usluga_drzewostanow"], b["warstwa_nadlesnictw"],
                             {**envelope_params(bounds), "where": "1=1"}))
    pp = prep(prov)
    out = []
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ref.nadlesnictwo")
        for f in feats:
            a = f["attributes"]
            g = esri_to_shapely(f.get("geometry") or {})
            if g is None:
                continue
            g, _ = fix_geometry(g)
            if g is None or not pp.intersects(g):
                continue
            inside = g.intersection(prov).area / 1e4
            if inside < cfg["bdl_rest"]["min_ha_w_wojewodztwie"]:
                continue
            kod = f"{_s(a['region_cd'])}-{_s(a['inspectorate_cd'])}"
            cur.execute("""INSERT INTO ref.nadlesnictwo (kod, nazwa, rdlp_kod, powierzchnia_ha, w_wojewodztwie_ha, geom)
                           VALUES (%s,%s,%s,%s,%s, ST_Multi(ST_GeomFromWKB(%s,2180)))
                           ON CONFLICT (kod) DO UPDATE SET nazwa=EXCLUDED.nazwa, w_wojewodztwie_ha=EXCLUDED.w_wojewodztwie_ha,
                             powierzchnia_ha=EXCLUDED.powierzchnia_ha, geom=EXCLUDED.geom""",
                        (kod, _s(a["inspectorate_name"]), _s(a["region_cd"]), g.area / 1e4, inside, wkb.dumps(g)))
            out.append({"kod": kod, "nazwa": _s(a["inspectorate_name"]), "w_woj_ha": inside,
                        "bounds": shp_transform(TO4326, g).bounds})
    conn.commit()
    return out


def _stand_rows(path, prov_prep, prov, zarzad: str, stats: dict):
    for f in read_stage(path):
        a = f["attributes"]
        g = esri_to_shapely(f.get("geometry") or {})
        if g is None:
            stats["bez_geometrii"] += 1
            continue
        g, fixed = fix_geometry(g)
        if g is None or g.is_empty:
            stats["bez_geometrii"] += 1
            continue
        stats["naprawione_geometrie"] += int(fixed)
        if not prov_prep.intersects(g):
            stats["poza_wojewodztwem"] += 1
            continue
        frac = 1.0 if prov_prep.contains(g) else g.intersection(prov).area / g.area
        yield a, g, frac


def _insert_stand(cur, a: dict, g, frac: float, zarzad: str, run_id: int, ext: str):
    sp = species(_s(a.get("species_cd_d")))
    share = part_share(a.get("part_cd"))
    tsl = site_type(_s(a.get("site_type_cd")))
    age = a.get("species_age")
    adr = _s(a.get("adress_forest"))
    nadl = adr[:5] if zarzad == "LP" and adr else None
    attrs = {k: _s(v) for k, v in a.items() if not k.startswith("st_")}
    cur.execute(
        """INSERT INTO forest.wydzielenie (source_id, external_id, obszar_id, adres_lesny, gatunek_panujacy,
             gatunek_panujacy_pochodzenie, wiek, wiek_pochodzenie, typ_siedliskowy, typ_siedliskowy_pochodzenie,
             udzial_panujacego, udzial_panujacego_pochodzenie, zarzad, wlasnosc, nadl_kod, rok_danych,
             w_wojewodztwie_frac, attrs, geom, import_id)
           VALUES (%s,%s,'podkarpackie',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_Multi(ST_GeomFromWKB(%s,2180)), %s)
           ON CONFLICT (source_id, external_id) DO NOTHING""",
        (SRC, ext, adr, sp, "opis_taksacyjny" if sp else "brak", age, "opis_taksacyjny" if age is not None else "brak",
         tsl, "opis_taksacyjny" if tsl else "brak", share, "opis_taksacyjny" if share is not None else "brak",
         zarzad, _s(a.get("owner_cat_name")), nadl, a.get("a_year"), round(frac, 4),
         json.dumps(attrs, ensure_ascii=False, default=str), wkb.dumps(g), run_id))
    return cur.rowcount


def import_province() -> dict:
    cfg = load_yaml("zasieg.yaml")
    b = cfg["bdl_rest"]
    days = float(cfg["odswiezanie_dni"])
    conn = connect()
    prov = province(conn)
    pp = prep(prov)
    report: dict = {"nadlesnictwa": [], "lp": {}, "poza_lp": {}, "siedliska": {}}
    # przebieg próbny: GRZYBY_LIMIT_UNITS=N ogranicza liczbę nadleśnictw i kafli (test całego potoku)
    limit = int(os.environ.get("GRZYBY_LIMIT_UNITS", "0")) or None
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO ref.obszar_pilotazowy (id, nazwa, typ_terenu, geom_origin, geom)
                       SELECT 'podkarpackie', 'Województwo podkarpackie', 'mieszany', 'prg', ST_Multi(ST_Union(geom))
                       FROM ref.wojewodztwo
                       ON CONFLICT (id) DO UPDATE SET geom=EXCLUDED.geom, geom_origin='prg'""")
    conn.commit()
    with HttpClient(min_interval_s=0.5, timeout_s=300) as client:
        # 1. nadleśnictwa
        with import_run(conn, SRC, "ref.nadlesnictwo", "podkarpackie") as run:
            nadl = import_nadlesnictwa(conn, client, cfg, prov)
            run.records = len(nadl)
        report["nadlesnictwa"] = [{"kod": n["kod"], "nazwa": n["nazwa"], "ha_w_wojewodztwie": round(n["w_woj_ha"])} for n in nadl]

        # 2. wydzielenia LP — jednostka: nadleśnictwo (adres leśny zaczyna się od RR-NN)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM forest.wydzielenie WHERE source_id IN ('bdl_ogcapi', %s)", (SRC,))
        conn.commit()
        stats = {"pobrane": 0, "z_cache": 0, "zapisane": 0, "duplikaty": 0, "naprawione_geometrie": 0,
                 "poza_wojewodztwem": 0, "bez_geometrii": 0}
        with import_run(conn, SRC, "forest.wydzielenie", "LP") as run:
            for n in nadl[:limit]:
                where = f"adress_forest LIKE '{n['kod']}-%' AND {b['filtr_drzewostanow']}"
                path, cnt, cached = stage_unit(client, "lp", n["kod"], b["usluga_drzewostanow"], b["warstwa_wydzielen_lp"],
                                               {**envelope_params(n["bounds"]), "where": where}, days)
                stats["pobrane"] += cnt
                stats["z_cache"] += int(cached)
                with conn.cursor() as cur:
                    for a, g, frac in _stand_rows(path, pp, prov, "LP", stats):
                        ok = _insert_stand(cur, a, g, frac, "LP", run.id, f"LP:{a.get('arodes_int_num')}")
                        stats["zapisane"] += ok
                        stats["duplikaty"] += 1 - ok
                conn.commit()
                log.info("LP %s %s: %d obiektów%s", n["kod"], n["nazwa"], cnt, " (cache)" if cached else "")
            run.records = stats["zapisane"]
        report["lp"] = stats

        # 3. wydzielenia poza LP wg PUL — jednostka: kafel
        stats2 = {k: 0 for k in stats}
        bounds = shp_transform(TO4326, prov).bounds
        with import_run(conn, SRC, "forest.wydzielenie", "poza_LP") as run:
            for unit, tb in _limited_tiles(bounds, b["kafel_stopnie"], nadl, limit):
                path, cnt, cached = stage_unit(client, "poza_lp", unit, b["usluga_drzewostanow"], b["warstwa_wydzielen_poza_lp"],
                                               {**envelope_params(tb), "where": b["filtr_drzewostanow"]}, days)
                stats2["pobrane"] += cnt
                stats2["z_cache"] += int(cached)
                with conn.cursor() as cur:
                    for a, g, frac in _stand_rows(path, pp, prov, "poza_LP", stats2):
                        # obiekt na granicy kafli przychodzi dwa razy — ON CONFLICT pomija duplikat
                        ok = _insert_stand(cur, a, g, frac, "poza_LP", run.id, f"PUL:{a.get('subarea_id')}")
                        stats2["zapisane"] += ok
                        stats2["duplikaty"] += 1 - ok
                conn.commit()
            run.records = stats2["zapisane"]
        report["poza_lp"] = stats2

        # 4. siedliska leśne (gleba, uwilgotnienie) — jednostka: kafel
        stats3 = {"pobrane": 0, "z_cache": 0, "zapisane": 0, "duplikaty": 0, "naprawione_geometrie": 0,
                  "poza_wojewodztwem": 0, "bez_geometrii": 0}
        with import_run(conn, SRC, "forest.siedlisko", "podkarpackie") as run:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE forest.siedlisko")
            for unit, tb in _limited_tiles(bounds, b["kafel_stopnie"], nadl, limit):
                path, cnt, cached = stage_unit(client, "siedliska", unit, b["usluga_siedlisk"], b["warstwa_siedlisk"],
                                               {**envelope_params(tb), "where": "valid = 'T'"}, days)
                stats3["pobrane"] += cnt
                stats3["z_cache"] += int(cached)
                with conn.cursor() as cur:
                    for a, g, frac in _stand_rows(path, pp, prov, "", stats3):
                        cur.execute("""INSERT INTO forest.siedlisko VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                         ST_Multi(ST_GeomFromWKB(%s,2180))) ON CONFLICT (id) DO NOTHING""",
                                    (a["site_type_id"], _s(a.get("site_type_cd")), _s(a.get("soil_subtype_cd")),
                                     _s(a.get("soil_species")), _s(a.get("moisture_cd")), _s(a.get("degradation_cd")),
                                     _s(a.get("geol_depos")), _s(a.get("data_source")), a.get("a_year"), a.get("valid_year"),
                                     wkb.dumps(g)))
                        stats3["zapisane"] += cur.rowcount
                        stats3["duplikaty"] += 1 - cur.rowcount
                conn.commit()
            run.records = stats3["zapisane"]
        report["siedliska"] = stats3
        assign_habitat_soil(conn)

        # 5. zakazy wstępu (aktualne i przyszłe), tylko przecinające województwo
        report["zakazy"] = import_bans(conn, client, cfg, prov)
    finalize_data_class(conn)
    conn.close()
    return report


def _limited_tiles(bounds, step, nadl, limit):
    all_t = tiles(bounds, step)
    if not limit:
        return all_t
    # w przebiegu próbnym: kafle przecinające wybrane nadleśnictwa
    sel = []
    for n in nadl[:limit]:
        x0, y0, x1, y1 = n["bounds"]
        sel += [t for t in all_t if t[1][0] < x1 and t[1][2] > x0 and t[1][1] < y1 and t[1][3] > y0 and t not in sel]
    return sel[:limit * 2]


def assign_habitat_soil(conn) -> None:
    """Gleba i uwilgotnienie z siedliska o największym pokryciu wydzielenia (informacja źródłowa BDL)."""
    with import_run(conn, SRC, "forest.wydzielenie.gleba", "podkarpackie") as run, conn.cursor() as cur:
        cur.execute("""
            WITH best AS (
              SELECT DISTINCT ON (w.id) w.id, s.soil_subtype_cd, s.soil_species, s.moisture_cd, s.data_source, s.valid_year,
                     ST_Area(ST_Intersection(w.geom, s.geom)) / NULLIF(ST_Area(w.geom), 0) AS frac
              FROM forest.wydzielenie w JOIN forest.siedlisko s ON ST_Intersects(w.geom, s.geom)
              ORDER BY w.id, ST_Area(ST_Intersection(w.geom, s.geom)) DESC)
            UPDATE forest.wydzielenie w SET
              gleba = NULLIF(b.soil_subtype_cd, ''), gleba_pochodzenie = CASE WHEN NULLIF(b.soil_subtype_cd, '') IS NULL
                                                                   THEN 'brak' ELSE 'opis_taksacyjny' END::meta.pochodzenie,
              gleba_gatunek = NULLIF(b.soil_species, ''), uwilgotnienie_kod = NULLIF(NULLIF(b.moisture_cd, ''), '-'),
              siedlisko_zrodlo = b.data_source, siedlisko_rok = b.valid_year, siedlisko_pokrycie = round(b.frac::numeric, 3)
            FROM best b WHERE b.id = w.id AND b.frac >= 0.5""")
        run.records = cur.rowcount
    conn.commit()


def import_bans(conn, client, cfg, prov) -> dict:
    b = cfg["bdl_rest"]
    pp = prep(prov)
    n_all = n_in = 0
    with import_run(conn, SRC, "access.zakaz", "podkarpackie") as run, conn.cursor() as cur:
        cur.execute("DELETE FROM access.zakaz WHERE source_id=%s", (SRC,))
        for f in query_pages(client, b["usluga_zakazow"], b["warstwa_zakazow"], {"where": "1=1"}):
            n_all += 1
            a = f["attributes"]
            g = esri_to_shapely(f.get("geometry") or {})
            if g is None:
                continue
            g, _ = fix_geometry(g)
            if g is None or not pp.intersects(g):
                continue
            ms = lambda v: datetime.fromtimestamp(v / 1000, tz=timezone.utc).date() if v else None
            cur.execute("""INSERT INTO access.zakaz (source_id, rodzaj, od, do_dnia, opis, attrs, geom, import_id)
                           VALUES (%s,%s,%s,%s,%s,%s, ST_Multi(ST_GeomFromWKB(%s,2180)), %s)""",
                        (SRC, _s(a.get("kod")) or "zakaz wstępu", ms(a.get("data")), ms(a.get("data_koncowa")),
                         _s(a.get("opis")), json.dumps({k: _s(v) for k, v in a.items()}, ensure_ascii=False, default=str),
                         wkb.dumps(g), run.id))
            n_in += 1
        run.records = n_in
    conn.commit()
    return {"w_kraju": n_all, "w_wojewodztwie": n_in}


def finalize_data_class(conn) -> None:
    """Klasa danych wydzielenia: 'pelniejsze' = TSL + gatunek panujący z udziałem + gleba ze źródła;
    w przeciwnym razie 'czesciowe'. (Pełny skład gatunkowy nie jest dostępny w usługach — zob. docs.)"""
    with conn.cursor() as cur:
        cur.execute("""UPDATE forest.wydzielenie SET klasa_danych = CASE
                         WHEN typ_siedliskowy IS NOT NULL AND gatunek_panujacy IS NOT NULL AND udzial_panujacego IS NOT NULL
                              AND gleba IS NOT NULL THEN 'pelniejsze' ELSE 'czesciowe' END""")
    conn.commit()


def quality_report(conn) -> dict:
    """Kompletność, duplikaty i poprawność geometrii po imporcie."""
    q = {}
    with conn.cursor() as cur:
        cur.execute("""SELECT zarzad, count(*), round(sum(ST_Area(geom) * w_wojewodztwie_frac) / 1e4),
                              count(*) FILTER (WHERE NOT ST_IsValid(geom)),
                              count(*) FILTER (WHERE gatunek_panujacy IS NULL), count(*) FILTER (WHERE udzial_panujacego IS NULL),
                              count(*) FILTER (WHERE typ_siedliskowy IS NULL), count(*) FILTER (WHERE wiek IS NULL),
                              count(*) FILTER (WHERE gleba IS NULL), count(*) FILTER (WHERE uwilgotnienie_kod IS NULL),
                              count(*) FILTER (WHERE ph_model IS NULL), count(*) FILTER (WHERE klasa_danych='pelniejsze')
                       FROM forest.wydzielenie GROUP BY zarzad""")
        for r in cur.fetchall():
            q[r[0]] = dict(zip(["wydzielen", "ha_w_wojewodztwie", "niepoprawne_geometrie", "brak_gatunku", "brak_udzialu",
                                "brak_tsl", "brak_wieku", "brak_gleby", "brak_uwilgotnienia", "brak_ph_model",
                                "klasa_pelniejsze"], r[1:]))
        cur.execute("""SELECT count(*) FROM (SELECT adres_lesny FROM forest.wydzielenie WHERE zarzad='LP'
                       GROUP BY adres_lesny HAVING count(*) > 1) d""")
        q["duplikaty_adresu_LP"] = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM (SELECT a.id FROM forest.wydzielenie a JOIN forest.wydzielenie b
                       ON a.id < b.id AND a.geom && b.geom AND ST_Equals(a.geom, b.geom) LIMIT 10000) d""")
        q["duplikaty_geometrii"] = cur.fetchone()[0]
    return q
