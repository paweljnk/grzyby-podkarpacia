"""Testy astronomiczne. Momenty faz porównane z niezależnymi tabelami USNO "Phases of the Moon"
(aa.usno.navy.mil) / NASA (zaćmienia): nów 2024-04-08 18:21 UTC (całkowite zaćmienie Słońca),
pełnia 2024-09-18 02:34 UTC (częściowe zaćmienie Księżyca), pełnia 2025-03-14 06:55 UTC (całkowite zaćmienie
Księżyca). Wartości wpisane z pamięci autora testu — przed publikacją potwierdzić w tabelach USNO/IMCCE.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from grzyby.astro import (calendar_day, calendar_modifier, illumination, moon_constellation, phase_name,
                          principal_phases, rise_set, sun_constellation)
from grzyby.config import load_yaml

UTC = timezone.utc


@pytest.mark.parametrize("expected,name", [
    (datetime(2024, 4, 8, 18, 21, tzinfo=UTC), "now"),
    (datetime(2024, 9, 18, 2, 34, tzinfo=UTC), "pelnia"),
    (datetime(2025, 3, 14, 6, 55, tzinfo=UTC), "pelnia"),
])
def test_principal_phase_times_match_usno(expected, name):
    found = principal_phases(expected - timedelta(days=1), expected + timedelta(days=1))
    assert len(found) == 1 and found[0][1] == name
    assert abs((found[0][0] - expected).total_seconds()) < 120


def test_illumination_extremes():
    assert illumination(datetime(2025, 3, 14, 6, 55, tzinfo=UTC)) > 0.99
    assert illumination(datetime(2024, 4, 8, 18, 21, tzinfo=UTC)) < 0.01


def test_phase_names_from_angle():
    assert phase_name(0.5) == "now" and phase_name(359) == "now"
    assert phase_name(45) == "sierp_przybywajacy" and phase_name(135) == "garb_przybywajacy"
    assert phase_name(180) == "pelnia" and phase_name(300) == "sierp_ubywajacy"


def test_iau_boundaries_via_sun_position():
    # Słońce wg granic IAU: w Strzelcu na początku stycznia, w Wężowniku na początku grudnia
    # (przy znakach zodiaku byłby to odpowiednio Koziorożec i Strzelec — test odróżnia gwiazdozbiory od znaków).
    assert sun_constellation(datetime(2026, 1, 5, 12, tzinfo=UTC)) == "Sgr"
    assert sun_constellation(datetime(2026, 12, 5, 12, tzinfo=UTC)) == "Oph"


def test_mapping_covers_twelve_constellations_and_four_elements():
    m = load_yaml("kalendarz.yaml")["gwiazdozbiory"]
    assert len(m) == 12
    assert {v for v in m.values()} == {"owoc", "korzen", "lisc", "kwiat"}
    assert all(list(m.values()).count(t) == 3 for t in ("owoc", "korzen", "lisc", "kwiat"))


def test_moon_moves_through_constellations_monthly():
    start = datetime(2026, 10, 1, tzinfo=UTC)
    seen = {moon_constellation(start + timedelta(hours=12 * i)) for i in range(56)}
    assert {"Ari", "Tau", "Gem", "Cnc", "Leo", "Vir", "Lib", "Sco", "Sgr", "Cap", "Aqr", "Psc"} <= seen


def test_rise_set_in_local_day_baligrod():
    rs = rise_set(date(2026, 10, 17), 49.33, 22.28)
    assert rs["wschod"] or rs["zachod"]
    for v in rs.values():
        if v:
            local = v.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Warsaw"))
            assert local.date() == date(2026, 10, 17)


def test_calendar_day_and_modifier_limits():
    cd = calendar_day(date(2026, 10, 17), 49.33, 22.28)
    assert 0 <= cd.oswietlenie <= 1 and cd.typ_biodynamiczny in {"owoc", "korzen", "lisc", "kwiat", "nieprzypisany"}
    cfg = load_yaml("kalendarz.yaml")
    d, parts = calendar_modifier(cd, cfg)
    assert abs(d) <= cfg["amplituda_pkt"] and parts["eksperymentalny"] is True
    big = {**cfg, "amplituda_pkt": 50}
    assert abs(calendar_modifier(cd, big)[0]) <= cfg["amplituda_max_pkt"]
    zero = {**cfg, "amplituda_pkt": 0}
    assert calendar_modifier(cd, zero)[0] == 0
