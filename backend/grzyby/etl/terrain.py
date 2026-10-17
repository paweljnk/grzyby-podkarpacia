"""Nachylenie, ekspozycja i statystyki strefowe rzeźby terenu dla wydzieleń.

Konwencje:
  - raster w układzie metrycznym (EPSG:2180), wiersze rosną na południe;
  - ekspozycja = azymut kierunku spadku, 0° = N, zgodnie z ruchem wskazówek zegara;
  - piksele brzegowe i z NoData mają NaN (nie zgadujemy wartości).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from affine import Affine
from rasterio import features
from shapely.geometry.base import BaseGeometry

ASPECT_CLASSES = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def slope_aspect_horn(dem: np.ndarray, res_x: float, res_y: float) -> tuple[np.ndarray, np.ndarray]:
    """Nachylenie [°] i ekspozycja [°] metodą Horna (1981). NaN na brzegach i przy NoData."""
    z = np.asarray(dem, dtype="float64")
    p = np.pad(z, 1, constant_values=np.nan)
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dz_dx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * res_x)          # wzrost na wschód
    dz_dy = ((a + 2 * b + c) - (g + 2 * h + i)) / (8 * res_y)          # wzrost na północ
    slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    aspect = np.degrees(np.arctan2(-dz_dx, -dz_dy)) % 360.0
    aspect = np.where((dz_dx == 0) & (dz_dy == 0), np.nan, aspect)
    # Horn nie używa komórki środkowej — NoData w środku też musi dać brak wyniku.
    slope = np.where(np.isnan(z), np.nan, slope)
    aspect = np.where(np.isnan(z), np.nan, aspect)
    return slope.astype("float32"), aspect.astype("float32")


def circular_mean_deg(angles: np.ndarray) -> float | None:
    a = angles[np.isfinite(angles)]
    if a.size == 0:
        return None
    r = np.radians(a)
    s, c = np.sin(r).mean(), np.cos(r).mean()
    if np.hypot(s, c) < 1e-9:  # kierunki się znoszą — brak dominującej ekspozycji
        return None
    deg = float(np.degrees(np.arctan2(s, c)) % 360.0)
    return 0.0 if deg >= 360.0 - 1e-9 else deg


def aspect_class(deg: float | None) -> str | None:
    if deg is None:
        return None
    return ASPECT_CLASSES[int(((deg + 22.5) % 360) // 45)]


@dataclass
class ZoneStats:
    n_pikseli: int
    wys_min: float | None
    wys_sr: float | None
    wys_max: float | None
    nachylenie_sr_deg: float | None
    nachylenie_max_deg: float | None
    ekspozycja_sr_deg: float | None
    ekspozycja_klasa: str | None


def _nan_stat(fn, arr: np.ndarray) -> float | None:
    v = arr[np.isfinite(arr)]
    return float(fn(v)) if v.size else None


def zonal_stats(
    geom: BaseGeometry,
    elev: np.ndarray,
    slope: np.ndarray,
    aspect: np.ndarray,
    transform: Affine,
    flat_threshold_deg: float,
) -> ZoneStats:
    """Statystyki dla jednego poligonu (geometria w CRS rastra)."""
    h, w = elev.shape
    minx, miny, maxx, maxy = geom.bounds
    inv = ~transform
    c_a, r_a = inv @ (minx, maxy)
    c_b, r_b = inv @ (maxx, miny)
    c0, r0 = max(int(np.floor(min(c_a, c_b))), 0), max(int(np.floor(min(r_a, r_b))), 0)
    c1, r1 = min(int(np.ceil(max(c_a, c_b))) + 1, w), min(int(np.ceil(max(r_a, r_b))) + 1, h)
    if c0 >= c1 or r0 >= r1:
        return ZoneStats(0, None, None, None, None, None, None, None)
    wt = transform @ Affine.translation(c0, r0)
    shape = (r1 - r0, c1 - c0)
    mask = features.geometry_mask([geom], shape, wt, invert=True, all_touched=False)
    if not mask.any():  # wydzielenie mniejsze niż piksel — bierzemy piksele dotknięte
        mask = features.geometry_mask([geom], shape, wt, invert=True, all_touched=True)
    e = elev[r0:r1, c0:c1][mask]
    s = slope[r0:r1, c0:c1][mask]
    a = aspect[r0:r1, c0:c1][mask]
    n = int(np.isfinite(e).sum())
    if n == 0:
        return ZoneStats(0, None, None, None, None, None, None, None)
    slope_mean = _nan_stat(np.mean, s)
    if slope_mean is not None and slope_mean < flat_threshold_deg:
        asp, cls = None, "plasko"
    else:
        asp = circular_mean_deg(a[np.isfinite(s) & (s >= flat_threshold_deg)])
        cls = aspect_class(asp)
    return ZoneStats(
        n_pikseli=n,
        wys_min=_nan_stat(np.min, e),
        wys_sr=_nan_stat(np.mean, e),
        wys_max=_nan_stat(np.max, e),
        nachylenie_sr_deg=slope_mean,
        nachylenie_max_deg=_nan_stat(np.max, s),
        ekspozycja_sr_deg=asp,
        ekspozycja_klasa=cls,
    )
