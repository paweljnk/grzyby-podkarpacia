"""Dostęp do danych dla modelu i API. Zbiór 'real' i 'demo' mają identyczną strukturę, ale osobne tabele —
wybór zbioru jest jawny w każdym wywołaniu, więc dane demonstracyjne nie mieszają się z rzeczywistymi.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from .model.components import Observation, Stand
from .weather.aggregate import DailyWeather

Dataset = Literal["real", "demo"]

TABLES: dict[str, dict[str, str]] = {
    "real": {"wydz": "forest.wydzielenie", "teren": "terrain.wydzielenie_teren", "komorka": "weather.komorka",
             "dzien": "weather.dzien", "wk": "forest.wydzielenie_komorka", "ochrona": "protection.forma_ochrony",
             "obs": "obs.obserwacja", "zakaz": "access.zakaz"},
    "demo": {"wydz": "demo.wydzielenie", "teren": "demo.wydzielenie_teren", "komorka": "demo.komorka",
             "dzien": "demo.dzien", "wk": "demo.wydzielenie_komorka", "ochrona": "demo.forma_ochrony",
             "obs": "demo.obserwacja", "zakaz": "demo.zakaz"},
}


def T(ds: Dataset) -> dict[str, str]:
    if ds not in TABLES:
        raise ValueError(f"nieznany zbiór danych: {ds}")
    return TABLES[ds]


@dataclass
class StandRow:
    stand: Stand
    obszar_id: str | None
    adres_lesny: str | None
    lat: float
    lon: float
    odleglosc_km: float | None
    powierzchnia_ha: float
    komorka_id: str | None
    nachylenie_max: float | None
    ekspozycja: str | None
    wys_min: float | None
    wys_max: float | None
    pochodzenie: dict[str, str]
    attrs: dict
    imported_at: datetime | None
    meta: dict | None = None      # zarząd, własność, rok danych, gleba/siedlisko, pH (model), klasa danych


_STAND_SQL = """
SELECT w.id, w.gatunek_panujacy, w.udzial_gatunkow, w.wiek, w.typ_siedliskowy, w.gleba,
       t.wys_sr, t.nachylenie_sr_deg, w.obszar_id, w.adres_lesny,
       ST_Y(c.p), ST_X(c.p), {dist}, ST_Area(w.geom) / 10000.0, wk.komorka_id,
       t.nachylenie_max_deg, t.ekspozycja_klasa, t.wys_min, t.wys_max,
       w.gatunek_panujacy_pochodzenie, w.udzial_gatunkow_pochodzenie, w.wiek_pochodzenie,
       w.typ_siedliskowy_pochodzenie, w.gleba_pochodzenie, t.pochodzenie, NULL::jsonb, w.imported_at,  -- attrs (surowe pola BDL) nie są potrzebne do oceny
       w.udzial_panujacego, w.ph_model, w.ph_q05, w.ph_q95,
       w.zarzad, w.wlasnosc, w.rok_danych, w.w_wojewodztwie_frac, w.gleba_gatunek, w.uwilgotnienie_kod,
       w.siedlisko_zrodlo, w.siedlisko_rok, w.siedlisko_pokrycie, w.klasa_danych, w.nadl_kod,
       w.udzial_panujacego_pochodzenie, w.ph_pochodzenie, t.ekspozycja_sr_deg
FROM {wydz} w
CROSS JOIN LATERAL (SELECT ST_Transform(ST_PointOnSurface(w.geom), 4326) p) c
LEFT JOIN {teren} t ON t.wydzielenie_id = w.id
LEFT JOIN {wk} wk ON wk.wydzielenie_id = w.id
"""


def _row(r) -> StandRow:
    shares = r[2] if isinstance(r[2], dict) or r[2] is None else json.loads(r[2])
    # Normalizacja kodów także przy odczycie — dane zaimportowane starszym słownikiem dają ten sam wynik.
    from .etl.bdl_codes import site_type, species
    st = Stand(r[0], species(r[1]), shares, r[3], site_type(r[4]), r[5], r[6], r[7],
               udzial_panujacego=r[27], ph_model=r[28], ph_q05=r[29], ph_q95=r[30], gleba_gatunek=r[35],
               ekspozycja_deg=r[44])
    prov = dict(zip(["gatunek_panujacy", "udzial_gatunkow", "wiek", "typ_siedliskowy", "gleba", "teren"],
                    [str(x) if x else "brak" for x in r[19:25]]))
    prov["udzial_panujacego"] = str(r[42] or "brak")
    prov["ph"] = str(r[43] or "brak")
    meta = dict(zip(["zarzad", "wlasnosc", "rok_danych", "w_wojewodztwie_frac", "gleba_gatunek", "uwilgotnienie_kod",
                     "siedlisko_zrodlo", "siedlisko_rok", "siedlisko_pokrycie", "klasa_danych", "nadl_kod"], r[31:42]))
    if isinstance(meta.get("wlasnosc"), str):
        meta["wlasnosc"] = meta["wlasnosc"].strip()
    return StandRow(st, r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15], r[16], r[17], r[18], prov,
                    r[25] or {}, r[26], meta)


def stands_near(conn, ds: Dataset, lat: float, lon: float, radius_km: float, limit: int = 20000) -> list[StandRow]:
    t = T(ds)
    pt = "ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 2180)"
    sql = _STAND_SQL.format(dist=f"ST_Distance(w.geom, {pt}) / 1000.0", **t) + \
        f" WHERE ST_DWithin(w.geom, {pt}, %(r)s) ORDER BY ST_Distance(w.geom, {pt}) LIMIT %(limit)s"
    with conn.cursor() as cur:
        cur.execute(sql, {"lat": lat, "lon": lon, "r": radius_km * 1000, "limit": limit})
        return [_row(r) for r in cur.fetchall()]


def stands_in_bbox(conn, ds: Dataset, bbox: tuple[float, float, float, float], limit: int = 20000) -> list[StandRow]:
    t = T(ds)
    env = "ST_Transform(ST_MakeEnvelope(%(x0)s, %(y0)s, %(x1)s, %(y1)s, 4326), 2180)"
    sql = _STAND_SQL.format(dist="NULL::float", **t) + f" WHERE w.geom && {env} LIMIT %(limit)s"
    with conn.cursor() as cur:
        cur.execute(sql, {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3], "limit": limit})
        return [_row(r) for r in cur.fetchall()]


def coverage_geojson(conn, bbox: tuple[float, float, float, float]) -> dict:
    with conn.cursor() as cur:
        cur.execute("""SELECT ix, iy, klasa, las_ref_ha, bdl_ha, ST_AsGeoJSON(ST_Transform(geom, 4326), 5) FROM coverage.siatka
                       WHERE geom && ST_Transform(ST_MakeEnvelope(%s,%s,%s,%s,4326), 2180)""", bbox)
        feats = [{"type": "Feature", "geometry": json.loads(g),
                  "properties": {"klasa": k, "las_ref_ha": round(r or 0, 1), "bdl_ha": round(b or 0, 1)}}
                 for _, _, k, r, b, g in cur.fetchall()]
    return {"type": "FeatureCollection", "features": feats}


def stand_by_id(conn, ds: Dataset, sid: int, lat: float | None = None, lon: float | None = None) -> StandRow | None:
    t = T(ds)
    if lat is not None and lon is not None:
        dist = "ST_Distance(w.geom, ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 2180)) / 1000.0"
    else:
        dist = "NULL::float"
    with conn.cursor() as cur:
        cur.execute(_STAND_SQL.format(dist=dist, **t) + " WHERE w.id = %(id)s", {"id": sid, "lat": lat, "lon": lon})
        r = cur.fetchone()
    return _row(r) if r else None


def stand_geojson(conn, ds: Dataset, ids: list[int], simplify_m: float = 0) -> dict[int, dict]:
    """Geometrie w EPSG:4326. simplify_m > 0 upraszcza do mapy (poniżej dokładności źródła)."""
    if not ids:
        return {}
    g = f"ST_SimplifyPreserveTopology(geom, {float(simplify_m)})" if simplify_m else "geom"
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, ST_AsGeoJSON(ST_Transform({g}, 4326), 5) FROM {T(ds)['wydz']} WHERE id = ANY(%s)", (ids,))
        return {i: json.loads(x) for i, x in cur.fetchall()}


def protection_bulk(conn, ds: Dataset, ids: list[int]) -> dict[int, list[dict]]:
    t = T(ds)
    out: dict[int, list[dict]] = {i: [] for i in ids}
    with conn.cursor() as cur:
        cur.execute(f"""SELECT w.id, o.rodzaj, o.nazwa, o.kod, o.source_id, o.warstwa FROM {t['ochrona']} o
                        JOIN {t['wydz']} w ON ST_Intersects(o.geom, w.geom) WHERE w.id = ANY(%s)""", (ids,))
        for r in cur.fetchall():
            out[r[0]].append(dict(zip(["rodzaj", "nazwa", "kod", "source_id", "warstwa"], r[1:])))
    return out


def bans_bulk(conn, ds: Dataset, ids: list[int], day: date) -> dict[int, list[dict]]:
    t = T(ds)
    out: dict[int, list[dict]] = {i: [] for i in ids}
    with conn.cursor() as cur:
        cur.execute(f"""SELECT w.id, z.rodzaj, z.opis, z.od, z.do_dnia, z.source_id FROM {t['zakaz']} z
                        JOIN {t['wydz']} w ON ST_Intersects(z.geom, w.geom)
                        WHERE w.id = ANY(%s) AND (z.od IS NULL OR z.od <= %s) AND (z.do_dnia IS NULL OR z.do_dnia >= %s)""",
                    (ids, day, day))
        for r in cur.fetchall():
            out[r[0]].append(dict(zip(["rodzaj", "opis", "od", "do", "source_id"], r[1:])))
    return out


def observations_region(conn, ds: Dataset, species: str, lat: float, lon: float, day: date, radius_km: float,
                        lookback_days: int = 60) -> list[tuple[float, float, Observation]]:
    """Obserwacje w regionie zapytania (promień + zasięg wpływu) — odległość do miejsca liczona potem w Pythonie."""
    t = T(ds)
    end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT ST_X(ST_Transform(geom,4326)), ST_Y(ST_Transform(geom,4326)), czas_utc, znaleziono, jakosc, czas_szukania_min
            FROM {t['obs']} WHERE species_id=%s AND czas_utc < %s AND czas_utc >= %s
              AND ST_DWithin(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),2180), %s)""",
                    (species, end, end - timedelta(days=lookback_days), lon, lat, radius_km * 1000))
        return [(r[0], r[1], Observation(max(0, (end - r[2]).days), 0.0, r[3], r[4], r[5])) for r in cur.fetchall()]


def weather_series(conn, ds: Dataset, komorka_id: str, start: date, end: date) -> tuple[list[DailyWeather], dict]:
    """Ciąg dobowy. Dla tej samej doby: najpierw wiersze z kompletnym opadem, potem kolejność stacja >
    reanaliza > analiza > prognoza (reanaliza z końca okresu bywa niepełna — wtedy wygrywa analiza)."""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT ON (data_lokalna) data_lokalna, typ, godzin, opad_mm, temp_min_c, temp_sr_c, temp_max_c,
                   wilg_powietrza_pct, wilg_gleby_m3m3, temp_gleby_c, et0_mm, pobrano_utc, model, rozdzielczosc_km
            FROM {T(ds)['dzien']} WHERE komorka_id=%s AND data_lokalna BETWEEN %s AND %s
            ORDER BY data_lokalna, (opad_mm IS NULL), CASE typ WHEN 'stacja' THEN 0 WHEN 'reanaliza' THEN 1 WHEN 'analiza' THEN 2 ELSE 3 END""",
                    (komorka_id, start, end))
        rows = cur.fetchall()
    days = [DailyWeather(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]) for r in rows]
    meta = {"pobrano_utc": max((r[11] for r in rows), default=None),
            "modele": sorted({r[12] for r in rows if r[12]}),
            "rozdzielczosc_km": max((r[13] for r in rows if r[13]), default=None),
            "komorka_id": komorka_id}
    return days, meta


def protection_for(conn, ds: Dataset, sid: int) -> list[dict]:
    t = T(ds)
    with conn.cursor() as cur:
        cur.execute(f"""SELECT o.rodzaj, o.nazwa, o.kod, o.source_id, o.warstwa FROM {t['ochrona']} o
                        JOIN {t['wydz']} w ON ST_Intersects(o.geom, w.geom) WHERE w.id=%s""", (sid,))
        return [dict(zip(["rodzaj", "nazwa", "kod", "source_id", "warstwa"], r)) for r in cur.fetchall()]


def bans_for(conn, ds: Dataset, sid: int, day: date) -> list[dict]:
    t = T(ds)
    with conn.cursor() as cur:
        cur.execute(f"""SELECT z.rodzaj, z.opis, z.od, z.do_dnia, z.source_id FROM {t['zakaz']} z
                        JOIN {t['wydz']} w ON ST_Intersects(z.geom, w.geom)
                        WHERE w.id=%s AND (z.od IS NULL OR z.od <= %s) AND (z.do_dnia IS NULL OR z.do_dnia >= %s)""",
                    (sid, day, day))
        return [dict(zip(["rodzaj", "opis", "od", "do", "source_id"], r)) for r in cur.fetchall()]


def ban_source_count(conn, ds: Dataset) -> int:
    """Ile wierszy ma tabela zakazów — 0 oznacza, że statusu zakazów nie da się sprawdzić."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {T(ds)['zakaz']}")
        return cur.fetchone()[0]


def observations_near(conn, ds: Dataset, species: str, lat: float, lon: float, day: date,
                      radius_km: float, lookback_days: int = 60) -> list[Observation]:
    t = T(ds)
    end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT czas_utc, ST_Distance(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),2180))/1000.0,
                   znaleziono, jakosc, czas_szukania_min
            FROM {t['obs']} WHERE species_id=%s AND czas_utc < %s AND czas_utc >= %s
              AND ST_DWithin(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),2180), %s)""",
                    (lon, lat, species, end, end - timedelta(days=lookback_days), lon, lat, radius_km * 1000))
        return [Observation(max(0, (end - r[0]).days), r[1], r[2], r[3], r[4]) for r in cur.fetchall()]


def dataset_info(conn, ds: Dataset) -> dict:
    t = T(ds)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*), max(imported_at) FROM {t['wydz']}")
        n, imp = cur.fetchone()
        cur.execute(f"SELECT min(data_lokalna), max(data_lokalna), max(pobrano_utc) FROM {t['dzien']}")
        dmin, dmax, wp = cur.fetchone()
        meta = {}
        if ds == "demo":
            cur.execute("SELECT klucz, wartosc FROM demo.metadane")
            meta = dict(cur.fetchall())
    return {"zbior": ds, "wydzielen": n, "import_drzewostanow_utc": imp, "pogoda_od": dmin, "pogoda_do": dmax,
            "pogoda_pobrano_utc": wp, "metadane": meta}
