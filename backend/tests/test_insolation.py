from datetime import date

from grzyby.model.insolation import insolation_index

D = date(2026, 9, 15)


def test_flat_is_one_and_missing_is_none():
    assert insolation_index(49.5, 0.5, 180, D) == 1.0
    assert insolation_index(49.5, None, 180, D) is None


def test_south_more_than_flat_more_than_north():
    s = insolation_index(49.5, 20, 180, D)
    n = insolation_index(49.5, 20, 0, D)
    e = insolation_index(49.5, 20, 90, D)
    w = insolation_index(49.5, 20, 270, D)
    assert s > 1.0 > n
    assert abs(e - w) < 0.02 and n < e < s                     # wschód ≈ zachód (symetria względem południa)


def test_steeper_north_slope_darker():
    assert insolation_index(49.5, 30, 0, D) < insolation_index(49.5, 10, 0, D)


def test_noon_geometry_equinox():
    # równonoc, stok południowy nachylony o szerokość geograficzną: w południe Słońce prostopadle → indeks > 1
    assert insolation_index(49.5, 49.5, 180, date(2026, 3, 20)) > 1.2
