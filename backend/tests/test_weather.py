from datetime import date, datetime, timedelta, timezone

import pytest

from grzyby.weather.aggregate import (DailyWeather, compute_indicators, hourly_to_daily, local_day_hours,
                                      rain_events)
from grzyby.weather.openmeteo import BadResponse, cell_center, parse_hourly

UTC = timezone.utc


def hours(start_utc: datetime, n: int) -> list[datetime]:
    return [start_utc + timedelta(hours=i) for i in range(n)]


def test_local_day_lengths_on_dst_changes_2026():
    assert local_day_hours(date(2026, 3, 29)) == 23   # przejście na czas letni
    assert local_day_hours(date(2026, 10, 25)) == 25  # powrót na czas zimowy
    assert local_day_hours(date(2026, 10, 17)) == 24


def test_local_day_boundaries_summer_time():
    # 2026-07-01 lokalnie (CEST, UTC+2) = 2026-06-30 22:00 UTC .. 2026-07-01 21:59 UTC
    t = hours(datetime(2026, 6, 30, 22, tzinfo=UTC), 24)
    days = hourly_to_daily(t, {"opad_mm": [1.0] * 24, "temp_c": list(range(24))}, "reanaliza", 22)
    assert [d.data for d in days] == [date(2026, 7, 1)]
    assert days[0].opad_mm == 24.0 and days[0].temp_min_c == 0 and days[0].temp_max_c == 23


def test_hour_at_22_utc_belongs_to_next_local_day_in_summer():
    t = [datetime(2026, 7, 1, 21, tzinfo=UTC), datetime(2026, 7, 1, 22, tzinfo=UTC)]
    days = hourly_to_daily(t, {"opad_mm": [5.0, 7.0]}, "prognoza", 1)
    assert {d.data: d.godzin for d in days} == {date(2026, 7, 1): 1, date(2026, 7, 2): 1}


@pytest.mark.parametrize("day,start_utc,n", [
    (date(2026, 3, 29), datetime(2026, 3, 28, 23, tzinfo=UTC), 23),
    (date(2026, 10, 25), datetime(2026, 10, 24, 22, tzinfo=UTC), 25),
])
def test_dst_day_sum_uses_all_hours(day, start_utc, n):
    t = hours(start_utc - timedelta(hours=3), n + 6)  # z zapasem po obu stronach
    days = {d.data: d for d in hourly_to_daily(t, {"opad_mm": [1.0] * (n + 6)}, "reanaliza", 22)}
    assert days[day].godzin == n
    assert days[day].opad_mm == float(n)


def test_incomplete_day_sum_is_none_not_zero():
    t = hours(datetime(2026, 7, 31, 22, tzinfo=UTC), 24)
    precip = [0.5] * 24
    precip[5] = None
    d = hourly_to_daily(t, {"opad_mm": precip, "temp_c": [10.0] * 24}, "reanaliza", 22)[0]
    assert d.opad_mm is None and d.temp_sr_c == 10.0


def make_series(precip: list[float], end: date, tmin=5.0, et0=1.0) -> list[DailyWeather]:
    n = len(precip)
    return [DailyWeather(data=end - timedelta(days=n - 1 - i), typ="reanaliza", godzin=24, opad_mm=p,
                         temp_min_c=tmin, temp_sr_c=tmin + 6, temp_max_c=tmin + 12, wilg_powietrza_pct=80,
                         et0_mm=et0) for i, p in enumerate(precip)]


def test_precipitation_sums_known_sequence():
    precip = [0.0] * 30
    precip[-1], precip[-3], precip[-7], precip[-14], precip[-30] = 1.0, 2.0, 4.0, 8.0, 16.0
    end = date(2026, 9, 30)
    ind = compute_indicators(make_series(precip, end), end, 1.0)
    assert ind.opad_mm == {3: 3.0, 7: 7.0, 14: 15.0, 30: 31.0}
    assert ind.dni_z_opadem_30 == 5 and ind.dni_z_opadem_14 == 4
    assert ind.najdluzszy_okres_bez_opadu_30 == 15   # dni 2..16 (indeksy 1..15)
    assert ind.dni_od_ostatniego_opadu == 0
    assert ind.et0_14_mm == 14.0 and ind.bilans_14_mm == 1.0
    assert ind.sklad_typow == {"reanaliza": 30}


def test_incomplete_window_gives_none():
    end = date(2026, 9, 30)
    series = make_series([1.0] * 10, end)
    ind = compute_indicators(series, end, 1.0)
    assert ind.opad_mm[7] == 7.0 and ind.opad_mm[14] is None and ind.opad_mm[30] is None
    assert ind.dni_z_opadem_30 is None


def test_frost_count():
    end = date(2026, 10, 10)
    s = make_series([0.0] * 30, end, tmin=3.0)
    s[-1].temp_min_c = -2.0
    s[-4].temp_min_c = -0.5
    assert compute_indicators(s, end, 1.0).przymrozki_7 == 2


def test_rain_events_merge_consecutive_days():
    end = date(2026, 9, 30)
    precip = [0.0] * 31
    precip[-5], precip[-6] = 10.0, 8.0   # epizod 18 mm, zakończony 4 dni temu
    precip[-20] = 3.0
    assert rain_events(make_series(precip, end), end, 15.0) == [(4, 18.0)]


def test_parse_hourly_rejects_missing_variable():
    payload = {"hourly": {"time": [0, 3600], "precipitation": [0.1, 0.2]}}
    times, vals = parse_hourly(payload, {"opad_mm": "precipitation"})
    assert times[1] == datetime(1970, 1, 1, 1, tzinfo=UTC) and vals["opad_mm"] == [0.1, 0.2]
    with pytest.raises(BadResponse):
        parse_hourly(payload, {"opad_mm": "precipitation", "temp_c": "temperature_2m"})


def test_cell_center():
    assert cell_center(49.3326, 22.2836, 0.1) == (49.35, 22.25)
