"""Import rzeźby terenu z Copernicus DEM GLO-30 dla obszarów pilotażowych.

Kroki: pobranie kafli 1x1° → mozaika i przycięcie do bbox → reprojekcja do EPSG:2180 (siatka 25 m,
wyrównana do wielokrotności rozdzielczości) → nachylenie i ekspozycja (Horn) → GeoTIFF w data/derived
→ wpis w terrain.raster → statystyki strefowe dla wydzieleń, jeśli są w bazie.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject, transform_bounds
from shapely import wkb
from shapely.geometry import box, mapping

from ..config import CRS_STORAGE, DERIVED_DIR, RAW_DIR, pilot_config
from ..db import connect, import_run
from ..sources import update_source
from .http import HttpClient
from .terrain import slope_aspect_horn, zonal_stats

log = logging.getLogger(__name__)

SOURCE_ID = "copernicus_dem_glo30"
BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def tiles_for_bbox(bbox: list[float]) -> list[str]:
    lon0, lat0, lon1, lat1 = bbox
    names = []
    for lat in range(math.floor(lat0), math.ceil(lat1)):
        for lon in range(math.floor(lon0), math.ceil(lon1)):
            names.append(tile_name(lat, lon))
    return names


def aligned_grid(bounds_2180: tuple[float, float, float, float], res: float):
    x0, y0, x1, y1 = bounds_2180
    x0, y0 = math.floor(x0 / res) * res, math.floor(y0 / res) * res
    x1, y1 = math.ceil(x1 / res) * res, math.ceil(y1 / res) * res
    width, height = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    return rasterio.transform.from_origin(x0, y1, res, res), width, height


def area_bbox(conn, area: dict, margin_deg: float = 0.01) -> list[float]:
    """Zasięg rastra: prostokąt roboczy ∪ granica nadleśnictwa z BDL (jeśli zaimportowana), z marginesem."""
    b = list(area["bbox_roboczy_wgs84"])
    with conn.cursor() as cur:
        cur.execute("""SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
                       FROM (SELECT ST_Extent(ST_Transform(geom, 4326)) e FROM ref.obszar_pilotazowy
                             WHERE id=%s AND geom_origin='bdl') s""", (area["id"],))
        r = cur.fetchone()
    if r and r[0] is not None:
        b = [min(b[0], r[0] - margin_deg), min(b[1], r[1] - margin_deg), max(b[2], r[2] + margin_deg), max(b[3], r[3] + margin_deg)]
    return b


def build_area_rasters(area: dict, tile_paths: list[Path], res: float, out_dir: Path, bbox: list[float] | None = None) -> dict[str, Path]:
    bbox = bbox or area["bbox_roboczy_wgs84"]
    srcs = [rasterio.open(p) for p in tile_paths]
    try:
        mosaic, mos_tr = merge(srcs, bounds=tuple(bbox), nodata=np.nan, dtype="float32")
        src_crs = srcs[0].crs
    finally:
        for s in srcs:
            s.close()
    dst_tr, w, h = aligned_grid(transform_bounds("EPSG:4326", CRS_STORAGE, *bbox, densify_pts=21), res)
    elev = np.full((h, w), np.nan, dtype="float32")
    reproject(mosaic[0], elev, src_transform=mos_tr, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=dst_tr, dst_crs=CRS_STORAGE, dst_nodata=np.nan, resampling=Resampling.bilinear)
    # Poza bbox w WGS84 (po reprojekcji prostokąt staje się trapezem) zostaje NaN — to brak danych, nie zero.
    slope, aspect = slope_aspect_horn(elev, res, res)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", width=w, height=h, count=1, dtype="float32", crs=CRS_STORAGE,
                   transform=dst_tr, nodata=np.nan, compress="deflate", predictor=3, tiled=True)
    paths = {}
    for name, arr in (("wysokosc", elev), ("nachylenie", slope), ("ekspozycja", aspect)):
        p = out_dir / f"{area['id']}_{name}.tif"
        with rasterio.open(p, "w", **profile) as dst:
            dst.write(arr, 1)
            dst.update_tags(zrodlo=SOURCE_ID, pochodzenie="model",
                            uwaga="Copernicus DEM to DSM (z koronami drzew) — nie NMT")
        paths[name] = p
    return paths


def _register_area(cur, area: dict, import_id: int) -> None:
    geom = box(*transform_bounds("EPSG:4326", CRS_STORAGE, *area["bbox_roboczy_wgs84"], densify_pts=21))
    # Granicy z BDL nie nadpisujemy prostokątem roboczym.
    cur.execute(
        """INSERT INTO ref.obszar_pilotazowy (id, nazwa, typ_terenu, geom_origin, geom, import_id)
           VALUES (%s,%s,%s,'bbox_roboczy', ST_Multi(ST_GeomFromWKB(%s, 2180)), %s)
           ON CONFLICT (id) DO UPDATE SET nazwa=EXCLUDED.nazwa, typ_terenu=EXCLUDED.typ_terenu
           WHERE ref.obszar_pilotazowy.geom_origin='bbox_roboczy'""",
        (area["id"], area["nazwa"], area["typ_terenu"], wkb.dumps(geom), import_id),
    )


def _register_rasters(cur, area: dict, paths: dict[str, Path], res: float, import_id: int) -> None:
    for name, p in paths.items():
        with rasterio.open(p) as ds:
            arr = ds.read(1)
            fin = arr[np.isfinite(arr)]
            zasieg = box(*ds.bounds)
            cur.execute(
                """INSERT INTO terrain.raster (id, source_id, obszar_id, warstwa, sciezka, crs, rozdzielczosc_m,
                       szerokosc_px, wysokosc_px, n_nodata, stat_min, stat_max, stat_sr, zasieg, import_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_GeomFromWKB(%s,2180), %s)
                   ON CONFLICT (id) DO UPDATE SET sciezka=EXCLUDED.sciezka, n_nodata=EXCLUDED.n_nodata,
                       stat_min=EXCLUDED.stat_min, stat_max=EXCLUDED.stat_max, stat_sr=EXCLUDED.stat_sr,
                       szerokosc_px=EXCLUDED.szerokosc_px, wysokosc_px=EXCLUDED.wysokosc_px,
                       zasieg=EXCLUDED.zasieg, import_id=EXCLUDED.import_id""",
                (f"{SOURCE_ID}:{area['id']}:{name}", SOURCE_ID, area["id"], name, str(p), CRS_STORAGE, res,
                 ds.width, ds.height, int(arr.size - fin.size),
                 float(fin.min()) if fin.size else None, float(fin.max()) if fin.size else None,
                 float(fin.mean()) if fin.size else None, wkb.dumps(zasieg), import_id),
            )


def compute_zonal_for_area(conn, area_id: str, paths: dict[str, Path], res: float,
                           flat_threshold: float, import_id: int) -> int:
    with rasterio.open(paths["wysokosc"]) as ds:
        elev, transform = ds.read(1), ds.transform
    with rasterio.open(paths["nachylenie"]) as ds:
        slope = ds.read(1)
    with rasterio.open(paths["ekspozycja"]) as ds:
        aspect = ds.read(1)
    n = 0
    with conn.cursor() as cur:
        cur.execute("SELECT id, ST_AsBinary(geom) FROM forest.wydzielenie WHERE obszar_id=%s", (area_id,))
        rows = cur.fetchall()
        for wid, g in rows:
            st = zonal_stats(wkb.loads(bytes(g)), elev, slope, aspect, transform, flat_threshold)
            if st.n_pikseli == 0:
                continue  # brak pokrycia rastrem — brak wiersza = brak danych
            cur.execute(
                """INSERT INTO terrain.wydzielenie_teren (wydzielenie_id, dem_source_id, rozdzielczosc_m, n_pikseli,
                       wys_min, wys_sr, wys_max, nachylenie_sr_deg, nachylenie_max_deg, ekspozycja_sr_deg,
                       ekspozycja_klasa, import_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (wydzielenie_id) DO UPDATE SET dem_source_id=EXCLUDED.dem_source_id,
                       rozdzielczosc_m=EXCLUDED.rozdzielczosc_m, n_pikseli=EXCLUDED.n_pikseli,
                       wys_min=EXCLUDED.wys_min, wys_sr=EXCLUDED.wys_sr, wys_max=EXCLUDED.wys_max,
                       nachylenie_sr_deg=EXCLUDED.nachylenie_sr_deg, nachylenie_max_deg=EXCLUDED.nachylenie_max_deg,
                       ekspozycja_sr_deg=EXCLUDED.ekspozycja_sr_deg, ekspozycja_klasa=EXCLUDED.ekspozycja_klasa,
                       import_id=EXCLUDED.import_id""",
                (wid, SOURCE_ID, res, st.n_pikseli, st.wys_min, st.wys_sr, st.wys_max, st.nachylenie_sr_deg,
                 st.nachylenie_max_deg, st.ekspozycja_sr_deg, st.ekspozycja_klasa, import_id),
            )
            n += 1
    return n


def import_dem() -> None:
    cfg = pilot_config()
    res = float(cfg["teren"]["rozdzielczosc_docelowa_m"])
    flat = float(cfg["teren"]["prog_plaskiego_terenu_deg"])
    raw_dir = RAW_DIR / "copernicus_dem"
    conn = connect()
    with HttpClient(min_interval_s=0.5) as client:
        for area in cfg["obszary"]:
            with import_run(conn, SOURCE_ID, "terrain.raster", area["id"], {"rozdzielczosc_m": res}) as run:
                bbox = area_bbox(conn, area)
                tiles = []
                for t in tiles_for_bbox(bbox):
                    log.info("Kafel %s", t)
                    tiles.append(client.download(f"{BASE_URL}/{t}/{t}.tif", raw_dir / f"{t}.tif"))
                paths = build_area_rasters(area, tiles, res, DERIVED_DIR / "teren", bbox)
                with conn.cursor() as cur:
                    _register_area(cur, area, run.id)
                    _register_rasters(cur, area, paths, res, run.id)
                run.records = len(paths)
                conn.commit()
            with import_run(conn, SOURCE_ID, "terrain.wydzielenie_teren", area["id"]) as run:
                run.records = compute_zonal_for_area(conn, area["id"], paths, res, flat, run.id)
                if run.records == 0:
                    run.set_status("partial", "Brak wydzieleń w bazie dla obszaru — statystyki strefowe niepoliczone")
                conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT max(finished_at) FROM meta.import_log WHERE source_id=%s AND status IN ('ok','partial')",
                    (SOURCE_ID,))
        last = cur.fetchone()[0]
    update_source(SOURCE_ID, ostatni_import=last.isoformat() if last else None)
    conn.close()
