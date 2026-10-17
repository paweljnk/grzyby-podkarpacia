"""Pobieranie warstw z oficjalnego interfejsu zapytań ArcGIS REST usług BDL (Map,Query,Data; stronicowanie).

Import jest przyrostowy i wznawialny: każda jednostka (nadleśnictwo albo kafel) trafia do pliku etapowego
`data/stage/<źródło>/<jednostka>.jsonl.gz` z plikiem `.done`; ponowne uruchomienie pomija jednostki, których
plik jest świeższy niż `odswiezanie_dni`. Przerwane pobieranie jednostki zaczyna ją od nowa (plik .part).
"""
from __future__ import annotations

import gzip
import json
import logging
import time
from pathlib import Path
from typing import Iterator

from shapely.geometry import MultiPolygon, Polygon
from shapely.validation import make_valid

from ..config import DATA_DIR
from .http import HttpClient

log = logging.getLogger(__name__)
REST = "https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services"
PAGE = 2000


def _signed_area(ring: list) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0, *_), (x1, y1, *_) in zip(ring, ring[1:])) / 2


def esri_to_shapely(geom: dict):
    """Pierścienie Esri: zewnętrzne zgodnie z ruchem wskazówek (pole ujemne), otwory przeciwnie."""
    rings = geom.get("rings") or []
    outers, holes = [], []
    for r in rings:
        if len(r) < 4:
            continue
        (outers if _signed_area(r) < 0 else holes).append([(p[0], p[1]) for p in r])
    if not outers and holes:          # niektóre serwery zapisują odwrotną orientację
        outers, holes = holes, []
    polys = [Polygon(o) for o in outers]
    hole_lists: list[list] = [[] for _ in polys]
    for h in holes:
        hp = Polygon(h)
        for i, p in enumerate(polys):
            if p.contains(hp.representative_point()):
                hole_lists[i].append(h)
                break
    out = [Polygon(p.exterior.coords, hl) for p, hl in zip(polys, hole_lists)]
    if not out:
        return None
    g = MultiPolygon(out) if len(out) > 1 else out[0]
    return g


def fix_geometry(g):
    """Zwraca (geometria MultiPolygon, czy_naprawiona). Geometrie niepoprawne naprawiamy make_valid."""
    fixed = False
    if not g.is_valid:
        g = make_valid(g)
        fixed = True
        polys = [p for p in getattr(g, "geoms", [g]) if p.geom_type in ("Polygon", "MultiPolygon")]
        parts = []
        for p in polys:
            parts.extend(getattr(p, "geoms", [p]))
        g = MultiPolygon(parts) if parts else None
    elif g.geom_type == "Polygon":
        g = MultiPolygon([g])
    return g, fixed


def query_pages(client: HttpClient, service: str, layer: int, params: dict) -> Iterator[dict]:
    """Wszystkie obiekty zapytania, strona po stronie (resultOffset), z geometrią w EPSG:2180."""
    url = f"{REST}/{service}/MapServer/{layer}/query"
    offset = 0
    while True:
        p = {"f": "json", "outSR": 2180, "returnGeometry": "true", "outFields": "*",
             "resultRecordCount": PAGE, "resultOffset": offset, **params}
        r = client.get(url, params=p, use_cache=False)
        if r.status_code != 200:
            raise RuntimeError(f"{service}/{layer}: HTTP {r.status_code}")
        d = r.json()
        if "error" in d:
            raise RuntimeError(f"{service}/{layer}: {d['error']}")
        feats = d.get("features", [])
        yield from feats
        if not feats or not d.get("exceededTransferLimit"):
            break
        offset += len(feats)


def stage_unit(client: HttpClient, source: str, unit: str, service: str, layer: int, params: dict,
               refresh_days: float) -> tuple[Path, int, bool]:
    """Pobiera jednostkę do pliku etapowego (lub używa istniejącego). Zwraca (ścieżka, liczba obiektów, czy z cache)."""
    d = DATA_DIR / "stage" / source
    d.mkdir(parents=True, exist_ok=True)
    path, done = d / f"{unit}.jsonl.gz", d / f"{unit}.done"
    if path.exists() and done.exists() and time.time() - done.stat().st_mtime < refresh_days * 86400:
        return path, int(json.loads(done.read_text())["n"]), True
    tmp = d / f"{unit}.jsonl.gz.part"
    n = 0
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for feat in query_pages(client, service, layer, params):
            f.write(json.dumps(feat, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(path)
    done.write_text(json.dumps({"n": n, "zapytanie": params, "warstwa": f"{service}/{layer}",
                                "pobrano": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
    return path, n, False


def read_stage(path: Path) -> Iterator[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def tiles(bounds: tuple[float, float, float, float], step: float) -> list[tuple[str, tuple[float, float, float, float]]]:
    lon0, lat0, lon1, lat1 = bounds
    out = []
    y = lat0
    while y < lat1:
        x = lon0
        while x < lon1:
            out.append((f"t{y:.2f}_{x:.2f}", (round(x, 4), round(y, 4), round(min(x + step, lon1), 4), round(min(y + step, lat1), 4))))
            x += step
        y += step
    return out


def envelope_params(b: tuple[float, float, float, float]) -> dict:
    return {"geometry": ",".join(map(str, b)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects"}
