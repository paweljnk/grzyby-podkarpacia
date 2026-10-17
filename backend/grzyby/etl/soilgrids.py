"""SoilGrids 2.0 (ISRIC, CC BY 4.0) — ŹRÓDŁO ZASTĘPCZE właściwości gleby: pH(H2O) w warstwie 0–5 cm.

To wynik modelu globalnego w siatce 250 m, a nie lokalny pomiar. Zapisujemy średnią i kwantyle Q0.05/Q0.95
(przedział niepewności modelu). REST API SoilGrids jest wstrzymane — używamy WCS (maps.isric.org).
Jednostki w rastrach: pH × 10.
"""
from __future__ import annotations

import logging

import numpy as np
import rasterio
from pyproj import Transformer
from shapely.ops import transform as shp_transform

from ..config import RAW_DIR
from ..db import connect, import_run
from .bdl_province import province
from .http import HttpClient

log = logging.getLogger(__name__)
SOURCE_ID = "soilgrids"
WCS = "https://maps.isric.org/mapserv?map=/map/phh2o.map"
COVERAGES = {"ph_model": "phh2o_0-5cm_mean", "ph_q05": "phh2o_0-5cm_Q0.05", "ph_q95": "phh2o_0-5cm_Q0.95"}


def fetch_coverage(client: HttpClient, cov: str, bounds) -> "Path":
    lon0, lat0, lon1, lat1 = bounds
    url = (f"{WCS}&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID={cov}&FORMAT=image/tiff"
           f"&SUBSET=long({lon0:.4f},{lon1:.4f})&SUBSET=lat({lat0:.4f},{lat1:.4f})"
           "&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326")
    dest = RAW_DIR / "soilgrids" / f"{cov}.tif"
    return client.download(url, dest)


def sample_points(path, lonlat: list[tuple[float, float]]) -> np.ndarray:
    with rasterio.open(path) as ds:
        vals = np.array([v[0] for v in ds.sample(lonlat)], dtype="float64")
        nod = ds.nodata
    if nod is not None:
        vals[vals == nod] = np.nan
    vals[vals <= 0] = np.nan       # 0 = brak danych w produktach SoilGrids
    return vals / 10.0


def import_soilgrids() -> int:
    conn = connect()
    with import_run(conn, SOURCE_ID, "forest.wydzielenie.ph", "podkarpackie") as run:
        prov = province(conn)
        to4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
        b = shp_transform(to4326, prov).bounds
        b = (b[0] - 0.02, b[1] - 0.02, b[2] + 0.02, b[3] + 0.02)
        with HttpClient(min_interval_s=1.0, timeout_s=600) as client:
            paths = {k: fetch_coverage(client, c, b) for k, c in COVERAGES.items()}
        with conn.cursor() as cur:
            cur.execute("""SELECT id, ST_X(p), ST_Y(p) FROM (SELECT id, ST_Transform(ST_PointOnSurface(geom), 4326) p
                           FROM forest.wydzielenie) s""")
            rows = cur.fetchall()
        pts = [(r[1], r[2]) for r in rows]
        vals = {k: sample_points(p, pts) for k, p in paths.items()}
        f = lambda x: None if np.isnan(x) else round(float(x), 2)
        params = [(f(vals["ph_model"][i]), f(vals["ph_q05"][i]), f(vals["ph_q95"][i]), sid)
                  for i, (sid, _, _) in enumerate(rows) if not np.isnan(vals["ph_model"][i])]
        with conn.cursor() as cur:
            cur.executemany("""UPDATE forest.wydzielenie SET ph_model=%s, ph_q05=%s, ph_q95=%s, ph_pochodzenie='model'
                               WHERE id=%s""", params)
        n = len(params)
        run.records = n
        conn.commit()
    conn.close()
    return n
