"""Usługi wyższego poziomu: ranking, karta miejsca, 7 dni, kalendarz miesięczny, porównanie."""
from __future__ import annotations

import calendar as pycal
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from . import repo
from .astro import CalendarDay, calendar_day, calendar_modifier
from .config import load_yaml
from .model.combine import Score, combine
from .model.components import habitat, observations, weather
from .species import Species, all_species

HISTORY_DAYS = 45


@lru_cache(maxsize=512)
def _calendar_cached(day: date, lat_r: float, lon_r: float) -> CalendarDay:
    return calendar_day(day, lat_r, lon_r)


def cal_day(day: date, lat: float, lon: float) -> CalendarDay:
    # Zaokrąglenie do 0,1° — faza i gwiazdozbiór nie zależą od miejsca w regionie; wschód/zachód zmienia się o minuty.
    return _calendar_cached(day, round(lat, 1), round(lon, 1))


def calendar_json(cd: CalendarDay) -> dict:
    return {
        "data": cd.data.isoformat(), "faza": cd.faza, "faza_opis": cd.faza_opis, "kat_fazy_deg": cd.kat_fazy_deg,
        "oswietlenie": cd.oswietlenie,
        "fazy_glowne": [{"czas_utc": t.isoformat(), "faza": f} for t, f in cd.fazy_glowne],
        "wschod_utc": cd.wschod.isoformat() if cd.wschod else None,
        "zachod_utc": cd.zachod.isoformat() if cd.zachod else None,
        "typ_biodynamiczny": cd.typ_biodynamiczny, "gwiazdozbior_poludnie": cd.gwiazdozbior,
        "zmiany_typu": [{"czas_utc": t.isoformat(), "typ": x} for t, x in cd.zmiany_typu],
        "uwaga": "Typ dnia biodynamicznego: tradycja (metoda M. Thun, granice gwiazdozbiorów IAU). "
                 "Brak naukowego potwierdzenia wpływu na grzyby; źródła biodynamiczne nie opisują grzybów.",
    }


def get_species(sid: str) -> Species:
    sp = all_species().get(sid)
    if not sp:
        raise KeyError(sid)
    return sp


def _component_json(c) -> dict:
    return {"wynik": c.wynik, "kompletnosc": c.kompletnosc,
            "czynniki": [asdict(f) for f in c.czynniki], "uzasadnienie": c.uzasadnienie}


def score_json(s: Score) -> dict:
    return {
        "wynik": s.wynik, "podstawa": s.podstawa,
        "A": _component_json(s.A), "B": _component_json(s.B),
        "C": s.C, "D": s.D, "D_szczegoly": s.D_szczegoly,
        "bramki": [asdict(g) for g in s.bramki], "rekomendowane": s.rekomendowane,
        "kompletnosc": s.kompletnosc, "jakosc": s.jakosc, "uzasadnienie": s.uzasadnienie,
    }


def score_place(conn, ds: repo.Dataset, row: repo.StandRow, sp: Species, day: date, calendar_on: bool,
                cal: CalendarDay | None, weather_cache: dict | None = None) -> tuple[Score, dict]:
    cfg = load_yaml("model.yaml")
    A = habitat(row.stand, sp, cfg)
    wmeta: dict = {}
    if row.komorka_id:
        key = (row.komorka_id, day)
        if weather_cache is not None and key in weather_cache:
            daily, wmeta = weather_cache[key]
        else:
            daily, wmeta = repo.weather_series(conn, ds, row.komorka_id, day - timedelta(days=HISTORY_DAYS), day)
            if weather_cache is not None:
                weather_cache[key] = (daily, wmeta)
    else:
        daily = []
    B, ind, gates = weather(sp, daily, day, row.stand.wys_sr, cfg)
    obs = repo.observations_near(conn, ds, sp.id, row.lat, row.lon, day, cfg["obserwacje"]["promien_km"])
    C, c_reasons = observations(obs, cfg)
    if calendar_on and cal is not None:
        D, Dd = calendar_modifier(cal)
    else:
        D, Dd = 0.0, None
    prot = repo.protection_for(conn, ds, row.stand.id)
    bans = repo.bans_for(conn, ds, row.stand.id, day)
    s = combine(A, B, C, D, Dd, gates["susza"], prot, cfg)
    for b in bans:
        from .model.combine import Gate
        s.bramki.append(Gate("zakaz_wstepu", f"Zakaz wstępu: {b['rodzaj']} {b.get('opis') or ''}".strip()))
        s.rekomendowane = False
    s.uzasadnienie += c_reasons
    extra = {"wskazniki_pogody": _ind_json(ind), "pogoda_meta": wmeta, "ochrona": prot, "zakazy": bans,
             "liczba_obserwacji": len(obs)}
    return s, extra


def _ind_json(ind) -> dict:
    d = asdict(ind)
    d["data"] = ind.data.isoformat()
    d["opad_mm"] = {str(k): v for k, v in ind.opad_mm.items()}
    return d


def _place_header(row: repo.StandRow) -> dict:
    return {
        "id": row.stand.id, "nazwa": row.adres_lesny or f"Wydzielenie {row.stand.id}",
        "obszar_id": row.obszar_id, "lat": round(row.lat, 5), "lon": round(row.lon, 5),
        "odleglosc_km": round(row.odleglosc_km, 1) if row.odleglosc_km is not None else None,
        "odleglosc_opis": "w linii prostej (brak danych o drogach publicznych)",
        "powierzchnia_ha": round(row.powierzchnia_ha, 2),
        "gatunek_panujacy": row.stand.gatunek_panujacy, "typ_siedliskowy": row.stand.typ_siedliskowy,
        "wiek": row.stand.wiek,
    }


def access_status(conn, ds: repo.Dataset, prot: list[dict], bans: list[dict]) -> dict:
    """Status dostępu: jawnie odróżnia 'brak zakazu' od 'nie da się sprawdzić'."""
    cfg = load_yaml("model.yaml")
    zakaz_zbioru = [p for p in prot if p.get("rodzaj") in cfg["bramki"]["zakaz_rodzaje"]]
    inne = [p for p in prot if p.get("rodzaj") not in cfg["bramki"]["zakaz_rodzaje"]]
    have_bans = repo.ban_source_count(conn, ds) > 0
    notes = []
    if zakaz_zbioru:
        notes.append("Park narodowy: zbiór grzybów co do zasady zakazany poza miejscami wyznaczonymi przez dyrektora parku.")
    for p in inne:
        if p.get("rodzaj") == "rezerwat":
            notes.append(f"Rezerwat {p.get('nazwa') or ''}: zasady zbioru wynikają z aktu ustanawiającego — sprawdź przed wyjazdem.")
        else:
            notes.append(f"{p.get('nazwa') or p.get('rodzaj')}: forma ochrony zwykle nie zakazuje zbioru — sprawdź akt.")
    if bans:
        notes.append("Obowiązuje zakaz wstępu do lasu.")
    elif not have_bans:
        notes.append("Statusu czasowych zakazów wstępu (pożarowe, prace leśne, ASF, polowania) NIE DA SIĘ SPRAWDZIĆ — "
                     "brak danych w aplikacji. Sprawdź komunikaty nadleśnictwa.")
    notes.append("Granice form ochrony z Geoserwisu GDOŚ nie są prawnym ustaleniem ich przebiegu.")
    notes.append("Unikaj upraw leśnych do 4 m wysokości i ostoi zwierząt (wstęp zabroniony).")
    return {
        "zakaz_zbioru": bool(zakaz_zbioru), "zakaz_wstepu": bool(bans),
        "zakazy_wstepu_sprawdzalne": have_bans, "formy_ochrony": prot, "zakazy": bans, "uwagi": notes,
        "las_prywatny_uwaga": "Jeśli to las prywatny, właściciel może ograniczyć wstęp.",
    }


def ranking(conn, ds: repo.Dataset, sp: Species, lat: float, lon: float, radius_km: float, day: date,
            calendar_on: bool, limit: int = 50, include_excluded: bool = False) -> dict:
    rows = repo.stands_near(conn, ds, lat, lon, radius_km)
    cal = cal_day(day, lat, lon)
    wc: dict = {}
    items, excluded = [], 0
    for row in rows:
        s, extra = score_place(conn, ds, row, sp, day, calendar_on, cal, wc)
        if not s.rekomendowane:
            excluded += 1
            if not include_excluded:
                continue
        items.append({**_place_header(row), **score_json(s),
                      "pogoda": {"komorka_id": extra["pogoda_meta"].get("komorka_id"),
                                 "opad_7d_mm": extra["wskazniki_pogody"]["opad_mm"].get("7"),
                                 "sklad_typow": extra["wskazniki_pogody"]["sklad_typow"]}})
    items.sort(key=lambda x: (x["wynik"] is None, -(x["wynik"] or 0)))
    return {"miejsca": items[:limit], "liczba_ocenionych": len(rows), "wykluczone": excluded,
            "kalendarz": calendar_json(cal) if calendar_on else None}


def place_card(conn, ds: repo.Dataset, sp: Species, sid: int, day: date, calendar_on: bool,
               lat: float | None = None, lon: float | None = None) -> dict | None:
    row = repo.stand_by_id(conn, ds, sid, lat, lon)
    if not row:
        return None
    cal = cal_day(day, row.lat, row.lon)
    s, extra = score_place(conn, ds, row, sp, day, calendar_on, cal)
    terr = {"wys_sr_m": row.stand.wys_sr, "wys_min_m": row.wys_min, "wys_max_m": row.wys_max,
            "nachylenie_sr_deg": row.stand.nachylenie_sr, "nachylenie_max_deg": row.nachylenie_max,
            "ekspozycja": row.ekspozycja,
            "uwaga": "Wysokość z Copernicus DEM (model powierzchni z koronami drzew) — zawyżona w lesie."}
    geo = repo.stand_geojson(conn, ds, [sid]).get(sid)
    return {
        **_place_header(row), **score_json(s),
        "geometria": geo,
        "drzewostan": {"gatunek_panujacy": row.stand.gatunek_panujacy, "udzial_gatunkow": row.stand.udzial_gatunkow,
                       "wiek": row.stand.wiek, "typ_siedliskowy": row.stand.typ_siedliskowy, "gleba": row.stand.gleba,
                       "pochodzenie": row.pochodzenie,
                       "import_utc": row.imported_at.isoformat() if row.imported_at else None},
        "teren": terr,
        "pogoda": {**extra["wskazniki_pogody"], **{k: (v.isoformat() if isinstance(v, datetime) else v)
                                                  for k, v in extra["pogoda_meta"].items()},
                   "uwaga": "Wartości dla komórki siatki pogodowej (ok. 9–11 km), nie pomiar w tym lesie."},
        "dostep": access_status(conn, ds, extra["ochrona"], extra["zakazy"]),
        "dojazd": {"odleglosc_km": round(row.odleglosc_km, 1) if row.odleglosc_km is not None else None,
                   "opis": "Odległość w linii prostej. Brak danych o drogach publicznych i parkingach "
                           "(BDOT10k/OSM niedostępne) — nie wskazujemy dojazdu ani parkingu. "
                           "Nie wjeżdżaj na drogi leśne bez potwierdzenia, że ruch jest dopuszczony.",
                   "nachylenie_sr_deg": row.stand.nachylenie_sr},
        "kalendarz": calendar_json(cal),
    }


def seven_days(conn, ds: repo.Dataset, sp: Species, sid: int, start: date, calendar_on: bool) -> dict | None:
    row = repo.stand_by_id(conn, ds, sid)
    if not row:
        return None
    days = []
    for k in range(7):
        d = start + timedelta(days=k)
        cal = cal_day(d, row.lat, row.lon)
        s, extra = score_place(conn, ds, row, sp, d, calendar_on, cal)
        ind = extra["wskazniki_pogody"]
        days.append({"data": d.isoformat(), "wynik": s.wynik, "rekomendowane": s.rekomendowane,
                     "jakosc": s.jakosc, "A": s.A.wynik, "B": s.B.wynik, "C": s.C, "D": s.D,
                     "bramki": [g.opis for g in s.bramki], "powody": s.B.uzasadnienie[:4],
                     "typy_danych": ind["sklad_typow"], "faza": cal.faza_opis,
                     "typ_biodynamiczny": cal.typ_biodynamiczny})
    scored = [x for x in days if x["wynik"] is not None and x["rekomendowane"]]
    if not scored:
        verdict = {"decyzja": "brak_rekomendacji",
                   "opis": "W najbliższych 7 dniach brak dnia spełniającego warunki (lub brak danych)."}
    else:
        best = max(scored, key=lambda x: x["wynik"])
        today = days[0]
        if best["data"] == today["data"] or (today["wynik"] or 0) >= best["wynik"] - 5:
            verdict = {"decyzja": "dzis", "dzien": today["data"],
                       "opis": f"Dziś wskaźnik {today['wynik']:.0f}; w kolejnych dniach nie będzie wyraźnie lepiej."}
        else:
            verdict = {"decyzja": "poczekaj", "dzien": best["data"],
                       "opis": f"Lepiej poczekać do {best['data']}: wskaźnik {best['wynik']:.0f} "
                               f"wobec {today['wynik'] if today['wynik'] is not None else 'brak'} dziś."}
    verdict["uwaga"] = "Dni prognozy mają mniejszą pewność; prognoza może się zmienić."
    return {"miejsce": _place_header(row), "dni": days, "werdykt": verdict}


def month_calendar(conn, ds: repo.Dataset, sp: Species, year: int, month: int, lat: float, lon: float,
                   sid: int | None = None) -> dict:
    row = repo.stand_by_id(conn, ds, sid) if sid else None
    n = pycal.monthrange(year, month)[1]
    out = []
    wc: dict = {}
    for d in range(1, n + 1):
        day = date(year, month, d)
        cd = cal_day(day, lat, lon)
        entry = {"data": day.isoformat(), "faza": cd.faza, "faza_opis": cd.faza_opis, "oswietlenie": cd.oswietlenie,
                 "typ_biodynamiczny": cd.typ_biodynamiczny, "wynik": None, "opad_mm": None, "temp_sr_c": None,
                 "typ_danych": None}
        if row:
            s, extra = score_place(conn, ds, row, sp, day, False, None, wc)
            entry["wynik"] = s.wynik
            entry["wynik_z_kalendarzem"] = (round(max(0, min(100, s.wynik + calendar_modifier(cd)[0])), 1)
                                            if s.wynik is not None else None)
            ind = extra["wskazniki_pogody"]
            entry["temp_sr_c"] = ind["temp_sr_dzien_c"]
            daily = wc.get((row.komorka_id, day), ([], {}))[0]
            today_w = next((x for x in daily if x.data == day), None)
            if today_w:
                entry["opad_mm"], entry["typ_danych"] = today_w.opad_mm, today_w.typ
        out.append(entry)
    return {"rok": year, "miesiac": month, "dni": out,
            "uwaga": "Typ dnia biodynamicznego i faza Księżyca — tradycja, oznaczone jako eksperymentalne."}


def compare(conn, ds: repo.Dataset, sp: Species, ids: list[int], day: date, calendar_on: bool) -> list[dict]:
    out = []
    for sid in ids:
        row = repo.stand_by_id(conn, ds, sid)
        if not row:
            continue
        cal = cal_day(day, row.lat, row.lon)
        s, extra = score_place(conn, ds, row, sp, day, calendar_on, cal)
        out.append({**_place_header(row), **score_json(s),
                    "opad_14d_mm": extra["wskazniki_pogody"]["opad_mm"].get("14"),
                    "temp_sr_7_c": extra["wskazniki_pogody"]["temp_sr_7_c"]})
    return out
