"""Składowe wskaźnika rekomendacji: A (siedlisko), B (pogoda i sezon), C (obserwacje).

Każda składowa zwraca wynik 0–100 (lub None przy braku danych), rozbicie na czynniki, kompletność
wejść (0–1) i uzasadnienia w punktach. Wszystkie progi pochodzą z config/model.yaml i species/*.yaml.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import load_yaml
from ..species import Species
from ..weather.aggregate import DailyWeather, Indicators, compute_indicators, rain_events


@dataclass
class Factor:
    nazwa: str
    wartosc: float | None          # 0–1; None = brak danych
    waga: float
    opis: str


@dataclass
class Component:
    wynik: float | None
    kompletnosc: float
    czynniki: list[Factor] = field(default_factory=list)
    uzasadnienie: list[str] = field(default_factory=list)


def _weighted(factors: list[Factor]) -> tuple[float | None, float]:
    have = [f for f in factors if f.wartosc is not None]
    wsum = sum(f.waga for f in factors)
    if not have:
        return None, 0.0
    hw = sum(f.waga for f in have)
    return sum(f.wartosc * f.waga for f in have) / hw, hw / wsum


def trapezoid(x: float, lo: float, opt_lo: float, opt_hi: float, hi: float, edge: float = 0.0) -> float:
    if x <= lo or x >= hi:
        return edge if x == lo or x == hi else 0.0
    if x < opt_lo:
        return edge + (1 - edge) * (x - lo) / (opt_lo - lo)
    if x <= opt_hi:
        return 1.0
    return edge + (1 - edge) * (hi - x) / (hi - opt_hi)


# ---------------------------------------------------------------- A: siedlisko
@dataclass
class Stand:
    id: int
    gatunek_panujacy: str | None
    udzial_gatunkow: dict[str, float] | None
    wiek: int | None
    typ_siedliskowy: str | None
    gleba: str | None
    wys_sr: float | None
    nachylenie_sr: float | None


def _soil_traits(gleba: str) -> dict | None:
    g = gleba.strip().lower()
    for t in load_yaml("gleby.yaml")["typy"]:
        if g.startswith(t["prefiks"]):
            return t
    return None


def habitat(stand: Stand, sp: Species, cfg: dict | None = None) -> Component:
    cfg = (cfg or load_yaml("model.yaml"))["siedlisko"]
    w = cfg["wagi"]
    names = {k: v["nazwa"] for k, v in load_yaml("slowniki.yaml")["drzewa"].items()}
    reasons: list[str] = []
    factors: list[Factor] = []
    completeness_penalty = 1.0

    # drzewa partnerskie
    if sp.typ_troficzny.wartosc == "mikoryzowy":
        strength = {p.drzewo: cfg["sila_zwiazku"][p.sila] for p in sp.drzewa_partnerskie}
        shares = stand.udzial_gatunkow
        if not shares and stand.gatunek_panujacy:
            shares = {stand.gatunek_panujacy: cfg["tylko_gatunek_panujacy_udzial"]}
            completeness_penalty = 0.85
            reasons.append("Znany tylko gatunek panujący — udział drzew partnerskich przyjęty orientacyjnie.")
        if shares:
            s = sum(share * strength.get(tree, 0.0) for tree, share in shares.items())
            v = min(1.0, s / cfg["udzial_nasycenia"])
            partners = [f"{names.get(t, t)} {round(share * 100)}%" for t, share in
                        sorted(shares.items(), key=lambda x: -x[1]) if t in strength]
            factors.append(Factor("drzewa", v, w["drzewa"],
                                  "drzewa partnerskie: " + (", ".join(partners) if partners else "brak")))
            reasons.append(f"Drzewa partnerskie: {', '.join(partners)}." if partners
                           else "Brak drzew partnerskich gatunku w drzewostanie.")
        else:
            factors.append(Factor("drzewa", None, w["drzewa"], "brak danych o składzie drzewostanu"))
            reasons.append("Brak danych o składzie drzewostanu.")
    # (saprotrofy: składnik drzew pomijany — wagi pozostałych normalizują się same)

    # typ siedliskowy
    tsl = stand.typ_siedliskowy
    if tsl:
        if tsl in sp.typy_siedliskowe.preferowane:
            v, d = cfg["typ_siedliskowy"]["preferowany"], f"typ siedliskowy {tsl} — preferowany"
        elif tsl in sp.typy_siedliskowe.dopuszczalne:
            v, d = cfg["typ_siedliskowy"]["dopuszczalny"], f"typ siedliskowy {tsl} — dopuszczalny"
        else:
            v, d = cfg["typ_siedliskowy"]["inny"], f"typ siedliskowy {tsl} — nietypowy dla gatunku"
        factors.append(Factor("typ_siedliskowy", v, w["typ_siedliskowy"], d))
        reasons.append(d[0].upper() + d[1:] + ".")
    else:
        factors.append(Factor("typ_siedliskowy", None, w["typ_siedliskowy"], "brak typu siedliskowego"))

    # wiek
    if stand.wiek is not None and sp.wiek_drzewostanu:
        wd = sp.wiek_drzewostanu
        if stand.wiek < wd.min_lat:
            v = cfg["wiek_ponizej_min"]
        elif stand.wiek < wd.optimum_lat[0]:
            v = cfg["wiek_ponizej_optimum"]
        elif stand.wiek <= wd.optimum_lat[1]:
            v = 1.0
        else:
            v = cfg["wiek_powyzej_optimum"]
        factors.append(Factor("wiek", v, w["wiek"], f"wiek drzewostanu {stand.wiek} lat"))
    else:
        factors.append(Factor("wiek", None, w["wiek"], "brak wieku drzewostanu"))

    # gleba
    traits = _soil_traits(stand.gleba) if stand.gleba else None
    if traits:
        ok = traits["odczyn"] in sp.gleba.odczyn and traits["zyznosc"] in sp.gleba.zyznosc
        v = cfg["gleba_zgodna"] if ok else cfg["gleba_niezgodna"]
        factors.append(Factor("gleba", v, w["gleba"], f"gleba: {stand.gleba} ({'zgodna' if ok else 'mniej typowa'})"))
    else:
        desc = "brak danych glebowych" if not stand.gleba else f"gleba '{stand.gleba}' bez przełożenia w config/gleby.yaml"
        factors.append(Factor("gleba", None, w["gleba"], desc))
        reasons.append("Brak danych glebowych — obniżona kompletność.")

    # rzeźba terenu
    if stand.wys_sr is not None:
        inside = sp.wysokosc_npm.min_m <= stand.wys_sr <= sp.wysokosc_npm.max_m
        v = 1.0 if inside else cfg["teren_poza_zakresem_wysokosci"]
        d = f"wysokość ok. {round(stand.wys_sr)} m n.p.m. (DSM)"
        if stand.nachylenie_sr is not None and stand.nachylenie_sr > cfg["teren_nachylenie_trudne_deg"]:
            v *= cfg["teren_nachylenie_trudne_mnoznik"]
            d += f", strome zbocza {round(stand.nachylenie_sr)}°"
        factors.append(Factor("teren", v, w["teren"], d))
    else:
        factors.append(Factor("teren", None, w["teren"], "brak danych o rzeźbie terenu"))

    # Drzewa partnerskie są czynnikiem ograniczającym (mnożnik): bez gospodarza mikoryzowego inne cechy
    # siedliska nie mogą podnieść wyniku. Pozostałe czynniki — średnia ważona.
    trees = next((f for f in factors if f.nazwa == "drzewa"), None)
    others = [f for f in factors if f.nazwa != "drzewa"]
    score, _ = _weighted(others)
    _, comp = _weighted(factors)
    if score is not None and trees is not None and trees.wartosc is not None:
        score *= trees.wartosc
    return Component(None if score is None else round(score * 100, 1), round(comp * completeness_penalty, 3),
                     factors, reasons)


# ---------------------------------------------------------------- B: pogoda i sezon
def _doy(mmdd: str, year: int) -> date:
    m, d = map(int, mmdd.split("-"))
    return date(year, m, d)


def season_factor(sp: Species, day: date, altitude_m: float | None, edge: float) -> tuple[float, str]:
    s = sp.sezon
    shift = 0.0
    if altitude_m is not None:
        shift = max(0.0, (altitude_m - s.wysokosc_odniesienia_m) / 100.0 * s.poprawka_wysokosci_dni_na_100m)
    sh = timedelta(days=round(shift))
    start, end = _doy(s.start, day.year) + sh, _doy(s.koniec, day.year) - sh
    p0, p1 = _doy(s.szczyt[0], day.year) + sh, _doy(s.szczyt[1], day.year) - sh
    if p1 < p0:  # po przesunięciu szczyt się zamknął — zostaje jeden dzień w środku
        mid = p0 + (p1 - p0) / 2
        p0 = p1 = mid
    if day < start or day > end:
        return 0.0, f"poza sezonem (okno {start:%d.%m}–{end:%d.%m} z poprawką na wysokość)"
    if p0 <= day <= p1:
        return 1.0, f"szczyt sezonu ({p0:%d.%m}–{p1:%d.%m})"
    if day < p0:
        v = edge + (1 - edge) * (day - start).days / max(1, (p0 - start).days)
        return v, f"początek sezonu (szczyt od {p0:%d.%m})"
    v = edge + (1 - edge) * (end - day).days / max(1, (end - p1).days)
    return v, f"koniec sezonu (do {end:%d.%m})"


def _lag_window(sp: Species, t_mean: float) -> tuple[int, int] | None:
    for p in sp.pogoda.opoznienie_po_opadzie.progi:
        if p.t_sr_od <= t_mean < p.t_sr_do:
            return p.dni
    return None


def weather(sp: Species, daily: list[DailyWeather], day: date, altitude_m: float | None,
            cfg: dict | None = None) -> tuple[Component, Indicators, dict]:
    full = cfg or load_yaml("model.yaml")
    c = full["pogoda"]
    wcfg = load_yaml("pogoda.yaml")
    w = c["wagi"]
    pg = sp.pogoda
    ind = compute_indicators(daily, day, wcfg["prog_dnia_z_opadem_mm"], tuple(wcfg["okna_opadow_dni"]),
                             frost_c=pg.przymrozek.tmin_prog_c)
    reasons: list[str] = []
    factors: list[Factor] = []
    gates: dict = {"susza": False}

    season, sdesc = season_factor(sp, day, altitude_m, c["sezon_brzeg"])
    reasons.append(sdesc[0].upper() + sdesc[1:] + ".")

    p = ind.opad_mm.get(pg.opady.okno_dni)
    if p is not None:
        o = pg.opady
        if p < o.min_mm:
            v = 0.4 * p / o.min_mm
        elif p < o.optimum_mm[0]:
            v = 0.4 + 0.6 * (p - o.min_mm) / (o.optimum_mm[0] - o.min_mm)
        elif p <= o.optimum_mm[1]:
            v = 1.0
        else:
            v = max(0.8, 1.0 - 0.2 * (p - o.optimum_mm[1]) / o.optimum_mm[1])
        sus = pg.susza
        if ind.bilans_14_mm is not None and ind.bilans_14_mm < sus.bilans_14d_mm_kara_ponizej:
            span = sus.bilans_14d_mm_kara_ponizej - sus.bilans_14d_mm_bramka_ponizej
            k = max(c["kara_susza_mnoznik_min"], 1 - (sus.bilans_14d_mm_kara_ponizej - ind.bilans_14_mm) / span)
            v *= k
            reasons.append(f"Ujemny bilans wodny 14 dni: {ind.bilans_14_mm:.0f} mm (opad − ET₀).")
        if ind.dni_od_ostatniego_opadu is not None and ind.dni_od_ostatniego_opadu >= sus.dni_bez_opadu_kara_od:
            v *= 0.6
            reasons.append(f"{ind.dni_od_ostatniego_opadu} dni bez opadu ≥1 mm.")
        factors.append(Factor("wilgoc", v, w["wilgoc"], f"opad {pg.opady.okno_dni} dni: {p:.0f} mm"))
        reasons.append(f"Opad z {pg.opady.okno_dni} dni: {p:.0f} mm (optimum {o.optimum_mm[0]:.0f}–{o.optimum_mm[1]:.0f} mm).")
        if (ind.bilans_14_mm is not None and ind.bilans_14_mm < sus.bilans_14d_mm_bramka_ponizej) or (
                ind.najdluzszy_okres_bez_opadu_30 is not None
                and ind.najdluzszy_okres_bez_opadu_30 >= full["bramki"]["susza_najdluzszy_okres_bez_opadu_dni"]
                and (ind.dni_od_ostatniego_opadu or 0) >= sus.dni_bez_opadu_kara_od):
            gates["susza"] = True
    else:
        factors.append(Factor("wilgoc", None, w["wilgoc"], "brak pełnych danych opadowych"))
        reasons.append("Brak pełnych danych opadowych.")

    # opóźnienie po opadzie (zależne od temperatury)
    t = ind.temp_sr_7_c
    events = rain_events(daily, day, pg.opoznienie_po_opadzie.opad_istotny_mm)
    if t is not None and ind.opad_mm.get(30) is not None:
        win = _lag_window(sp, t)
        if win is None:
            v, d = 0.1, f"średnia temp. 7 dni {t:.1f}°C poza zakresem owocnikowania"
        elif not events:
            v, d = c["brak_epizodu_opadu"], f"brak opadu ≥{pg.opoznienie_po_opadzie.opad_istotny_mm:.0f} mm w 30 dniach"
        else:
            best, best_d = 0.0, ""
            for ago, mm in events:
                lo, hi = win
                if lo <= ago <= hi:
                    val = 1.0
                elif ago < lo:
                    val = 0.3 + 0.5 * ago / lo
                else:
                    val = max(0.2, 1.0 - 0.07 * (ago - hi))
                if val > best:
                    best, best_d = val, f"opad {mm:.0f} mm {ago} dni temu; typowe opóźnienie {lo}–{hi} dni przy ~{t:.0f}°C"
            v, d = best, best_d
        factors.append(Factor("opoznienie", v, w["opoznienie"], d))
        reasons.append(d[0].upper() + d[1:] + ".")
    else:
        factors.append(Factor("opoznienie", None, w["opoznienie"], "brak danych do oceny opóźnienia po opadzie"))

    if t is not None:
        tc = pg.temperatura
        v = trapezoid(t, tc.t_sr_min, tc.t_sr_optimum[0], tc.t_sr_optimum[1], tc.t_sr_max)
        factors.append(Factor("temperatura", v, w["temperatura"], f"średnia temp. 7 dni {t:.1f}°C"))
    else:
        factors.append(Factor("temperatura", None, w["temperatura"], "brak danych temperatury"))

    sm = ind.wilg_gleby_dzien
    if sm is not None:
        g = c["wilgotnosc_gleby_m3m3"]
        v = trapezoid(sm, g["sucha"], g["optimum"][0], g["optimum"][1], 0.6, edge=0.0)
        factors.append(Factor("wilgotnosc_gleby", v, w["wilgotnosc_gleby"],
                              f"wilgotność gleby (model, komórka siatki) {sm:.2f} m³/m³"))
    else:
        factors.append(Factor("wilgotnosc_gleby", None, w["wilgotnosc_gleby"], "brak wilgotności gleby z modelu"))

    # Dostępność wody (opad + kary za suszę) jest czynnikiem ograniczającym (mnożnik), jak sezon;
    # opóźnienie, temperatura i wilgotność gleby — średnia ważona.
    water = next(f for f in factors if f.nazwa == "wilgoc")
    score, _ = _weighted([f for f in factors if f.nazwa != "wilgoc"])
    _, comp = _weighted(factors)
    if score is not None and water.wartosc is not None:
        score *= water.wartosc
    frost_pen = 0.0
    if ind.przymrozki_7:
        frost_pen = ind.przymrozki_7 * pg.przymrozek.kara_pkt_za_dzien_7d
        reasons.append(f"Przymrozki w ostatnich 7 dniach: {ind.przymrozki_7} (kara {frost_pen:.0f} pkt).")
    if score is None:
        return Component(None, 0.0, factors, reasons), ind, gates
    result = max(0.0, season * score * 100 - frost_pen)
    factors.insert(0, Factor("sezon", season, 0.0, sdesc + " (mnożnik)"))
    n_fc = ind.sklad_typow.get("prognoza", 0)
    comp *= full["kompletnosc"]["prognoza_mnoznik_dnia"] ** n_fc
    if n_fc:
        reasons.append(f"Dni prognozy w oknie: {n_fc} — mniejsza pewność.")
    return Component(round(result, 1), round(comp, 3), factors, reasons), ind, gates


# ---------------------------------------------------------------- C: obserwacje
@dataclass
class Observation:
    dni_temu: int
    odleglosc_km: float
    znaleziono: bool
    jakosc: str            # wysoka | srednia | niska
    czas_szukania_min: int | None = None


def observations(obs: list[Observation], cfg: dict | None = None) -> tuple[float, list[str]]:
    c = (cfg or load_yaml("model.yaml"))["obserwacje"]
    total, found, nothing = 0.0, 0, 0
    for o in obs:
        if o.odleglosc_km > c["promien_km"]:
            continue
        wgt = c["jakosc"].get(o.jakosc, 0.3) * 0.5 ** (o.dni_temu / c["polowiczny_czas_dni"]) \
            * math.exp(-o.odleglosc_km / c["skala_odleglosci_km"])
        if o.znaleziono:
            total += wgt
            found += 1
        else:
            # krótkie szukanie mniej znaczy niż długie
            effort = min(1.0, (o.czas_szukania_min or 60) / 120)
            total -= c["waga_nic_nie_znalazlem"] * wgt * effort
            nothing += 1
    pts = round(c["max_pkt"] * math.tanh(total), 1)
    reasons = []
    if found or nothing:
        reasons.append(f"Zgłoszenia w promieniu {c['promien_km']} km: znaleziska {found}, „nic nie znalazłem” {nothing} "
                       f"(modyfikator {pts:+.1f} pkt).")
    return pts, reasons
