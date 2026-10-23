"""Testy wymagane w kryterium Etapu 3c."""
from datetime import date, timedelta

import pytest

from grzyby.astro import CalendarDay
from grzyby.model.combine import combine, weighted_geometric
from grzyby.model.components import Observation, Stand, habitat, observations, season_factor, weather
from grzyby.species import all_species
from grzyby.weather.aggregate import DailyWeather

SP = all_species()["boletus_edulis"]
DAY = date(2026, 9, 1)

GOOD_STAND = Stand(1, "SW", {"SW": 0.6, "BK": 0.3, "JD": 0.1}, 80, "LMGśw", "brunatna kwaśna", 650.0, 12.0)
NO_HABITAT = Stand(2, "OL", {"OL": 1.0}, 15, "Ol", "torfowa", 650.0, 2.0)


def series(precip_by_ago: dict[int, float], tmean=15.0, tmin=9.0, et0=1.5, n=40, sm=0.3, end=DAY):
    out = []
    for k in range(n - 1, -1, -1):
        out.append(DailyWeather(end - timedelta(days=k), "reanaliza", 24, precip_by_ago.get(k, 0.0),
                                tmin, tmean, tmin + 12, 85.0, sm, 13.0, et0))
    return out


IDEAL = series({9: 25.0, 10: 20.0, 3: 6.0, 1: 4.0})
DROUGHT = series({35: 5.0}, tmean=21, tmin=13, et0=4.0, sm=0.10)


def best_calendar_d():
    return 5.0, {"eksperymentalny": True}


def test_no_habitat_with_ideal_weather_and_favourable_calendar_is_low():
    A = habitat(NO_HABITAT, SP)
    B, _, gates = weather(SP, IDEAL, DAY, 650)
    assert B.wynik > 60                      # pogoda rzeczywiście dobra
    s = combine(A, B, C=0, D=5.0, D_details={"eksperymentalny": True}, drought=gates["susza"], protection=[])
    assert A.wynik < 30
    assert s.wynik < 40
    assert not s.rekomendowane and any(g.kod == "siedlisko" for g in s.bramki)


def test_good_habitat_ideal_weather_is_high():
    A = habitat(GOOD_STAND, SP)
    B, _, gates = weather(SP, IDEAL, DAY, 650)
    s = combine(A, B, 0, 0, None, gates["susza"], [])
    assert s.wynik > 70 and s.rekomendowane and s.jakosc == "wysoka"


def test_drought_gives_low_score_and_gate():
    A = habitat(GOOD_STAND, SP)
    B, ind, gates = weather(SP, DROUGHT, DAY, 650)
    s = combine(A, B, 0, 5.0, {"eksperymentalny": True}, gates["susza"], [])
    assert gates["susza"] and s.wynik < 35
    assert not s.rekomendowane and any(g.kod == "susza" for g in s.bramki)


def test_missing_soil_lowers_completeness_but_not_zero():
    full = habitat(GOOD_STAND, SP)
    nosoil = habitat(Stand(**{**GOOD_STAND.__dict__, "gleba": None}), SP)
    assert 0 < nosoil.kompletnosc < full.kompletnosc
    assert nosoil.wynik is not None and nosoil.wynik > 0
    assert any("gleby" in r for r in nosoil.uzasadnienie)


def test_out_of_season_zeroes_weather():
    B, _, _ = weather(SP, series({9: 30.0}, end=date(2026, 3, 1)), date(2026, 3, 1), 300)
    assert B.wynik == 0


def test_altitude_shifts_season():
    low, _ = season_factor(SP, date(2026, 6, 20), 200, 0.3)
    high, _ = season_factor(SP, date(2026, 6, 20), 1000, 0.3)
    assert low > 0 and high == 0     # w górach sezon zaczyna się później


def test_protection_gate_national_park():
    A = habitat(GOOD_STAND, SP)
    B, _, g = weather(SP, IDEAL, DAY, 650)
    s = combine(A, B, 15, 5, None, g["susza"], [{"rodzaj": "park_narodowy", "nazwa": "Park X"}])
    assert not s.rekomendowane and any(x.kod == "zakaz" for x in s.bramki)


def test_score_bounds_and_geometric_mean():
    assert weighted_geometric(0, 100, 0.5, 0.5) == 0
    assert weighted_geometric(100, 100, 0.5, 0.5) == pytest.approx(100)
    assert weighted_geometric(25, 100, 0.5, 0.5) == pytest.approx(50)
    A = habitat(GOOD_STAND, SP)
    B, _, g = weather(SP, IDEAL, DAY, 650)
    assert combine(A, B, 15, 5, None, False, []).wynik <= 100


def test_missing_weather_reduces_but_reports():
    A = habitat(GOOD_STAND, SP)
    B, _, g = weather(SP, [], DAY, 650)
    s = combine(A, B, 0, 0, None, g["susza"], [])
    assert s.wynik is None and not s.rekomendowane and any("brak danych" in r for r in s.uzasadnienie)


def test_observations_modifier_sign_decay_and_cap():
    found_now, _ = observations([Observation(0, 0.5, True, "wysoka")])
    found_old, _ = observations([Observation(30, 0.5, True, "wysoka")])
    nothing, _ = observations([Observation(0, 0.5, False, "wysoka", 180)])
    many, _ = observations([Observation(0, 0.1, True, "wysoka")] * 50)
    assert found_now > found_old > 0 and nothing < 0 and many <= 15
    assert observations([Observation(0, 50, True, "wysoka")])[0] == 0


def test_south_slope_dries_faster_than_north():
    daily = series({10: 30.0}, et0=2.5)
    _, ind_n, _ = weather(SP, daily, DAY, 300, None, 0.7)
    _, ind_s, _ = weather(SP, daily, DAY, 300, None, 1.3)
    _, ind_f, _ = weather(SP, daily, DAY, 300, None, 1.0)
    assert ind_s.bilans_14_mm < ind_f.bilans_14_mm < ind_n.bilans_14_mm
