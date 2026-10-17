"""Agregacja pogody: godziny UTC → doby lokalne (Europe/Warsaw) → wskaźniki dla modelu.

Funkcje są czyste (bez sieci i bazy), żeby dało się je testować na znanych ciągach.
Brak danych zostaje None — nie interpolujemy i nie wstawiamy zer.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")

SUM_VARS = {"opad_mm", "et0_mm"}
MEAN_VARS = {"wilg_powietrza_pct", "wilg_gleby_m3m3", "temp_gleby_c"}


@dataclass
class DailyWeather:
    data: date
    typ: str                        # stacja | reanaliza | prognoza
    godzin: int
    opad_mm: float | None = None
    temp_min_c: float | None = None
    temp_sr_c: float | None = None
    temp_max_c: float | None = None
    wilg_powietrza_pct: float | None = None
    wilg_gleby_m3m3: float | None = None
    temp_gleby_c: float | None = None
    et0_mm: float | None = None


def local_day_hours(day: date, tz: ZoneInfo = WARSAW) -> int:
    """Liczba godzin w dobie lokalnej (23 przy przejściu na czas letni, 25 przy powrocie)."""
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    nxt = start + timedelta(days=1)
    nxt = datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz)
    return int((nxt.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds() // 3600)


def hourly_to_daily(
    times_utc: list[datetime],
    values: dict[str, list[float | None]],
    typ: str,
    min_hours: int,
    tz: ZoneInfo = WARSAW,
) -> list[DailyWeather]:
    """Grupuje godziny (znacznik = początek godziny, UTC) w doby lokalne.

    Doba, w której brakuje godzin (poniżej min_hours lub poniżej rzeczywistej długości doby przy sumach),
    dostaje None dla zmiennych sumowanych — suma z niepełnej doby byłaby zaniżona.
    """
    buckets: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    hours: Counter = Counter()
    for i, t in enumerate(times_utc):
        if t.tzinfo is None:
            raise ValueError("Znaczniki czasu muszą mieć strefę (UTC)")
        d = t.astimezone(tz).date()
        hours[d] += 1
        for var, arr in values.items():
            v = arr[i]
            if v is not None:
                buckets[d][var].append(float(v))
    out = []
    for d in sorted(hours):
        n_expected = local_day_hours(d, tz)
        dw = DailyWeather(data=d, typ=typ, godzin=hours[d])
        b = buckets[d]
        if hours[d] < min_hours:
            out.append(dw)
            continue
        for var in SUM_VARS:
            vals = b.get(var, [])
            setattr(dw, var, round(sum(vals), 2) if len(vals) == n_expected else None)
        t = b.get("temp_c", [])
        if len(t) >= min_hours:
            dw.temp_min_c, dw.temp_max_c, dw.temp_sr_c = min(t), max(t), round(mean(t), 2)
        for var in MEAN_VARS:
            vals = b.get(var, [])
            setattr(dw, var, round(mean(vals), 3) if len(vals) >= min_hours else None)
        out.append(dw)
    return out


@dataclass
class Indicators:
    data: date
    opad_mm: dict[int, float | None] = field(default_factory=dict)   # {3: .., 7: .., 14: .., 30: ..}
    dni_z_opadem_14: int | None = None
    dni_z_opadem_30: int | None = None
    najdluzszy_okres_bez_opadu_30: int | None = None
    dni_od_ostatniego_opadu: int | None = None
    temp_min_7_c: float | None = None
    temp_sr_7_c: float | None = None
    temp_max_7_c: float | None = None
    temp_sr_dzien_c: float | None = None
    przymrozki_7: int | None = None
    wilg_powietrza_7_pct: float | None = None
    wilg_gleby_dzien: float | None = None
    temp_gleby_dzien_c: float | None = None
    et0_14_mm: float | None = None
    bilans_14_mm: float | None = None
    sklad_typow: dict[str, int] = field(default_factory=dict)       # ile dni z reanalizy / prognozy w oknie 30 d


def _window(series: dict[date, DailyWeather], end: date, days: int) -> list[DailyWeather | None]:
    return [series.get(end - timedelta(days=k)) for k in range(days - 1, -1, -1)]


def _complete_sum(win: list[DailyWeather | None], attr: str) -> float | None:
    vals = [getattr(d, attr) if d else None for d in win]
    if any(v is None for v in vals):
        return None
    return round(sum(vals), 2)


def compute_indicators(daily: list[DailyWeather], day: date, wet_threshold_mm: float,
                       windows: tuple[int, ...] = (3, 7, 14, 30), frost_c: float = 0.0) -> Indicators:
    """Wskaźniki dla dnia `day` (włącznie) na podstawie ciągu dobowego. Okna niepełne → None."""
    s = {d.data: d for d in daily}
    ind = Indicators(data=day)
    for w in windows:
        ind.opad_mm[w] = _complete_sum(_window(s, day, w), "opad_mm")
    w30 = _window(s, day, 30)
    p30 = [d.opad_mm if d else None for d in w30]
    if all(v is not None for v in p30):
        wet = [v >= wet_threshold_mm for v in p30]
        ind.dni_z_opadem_30 = sum(wet)
        ind.dni_z_opadem_14 = sum(wet[-14:])
        run = best = 0
        for x in wet:
            run = 0 if x else run + 1
            best = max(best, run)
        ind.najdluzszy_okres_bez_opadu_30 = best
        last_wet = max((i for i, x in enumerate(wet) if x), default=None)
        ind.dni_od_ostatniego_opadu = (29 - last_wet) if last_wet is not None else None
    w7 = [d for d in _window(s, day, 7) if d]
    if len(w7) == 7 and all(d.temp_min_c is not None for d in w7):
        ind.temp_min_7_c = min(d.temp_min_c for d in w7)
        ind.temp_max_7_c = max(d.temp_max_c for d in w7)
        ind.temp_sr_7_c = round(mean(d.temp_sr_c for d in w7), 2)
        ind.przymrozki_7 = sum(d.temp_min_c < frost_c for d in w7)
    if len(w7) == 7 and all(d.wilg_powietrza_pct is not None for d in w7):
        ind.wilg_powietrza_7_pct = round(mean(d.wilg_powietrza_pct for d in w7), 1)
    today = s.get(day)
    if today:
        ind.temp_sr_dzien_c = today.temp_sr_c
        ind.wilg_gleby_dzien = today.wilg_gleby_m3m3
        ind.temp_gleby_dzien_c = today.temp_gleby_c
    w14 = _window(s, day, 14)
    ind.et0_14_mm = _complete_sum(w14, "et0_mm")
    if ind.opad_mm.get(14) is not None and ind.et0_14_mm is not None:
        ind.bilans_14_mm = round(ind.opad_mm[14] - ind.et0_14_mm, 2)
    ind.sklad_typow = dict(Counter(d.typ for d in w30 if d))
    return ind


def rain_events(daily: list[DailyWeather], day: date, threshold_mm: float, lookback: int = 30) -> list[tuple[int, float]]:
    """Istotne opady przed dniem `day`: lista (ile dni temu, mm). Opady w dniach kolejnych są sumowane w epizod."""
    s = {d.data: d for d in daily}
    events: list[tuple[int, float]] = []
    acc, acc_end = 0.0, None
    for k in range(lookback, -1, -1):
        d = s.get(day - timedelta(days=k))
        # Doba bez danych przerywa epizod (nie liczymy jej jako opadu); kompletność okna ocenia compute_indicators.
        p = d.opad_mm if d and d.opad_mm is not None else 0.0
        if p >= 1.0:
            acc += p
            acc_end = k
        elif acc:
            if acc >= threshold_mm:
                events.append((acc_end, round(acc, 1)))
            acc = 0.0
    if acc >= threshold_mm:
        events.append((acc_end, round(acc, 1)))
    return events
