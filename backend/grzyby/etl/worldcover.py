"""Warstwa referencyjna lasów: ESA WorldCover 2021 v200 (10 m, CC BY 4.0), klasa 10 = „Tree cover”.

Służy WYŁĄCZNIE do oceny pokrycia danymi: ile lasu (wg obrazu satelitarnego) w granicach województwa ma opis
z BDL. „Tree cover” ≠ las w rozumieniu ustawy (obejmuje zadrzewienia, parki; pomija zręby i uprawy) — wynik
jest przybliżeniem i tak jest opisany. Wynik: siatka 1 km (EPSG:2180) z powierzchnią lasu referencyjnego.
"""
from __future__ import annotations

import logging
import math

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio import features
from rasterio.windows import Window, from_bounds
from shapely import wkb
from shapely.geometry import box
from shapely.ops import transform as shp_transform

from ..config import RAW_DIR
from ..db import connect, import_run
from .http import HttpClient

log = logging.getLogger(__name__)
SOURCE_ID = "esa_worldcover_2021"
URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
TREE_CLASS = 10
CELL_M = 1000
AGG = 10            # 10×10 pikseli 10 m → piksel ~100 m (w stopniach) przed przypisaniem do komórek 1 km


def tiles_for(bounds: tuple[float, float, float, float]) -> list[str]:
    lon0, lat0, lon1, lat1 = bounds
    out = []
    for lat in range(math.floor(lat0 / 3) * 3, math.ceil(lat1 / 3) * 3, 3):
        for lon in range(math.floor(lon0 / 3) * 3, math.ceil(lon1 / 3) * 3, 3):
            out.append(f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}")
    return out


def province_geometry(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT ST_AsBinary(ST_Union(geom)) FROM ref.wojewodztwo")
        g = cur.fetchone()[0]
    if g is None:
        raise RuntimeError("Brak granicy województwa (PRG) — najpierw `import prg`")
    return wkb.loads(bytes(g))


def forest_fraction_cells(tile_paths: list, province_2180) -> dict[tuple[int, int], float]:
    """Powierzchnia [ha] klasy Tree cover w komórkach 1 km (klucz: indeksy x,y komórki), tylko w granicach województwa."""
    to4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
    to2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
    prov4326 = shp_transform(to4326, province_2180)
    acc: dict[tuple[int, int], float] = {}
    for path in tile_paths:
        with rasterio.open(path) as ds:
            win = from_bounds(*prov4326.bounds, transform=ds.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, ds.width, ds.height))
            step = 2000  # pas wierszy (wielokrotność AGG)
            for r0 in range(int(win.row_off), int(win.row_off + win.height), step):
                h = min(step, int(win.row_off + win.height) - r0)
                h -= h % AGG
                w = int(win.width) - int(win.width) % AGG
                if h <= 0 or w <= 0:
                    continue
                sub = Window(int(win.col_off), r0, w, h)
                a = ds.read(1, window=sub)
                frac = (a == TREE_CLASS).reshape(h // AGG, AGG, w // AGG, AGG).mean(axis=(1, 3))
                tr = ds.window_transform(sub) * rasterio.Affine.scale(AGG)
                inside = features.geometry_mask([prov4326], frac.shape, tr, invert=True)
                rows, cols = np.nonzero(inside & (frac > 0))
                if rows.size == 0:
                    continue
                lon = tr.c + (cols + 0.5) * tr.a
                lat = tr.f + (rows + 0.5) * tr.e
                # powierzchnia piksela zagregowanego [m²] na danej szerokości
                px_area = (abs(tr.a) * 111_320 * np.cos(np.radians(lat))) * (abs(tr.e) * 110_574)
                x, y = to2180.transform(lon, lat)
                ix, iy = np.floor(x / CELL_M).astype(int), np.floor(y / CELL_M).astype(int)
                ha = frac[rows, cols] * px_area / 10_000
                for k, v in zip(zip(ix.tolist(), iy.tolist()), ha.tolist()):
                    acc[k] = acc.get(k, 0.0) + v
    return acc


def import_reference(min_ha: float = 1.0) -> int:
    """Pobiera kafle WorldCover, liczy las referencyjny w siatce 1 km i zapisuje coverage.siatka."""
    conn = connect()
    with import_run(conn, SOURCE_ID, "coverage.siatka", "podkarpackie") as run:
        prov = province_geometry(conn)
        to4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
        tiles = tiles_for(shp_transform(to4326, prov).bounds)
        paths = []
        with HttpClient(min_interval_s=0.5, timeout_s=600) as client:
            for t in tiles:
                paths.append(client.download(URL.format(tile=t), RAW_DIR / "worldcover" / f"{t}.tif"))
        cells = forest_fraction_cells(paths, prov)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE coverage.siatka")
            for (ix, iy), ha in cells.items():
                if ha < min_ha:
                    continue
                g = box(ix * CELL_M, iy * CELL_M, (ix + 1) * CELL_M, (iy + 1) * CELL_M)
                cur.execute("""INSERT INTO coverage.siatka (ix, iy, las_ref_ha, geom) VALUES (%s,%s,%s, ST_GeomFromWKB(%s,2180))""",
                            (ix, iy, round(ha, 2), wkb.dumps(g)))
        run.records = sum(1 for v in cells.values() if v >= min_ha)
        conn.commit()
    conn.close()
    return run.records


def compute_coverage() -> dict:
    """Powierzchnia wydzieleń BDL w komórkach (wg klasy danych) i klasa komórki; zwraca podsumowanie."""
    conn = connect()
    with import_run(conn, "pokrycie", "coverage.siatka", "podkarpackie") as run, conn.cursor() as cur:
        cur.execute("""
            WITH s AS (
              SELECT c.ix, c.iy,
                     SUM(ST_Area(ST_Intersection(c.geom, w.geom))) FILTER (WHERE w.klasa_danych = 'pelniejsze') / 1e4 AS full_ha,
                     SUM(ST_Area(ST_Intersection(c.geom, w.geom))) / 1e4 AS any_ha
              FROM coverage.siatka c JOIN forest.wydzielenie w ON ST_Intersects(c.geom, w.geom)
              GROUP BY c.ix, c.iy)
            UPDATE coverage.siatka c SET bdl_ha = COALESCE(s.any_ha, 0), bdl_pelniejsze_ha = COALESCE(s.full_ha, 0)
            FROM s WHERE s.ix = c.ix AND s.iy = c.iy""")
        cur.execute("UPDATE coverage.siatka SET bdl_ha = COALESCE(bdl_ha, 0), bdl_pelniejsze_ha = COALESCE(bdl_pelniejsze_ha, 0)")
        cur.execute("""UPDATE coverage.siatka SET klasa = CASE
                         WHEN LEAST(bdl_ha, las_ref_ha) < 0.25 * las_ref_ha THEN 'brak_oceny'
                         WHEN bdl_pelniejsze_ha >= 0.5 * LEAST(bdl_ha, las_ref_ha) THEN 'pelniejsze'
                         ELSE 'czesciowe' END""")
        cur.execute("""SELECT count(*), sum(las_ref_ha), sum(LEAST(bdl_ha, las_ref_ha)), sum(bdl_ha),
                              count(*) FILTER (WHERE klasa='pelniejsze'), count(*) FILTER (WHERE klasa='czesciowe'),
                              count(*) FILTER (WHERE klasa='brak_oceny') FROM coverage.siatka""")
        n, ref, covered, bdl, full, part, none = cur.fetchone()
        run.records = n
        conn.commit()
    conn.close()
    return {"komorek": n, "las_ref_ha": round(ref or 0), "pokryte_ha_szac": round(covered or 0), "bdl_ha_w_komorkach": round(bdl or 0),
            "pokrycie_proc": round(100 * (covered or 0) / ref, 1) if ref else None,
            "komorki_pelniejsze": full, "komorki_czesciowe": part, "komorki_brak_oceny": none}
