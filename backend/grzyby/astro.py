"""Księżyc (faza, oświetlenie, kwadry, wschód/zachód) i typy dni biodynamicznych (metoda M. Thun, granice IAU).

Efemerydy: JPL DE421 z pakietu skyfield-data (bez pobierania z sieci). Czas wejścia/wyjścia: UTC;
doby lokalne liczone w Europe/Warsaw.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from skyfield import almanac
from skyfield.api import load_constellation_map, wgs84
from skyfield.framelib import ecliptic_frame

from .config import load_yaml

WARSAW = ZoneInfo("Europe/Warsaw")
PHASE_NAMES = ["now", "pierwsza_kwadra", "pelnia", "ostatnia_kwadra"]
PHASE_LABELS = {
    "now": "nów", "sierp_przybywajacy": "sierp przybywający", "pierwsza_kwadra": "pierwsza kwadra",
    "garb_przybywajacy": "Księżyc garbaty przybywający", "pelnia": "pełnia", "garb_ubywajacy": "Księżyc garbaty ubywający",
    "ostatnia_kwadra": "ostatnia kwadra", "sierp_ubywajacy": "sierp ubywający",
}


@lru_cache
def _eph():
    from skyfield.api import Loader
    from skyfield_data import get_skyfield_data_path
    load = Loader(get_skyfield_data_path(), expire=False)
    return load.timescale(builtin=True), load("de421.bsp")


@lru_cache
def _constellation_of():
    return load_constellation_map()


def _t(dt: datetime):
    ts, _ = _eph()
    return ts.from_datetime(dt.astimezone(timezone.utc))


def phase_angle_deg(dt: datetime) -> float:
    """Różnica długości ekliptycznych Księżyc − Słońce (0 = nów, 180 = pełnia)."""
    _, eph = _eph()
    return float(almanac.moon_phase(eph, _t(dt)).degrees)


def illumination(dt: datetime) -> float:
    _, eph = _eph()
    t = _t(dt)
    earth = eph["earth"]
    return float(earth.at(t).observe(eph["moon"]).apparent().fraction_illuminated(eph["sun"]))


def phase_name(angle: float, window_deg: float = 6.0) -> str:
    """Nazwa fazy; fazy główne w oknie ±window_deg (ok. ±12 h) wokół momentu astronomicznego."""
    for i, center in enumerate((0, 90, 180, 270)):
        if min(abs(angle - center), 360 - abs(angle - center)) <= window_deg:
            return PHASE_NAMES[i]
    if angle < 90:
        return "sierp_przybywajacy"
    if angle < 180:
        return "garb_przybywajacy"
    if angle < 270:
        return "garb_ubywajacy"
    return "sierp_ubywajacy"


def principal_phases(start: datetime, end: datetime) -> list[tuple[datetime, str]]:
    ts, eph = _eph()
    times, codes = almanac.find_discrete(_t(start), _t(end), almanac.moon_phases(eph))
    return [(t.utc_datetime(), PHASE_NAMES[int(c)]) for t, c in zip(times, codes)]


def rise_set(day: date, lat: float, lon: float) -> dict[str, datetime | None]:
    """Wschód i zachód Księżyca w dobie lokalnej (Europe/Warsaw); None, gdy zjawisko nie zachodzi."""
    _, eph = _eph()
    start = datetime(day.year, day.month, day.day, tzinfo=WARSAW)
    end = datetime((day + timedelta(days=1)).year, (day + timedelta(days=1)).month, (day + timedelta(days=1)).day, tzinfo=WARSAW)
    topos = wgs84.latlon(lat, lon)
    observer = eph["earth"] + topos
    out: dict[str, datetime | None] = {"wschod": None, "zachod": None}
    rt, ry = almanac.find_risings(observer, eph["moon"], _t(start), _t(end))
    st, sy = almanac.find_settings(observer, eph["moon"], _t(start), _t(end))
    if len(rt) and ry[0]:
        out["wschod"] = rt[0].utc_datetime()
    if len(st) and sy[0]:
        out["zachod"] = st[0].utc_datetime()
    return out


def moon_constellation(dt: datetime) -> str:
    """Skrót IAU gwiazdozbioru, w którym widać Księżyc (pozycja geocentryczna, układ daty)."""
    _, eph = _eph()
    pos = eph["earth"].at(_t(dt)).observe(eph["moon"]).apparent()
    return str(_constellation_of()(pos))


def sun_constellation(dt: datetime) -> str:
    _, eph = _eph()
    return str(_constellation_of()(eph["earth"].at(_t(dt)).observe(eph["sun"]).apparent()))


def moon_ecliptic_lon(dt: datetime) -> float:
    _, eph = _eph()
    lat, lon, _ = eph["earth"].at(_t(dt)).observe(eph["moon"]).apparent().frame_latlon(ecliptic_frame)
    return float(lon.degrees)


def biodynamic_type(constellation: str) -> str:
    return load_yaml("kalendarz.yaml")["gwiazdozbiory"].get(constellation, "nieprzypisany")


@dataclass
class CalendarDay:
    data: date
    faza: str
    faza_opis: str
    kat_fazy_deg: float
    oswietlenie: float
    fazy_glowne: list[tuple[datetime, str]]
    wschod: datetime | None
    zachod: datetime | None
    typ_biodynamiczny: str           # przeważający w dobie lokalnej
    gwiazdozbior: str                # o lokalnym południu
    zmiany_typu: list[tuple[datetime, str]]


def calendar_day(day: date, lat: float, lon: float) -> CalendarDay:
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=WARSAW)
    start = datetime(day.year, day.month, day.day, tzinfo=WARSAW)
    # Typ dnia: przeważający typ w 24 próbkach godzinowych doby lokalnej + chwile zmian.
    samples = []
    for h in range(24):
        t = (start.astimezone(timezone.utc) + timedelta(hours=h, minutes=30))
        samples.append((t, biodynamic_type(moon_constellation(t))))
    changes = [(t, typ) for (t0, p), (t, typ) in zip(samples, samples[1:]) if typ != p]
    dominant = Counter(typ for _, typ in samples).most_common(1)[0][0]
    ang = phase_angle_deg(noon)
    ph = principal_phases(start, start + timedelta(days=1))
    # Faza główna w tej dobie ma pierwszeństwo przed nazwą z kąta.
    name = ph[0][1] if ph else phase_name(ang)
    rs = rise_set(day, lat, lon)
    return CalendarDay(day, name, PHASE_LABELS[name], round(ang, 1), round(illumination(noon), 3), ph,
                       rs["wschod"], rs["zachod"], dominant, moon_constellation(noon), changes)


def calendar_modifier(cd: CalendarDay, cfg: dict | None = None) -> tuple[float, dict]:
    """Jeden wspólny modyfikator D (punkty) z fazy i biodynamiki; ograniczony do ±amplituda_max."""
    cfg = cfg or load_yaml("kalendarz.yaml")
    amp = min(abs(float(cfg["amplituda_pkt"])), float(cfg["amplituda_max_pkt"]))
    sk = cfg["skladowe"]
    vf = float(sk["faza"]["wartosci"][cd.faza])
    vb = float(sk["biodynamika"]["wartosci"][cd.typ_biodynamiczny])
    wsum = sk["faza"]["waga"] + sk["biodynamika"]["waga"]
    combined = (sk["faza"]["waga"] * vf + sk["biodynamika"]["waga"] * vb) / wsum if wsum else 0.0
    combined = max(-1.0, min(1.0, combined))
    return round(combined * amp, 2), {"faza": vf, "biodynamika": vb, "laczna": round(combined, 3), "amplituda": amp,
                                       "eksperymentalny": bool(cfg.get("eksperymentalny", True))}
