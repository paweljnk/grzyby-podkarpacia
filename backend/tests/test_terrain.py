import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import box

from grzyby.etl.terrain import aspect_class, circular_mean_deg, slope_aspect_horn, zonal_stats

RES = 25.0


def plane(dz_dx_east, dz_dy_north, n=7):
    cols = np.arange(n) * RES
    rows = np.arange(n) * RES          # wiersze rosną na południe
    x, y_south = np.meshgrid(cols, rows)
    return (100 + dz_dx_east * x - dz_dy_north * y_south).astype("float32")


@pytest.mark.parametrize("gx,gy,expected_aspect", [
    (0.1, 0.0, 270.0),   # teren wznosi się na wschód → stok opada na zachód
    (-0.1, 0.0, 90.0),
    (0.0, 0.1, 180.0),   # wznosi się na północ → stok południowy
    (0.0, -0.1, 0.0),
])
def test_aspect_of_planes(gx, gy, expected_aspect):
    slope, aspect = slope_aspect_horn(plane(gx, gy), RES, RES)
    inner = aspect[1:-1, 1:-1]
    assert np.allclose(inner % 360, expected_aspect % 360, atol=1e-3) or (
        expected_aspect == 0.0 and np.allclose(np.minimum(inner, 360 - inner), 0, atol=1e-3))
    assert np.allclose(slope[1:-1, 1:-1], np.degrees(np.arctan(0.1)), atol=1e-3)


def test_edges_and_nodata_are_nan():
    z = plane(0.1, 0.0)
    z[3, 3] = np.nan
    slope, _ = slope_aspect_horn(z, RES, RES)
    assert np.isnan(slope[0]).all() and np.isnan(slope[:, -1]).all()
    assert np.isnan(slope[2:5, 2:5]).all()          # sąsiedzi NoData też bez wartości
    assert np.isfinite(slope[1, 1])


def test_flat_has_zero_slope_and_no_aspect():
    slope, aspect = slope_aspect_horn(np.full((5, 5), 300.0), RES, RES)
    assert np.allclose(slope[1:-1, 1:-1], 0) and np.isnan(aspect[1:-1, 1:-1]).all()


def test_circular_mean_wraps_around_north():
    assert circular_mean_deg(np.array([350.0, 10.0])) == pytest.approx(0.0, abs=1e-6)
    assert circular_mean_deg(np.array([0.0, 180.0])) is None
    assert circular_mean_deg(np.array([np.nan])) is None


@pytest.mark.parametrize("deg,cls", [(0, "N"), (22.4, "N"), (22.6, "NE"), (180, "S"), (337.6, "N"), (300, "NW")])
def test_aspect_class(deg, cls):
    assert aspect_class(deg) == cls


def test_zonal_stats_on_synthetic_plane():
    z = plane(0.0, 0.1, n=20)               # stok południowy, 5.71°
    slope, aspect = slope_aspect_horn(z, RES, RES)
    tr = from_origin(0, 20 * RES, RES, RES)
    st = zonal_stats(box(5 * RES, 5 * RES, 10 * RES, 10 * RES), z, slope, aspect, tr, flat_threshold_deg=2.0)
    assert st.n_pikseli == 25
    assert st.ekspozycja_klasa == "S"
    assert st.nachylenie_sr_deg == pytest.approx(5.71, abs=0.01)
    assert st.wys_min < st.wys_sr < st.wys_max


def test_zonal_stats_flat_and_outside():
    z = np.full((10, 10), 200.0, dtype="float32")
    slope, aspect = slope_aspect_horn(z, RES, RES)
    tr = from_origin(0, 10 * RES, RES, RES)
    st = zonal_stats(box(50, 50, 150, 150), z, slope, aspect, tr, 2.0)
    assert st.ekspozycja_klasa == "plasko" and st.ekspozycja_sr_deg is None
    out = zonal_stats(box(10_000, 10_000, 10_100, 10_100), z, slope, aspect, tr, 2.0)
    assert out.n_pikseli == 0 and out.wys_sr is None


def test_zonal_stats_tiny_polygon_uses_touched_pixels():
    z = plane(0.0, 0.1, n=10)
    slope, aspect = slope_aspect_horn(z, RES, RES)
    tr = from_origin(0, 10 * RES, RES, RES)
    st = zonal_stats(box(101, 101, 104, 104), z, slope, aspect, tr, 2.0)
    assert st.n_pikseli >= 1
