"""Importy wektorowe: BDL (OGC API Features), GDOŚ CRFOP i PRG (WFS).

Nazwy kolekcji/warstw i pól pochodzą wyłącznie z config/bdl_mapping.yaml, uzupełnianego po `make probe`.
Gdy mapowanie jest puste, import kończy się statusem 'skipped' z instrukcją — nie zgadujemy schematu.
"""
from __future__ import annotations

import io
import json
import logging
from typing import Any, Iterator

import geopandas as gpd
from shapely import wkb

from ..config import CRS_STORAGE, bdl_mapping, pilot_config
from ..db import connect, import_run
from ..sources import load_sources
from .http import HttpClient, SourceUnavailable
from .probe import parse_wfs_capabilities

log = logging.getLogger(__name__)
PAGE_LIMIT = 1000


class MappingMissing(SourceUnavailable):
    """Brak mapowania warstw/pól — wymagane po odczytaniu rzeczywistego schematu."""


def ogcapi_items(client: HttpClient, base: str, collection: str, bbox: list[float]) -> Iterator[dict]:
    """Wszystkie obiekty kolekcji w bbox (CRS84), ze stronicowaniem przez link rel=next."""
    url = f"{base.rstrip('/')}/collections/{collection}/items"
    params: dict[str, Any] | None = {"f": "json", "limit": PAGE_LIMIT, "bbox": ",".join(map(str, bbox))}
    while url:
        page = client.get(url, params=params).json()
        yield from page.get("features", [])
        nxt = [l["href"] for l in page.get("links", []) if l.get("rel") == "next"]
        url, params = (nxt[0], None) if nxt else (None, None)


def wfs_features(client: HttpClient, url: str, type_name: str, bbox: list[float]) -> gpd.GeoDataFrame:
    caps = parse_wfs_capabilities(client.get(url, params={"service": "WFS", "request": "GetCapabilities"}).content)
    if type_name not in {ft.get("Name") for ft in caps["typy_obiektow"]}:
        raise MappingMissing(f"Warstwa {type_name!r} nie występuje w GetCapabilities {url}")
    fmt = next((f for f in caps["formaty_wyjsciowe"] if "json" in f.lower()), None)
    params = {"service": "WFS", "version": caps["wersja"] or "2.0.0", "request": "GetFeature",
              "typeName": type_name, "bbox": ",".join(map(str, bbox)) + ",urn:ogc:def:crs:OGC:1.3:CRS84"}
    if fmt:
        params["outputFormat"] = fmt
    r = client.get(url, params=params)
    return gpd.read_file(io.BytesIO(r.content))


def _to_storage(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise ValueError("Źródło nie podało układu współrzędnych — nie przyjmujemy założeń")
    return gdf.to_crs(CRS_STORAGE)


def _prop(props: dict, field: str | None):
    return props.get(field) if field else None


def _nadlesnictwa(client: HttpClient, base: str, m: dict, bbox: list[float]) -> list[dict]:
    return list(ogcapi_items(client, base, m["kolekcja_nadlesnictw"], bbox))


def _match_inspectorate(feats: list[dict], m: dict, needle: str) -> dict | None:
    from .bdl_codes import search_key
    hits = [f for f in feats if needle in search_key(str((f.get("properties") or {}).get(m["pole_nazwy_nadlesnictwa"], "")))]
    return hits[0] if len(hits) == 1 else None


def map_bdl_feature(p: dict, m: dict) -> dict:
    """Atrybuty znormalizowane z obiektu BDL wg config/bdl_mapping.yaml (czysta funkcja, testowana)."""
    from .bdl_codes import site_type, species
    f = m["pola"]
    raw = lambda k: p.get(f[k]) if f.get(k) else None
    vals = {
        "external_id": str(raw("external_id")) if raw("external_id") is not None else None,
        "adres_lesny": raw("adres_lesny"),
        "gatunek_panujacy": species(raw("gatunek_panujacy")),
        "udzial_gatunkow": raw("udzial_gatunkow"),
        "wiek": raw("wiek"),
        "typ_siedliskowy": site_type(raw("typ_siedliskowy")),
        "gleba": raw("gleba"),
    }
    vals["pochodzenie"] = {k: ("opis_taksacyjny" if vals[k] is not None else "brak")
                           for k in ("gatunek_panujacy", "udzial_gatunkow", "wiek", "typ_siedliskowy", "gleba")}
    return vals


def import_bdl() -> None:
    from shapely.geometry import shape
    from .bdl_codes import search_key
    m = bdl_mapping()["bdl_ogcapi"]
    base = load_sources()["bdl_ogcapi"]["url"]
    conn = connect()
    with HttpClient(min_interval_s=0.5, timeout_s=120) as client:
        for area in pilot_config()["obszary"]:
            try:
                with import_run(conn, "bdl_ogcapi", "forest.wydzielenie", area["id"]) as run:
                    if not m.get("kolekcje_wydzielen") or not m["pola"].get("external_id"):
                        raise MappingMissing("config/bdl_mapping.yaml: brak kolekcje_wydzielen / pola.external_id")
                    bbox = area["bbox_roboczy_wgs84"]
                    prefix = None
                    insp = None
                    if area.get("nadlesnictwo_szukaj") and m.get("kolekcja_nadlesnictw"):
                        insp = _match_inspectorate(_nadlesnictwa(client, base, m, bbox), m,
                                                   search_key(area["nadlesnictwo_szukaj"]))
                    if insp:
                        ip = insp["properties"]
                        prefix = f"{ip[m['pole_kodu_rdlp']]}-{ip[m['pole_kodu_nadlesnictwa']]}-"
                        g = shape(insp["geometry"])
                        bbox = list(g.bounds)
                        g2180 = _to_storage(gpd.GeoDataFrame(geometry=[g], crs="OGC:CRS84")).geometry.iloc[0]
                        with conn.cursor() as cur:
                            cur.execute(
                                """INSERT INTO ref.obszar_pilotazowy (id, nazwa, typ_terenu, geom_origin, geom, import_id)
                                   VALUES (%s,%s,%s,'bdl', ST_Multi(ST_GeomFromWKB(%s,2180)), %s)
                                   ON CONFLICT (id) DO UPDATE SET nazwa=EXCLUDED.nazwa, geom_origin='bdl',
                                     geom=EXCLUDED.geom, import_id=EXCLUDED.import_id""",
                                (area["id"], f"Nadleśnictwo {ip[m['pole_nazwy_nadlesnictwa']]}", area["typ_terenu"],
                                 wkb.dumps(g2180), run.id))
                    else:
                        log.warning("%s: nie znaleziono jednoznacznie nadleśnictwa w BDL — użyty prostokąt roboczy", area["id"])
                    n = 0
                    for coll in m["kolekcje_wydzielen"]:
                        url = f"{base.rstrip('/')}/collections/{coll}/items"
                        params = {"f": "json", "limit": PAGE_LIMIT, "bbox": ",".join(map(str, bbox)), **m.get("filtr", {})}
                        with conn.cursor() as cur:
                            while url:
                                page = client.get(url, params=params).json()
                                for feat in page.get("features", []):
                                    p = feat.get("properties") or {}
                                    v = map_bdl_feature(p, m)
                                    if prefix and not str(v["adres_lesny"] or "").startswith(prefix):
                                        continue
                                    if not v["external_id"] or not feat.get("geometry"):
                                        continue
                                    geom = _to_storage(gpd.GeoDataFrame(geometry=[shape(feat["geometry"])],
                                                                        crs="OGC:CRS84")).geometry.iloc[0]
                                    pr = v["pochodzenie"]
                                    cur.execute(
                                        """INSERT INTO forest.wydzielenie (source_id, external_id, obszar_id, adres_lesny,
                                             gatunek_panujacy, gatunek_panujacy_pochodzenie, udzial_gatunkow, udzial_gatunkow_pochodzenie,
                                             wiek, wiek_pochodzenie, typ_siedliskowy, typ_siedliskowy_pochodzenie,
                                             gleba, gleba_pochodzenie, attrs, geom, import_id)
                                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_Multi(ST_GeomFromWKB(%s,2180)),%s)
                                           ON CONFLICT (source_id, external_id) DO UPDATE SET obszar_id=EXCLUDED.obszar_id,
                                             adres_lesny=EXCLUDED.adres_lesny, gatunek_panujacy=EXCLUDED.gatunek_panujacy,
                                             gatunek_panujacy_pochodzenie=EXCLUDED.gatunek_panujacy_pochodzenie,
                                             wiek=EXCLUDED.wiek, wiek_pochodzenie=EXCLUDED.wiek_pochodzenie,
                                             typ_siedliskowy=EXCLUDED.typ_siedliskowy,
                                             typ_siedliskowy_pochodzenie=EXCLUDED.typ_siedliskowy_pochodzenie,
                                             attrs=EXCLUDED.attrs, geom=EXCLUDED.geom, import_id=EXCLUDED.import_id,
                                             imported_at=now()""",
                                        ("bdl_ogcapi", v["external_id"], area["id"], v["adres_lesny"],
                                         v["gatunek_panujacy"], pr["gatunek_panujacy"],
                                         json.dumps(v["udzial_gatunkow"]) if v["udzial_gatunkow"] is not None else None,
                                         pr["udzial_gatunkow"], v["wiek"], pr["wiek"], v["typ_siedliskowy"],
                                         pr["typ_siedliskowy"], v["gleba"], pr["gleba"],
                                         json.dumps({**p, "_kolekcja": coll}, default=str), wkb.dumps(geom), run.id))
                                    n += 1
                                nxt = [l["href"] for l in page.get("links", []) if l.get("rel") == "next"]
                                url, params = (nxt[0], None) if nxt else (None, None)
                        conn.commit()
                    run.records = n
                    if not insp:
                        run.set_status("partial", "nadleśnictwo nieodnalezione — zakres z prostokąta roboczego")
                    conn.commit()
                    log.info("BDL %s: %d wydzieleń (prefiks %s)", area["id"], n, prefix)
            except SourceUnavailable as e:
                log.warning("BDL %s pominięte: %s", area["id"], e)
    conn.close()


def import_gdos() -> None:
    m = bdl_mapping()["gdos_crfop"]
    url = load_sources()["gdos_crfop"]["url"]
    bbox = _union_bbox()
    conn = connect()
    with HttpClient() as client:
        try:
            with import_run(conn, "gdos_crfop", "protection.forma_ochrony", "pilotaz", {"warstwy": m["warstwy"]}) as run:
                if not m["warstwy"]:
                    raise MappingMissing("config/bdl_mapping.yaml: gdos_crfop.warstwy puste — uzupełnij po `make probe`")
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM protection.forma_ochrony WHERE source_id='gdos_crfop'")
                    for layer in m["warstwy"]:
                        gdf = _to_storage(wfs_features(client, url, layer, bbox))
                        for _, row in gdf.iterrows():
                            props = {k: v for k, v in row.items() if k != "geometry"}
                            cur.execute(
                                """INSERT INTO protection.forma_ochrony (source_id, warstwa, rodzaj, nazwa, kod, attrs, geom, import_id)
                                   VALUES ('gdos_crfop',%s,%s,%s,%s,%s, ST_Multi(ST_GeomFromWKB(%s,2180)), %s)""",
                                (layer, m["rodzaj_wg_warstwy"].get(layer), _prop(props, m["pola"]["nazwa"]),
                                 _prop(props, m["pola"]["kod"]), json.dumps(props, default=str),
                                 wkb.dumps(row.geometry), run.id),
                            )
                        run.records += len(gdf)
                conn.commit()
        except SourceUnavailable as e:
            log.warning("GDOŚ pominięte: %s", e)
    conn.close()


def import_prg() -> None:
    from shapely.geometry import Point
    m = bdl_mapping()["prg"]
    url = load_sources()["prg_wojewodztwa"]["url"]
    conn = connect()
    with HttpClient(timeout_s=180) as client:
        try:
            with import_run(conn, "prg_wojewodztwa", "ref.wojewodztwo", "podkarpackie") as run:
                if not m["warstwa_wojewodztw"]:
                    raise MappingMissing("config/bdl_mapping.yaml: prg.warstwa_wojewodztw puste")
                lon, lat = m["punkt_wewnatrz_wgs84"]
                gdf = _to_storage(wfs_features(client, url, m["warstwa_wojewodztw"], [lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01]))
                pt = _to_storage(gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs="EPSG:4326")).geometry.iloc[0]
                gdf = gdf[gdf.geometry.contains(pt)]
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM ref.wojewodztwo WHERE source_id='prg_wojewodztwa'")
                    for _, row in gdf.iterrows():
                        props = {k: v for k, v in row.items() if k != "geometry"}
                        cur.execute(
                            """INSERT INTO ref.wojewodztwo (source_id, teryt, nazwa, attrs, geom, import_id)
                               VALUES ('prg_wojewodztwa',%s,%s,%s, ST_Multi(ST_GeomFromWKB(%s,2180)), %s)""",
                            (_prop(props, m["pole_teryt"]), _prop(props, m["pole_nazwy"]),
                             json.dumps(props, default=str), wkb.dumps(row.geometry), run.id))
                run.records = len(gdf)
                conn.commit()
        except SourceUnavailable as e:
            log.warning("PRG pominięte: %s", e)
    conn.close()


def _union_bbox() -> list[float]:
    bbs = [a["bbox_roboczy_wgs84"] for a in pilot_config()["obszary"]]
    return [min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs)]
