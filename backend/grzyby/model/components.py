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
    wynik: float | None                  # warunki (środek przedziału)
    kompletnosc: float                   # pewność wejść 0–1 (źródło=1, model=0.5, brak=0) — NIE wpływa na warunki
    czynniki: list[Factor] = field(default_factory=list)
    uzasadnienie: list[str] = field(default_factory=list)
    zakres: tuple[float, float] | None = None   # przedział warunków, gdy część danych nieznana


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
    gleba: str | None                       # podtyp gleby (kod BDL) albo nazwa
    wys_sr: float | None
    nachylenie_sr: float | None
    udzial_panujacego: float | None = None  # part_cd/10
    ph_model: float | None = None           # SoilGrids (model)
    ph_q05: float | None = None
    ph_q95: float | None = None


def soil_from_code(code: str) -> dict | None:
    """Cechy gleby z kodu podtypu BDL (najdłuższy prefiks w config/gleby_bdl.yaml) albo z nazwy (config/gleby.yaml)."""
    podtypy = load_yaml("gleby_bdl.yaml")["podtypy"]
    c = code.strip()
    for k in sorted(podtypy, key=len, reverse=True):
        if c.startswith(k):
            return {**podtypy[k], "kod": c}
    g = c.lower()
    for t in load_yaml("gleby.yaml")["typy"]:
        if g.startswith(t["prefiks"]):
            return {"nazwa": c, "odczyn": t["odczyn"], "zyznosc": t["zyznosc"], "kod": c}
    return None


def ph_class(ph: float) -> str:
    for k in load_yaml("gleby_bdl.yaml")["ph_klasy"]:
        if ph < k["do"]:
            return k["odczyn"]
    return "zasadowy"


def _trees_interval(stand: Stand, sp: Species, cfg: dict) -> tuple[float | None, float | None, float, str]:
    """(dolna, górna granica czynnika drzew, pewność wejścia 0–1, opis). Nieznana część składu → przedział, nie zgadywanie."""
    strength = {p.drzewo: cfg["sila_zwiazku"][p.sila] for p in sp.drzewa_partnerskie}
    sat = cfg["udzial_nasycenia"]
    names = {k: v["nazwa"] for k, v in load_yaml("slowniki.yaml")["drzewa"].items()}
    if stand.udzial_gatunkow:
        s = sum(share * strength.get(t, 0.0) for t, share in stand.udzial_gatunkow.items())
        v = min(1.0, s / sat)
        desc = ", ".join(f"{names.get(t, t)} {round(sh * 100)}%" for t, sh in sorted(stand.udzial_gatunkow.items(), key=lambda x: -x[1]))
        return v, v, 1.0, f"pełny skład: {desc}"
    if not stand.gatunek_panujacy:
        return None, None, 0.0, "brak danych o drzewostanie"
    dom = stand.gatunek_panujacy
    st = strength.get(dom, 0.0)
    if stand.udzial_panujacego is not None:
        share, known = stand.udzial_panujacego, stand.udzial_panujacego
    else:
        share, known = cfg["udzial_nieznany_min"], 0.0
    lo = min(1.0, share * st / sat)
    hi = min(1.0, (share * st + (1 - share) * 1.0) / sat) if share < 1 else lo
    if stand.udzial_panujacego is None:
        hi = 1.0
    sh = f"{round(stand.udzial_panujacego * 100)}%" if stand.udzial_panujacego is not None else "udział nieznany"
    rest = "" if share >= 1 else f"; pozostałe {round((1 - share) * 100)}% składu nieznane"
    role = "partner" if st > 0 else "nie jest partnerem mikoryzowym"
    return lo, hi, max(known, 0.5 if stand.udzial_panujacego is None else known), \
        f"gatunek panujący {names.get(dom, dom)} {sh} ({role}){rest}"


def habitat(stand: Stand, sp: Species, cfg: dict | None = None) -> Component:
    full = cfg or load_yaml("model.yaml")
    cfg = full["siedlisko"]
    w = cfg["wagi"]
    cred = cfg["pewnosc_zrodla"]
    reasons: list[str] = []
    factors: list[Factor] = []
    conf: dict[str, float] = {}          # pewność wejść (0–1) dla liczenia pewności, nie warunków

    trees_lo = trees_hi = None
    if sp.typ_troficzny.wartosc == "mikoryzowy":
        trees_lo, trees_hi, c, d = _trees_interval(stand, sp, cfg)
        conf["drzewa"] = c
        factors.append(Factor("drzewa", None if trees_lo is None else (trees_lo + trees_hi) / 2, w["drzewa"], d))
        reasons.append(d[0].upper() + d[1:] + ".")
        if trees_lo is not None and trees_hi - trees_lo > 0.01:
            reasons.append("Nieznany pełny skład drzewostanu — warunki podane jako przedział, obniżona pewność.")

    tsl = stand.typ_siedliskowy
    if tsl:
        if tsl in sp.typy_siedliskowe.preferowane:
            v, d = cfg["typ_siedliskowy"]["preferowany"], f"typ siedliskowy {tsl} — preferowany"
        elif tsl in sp.typy_siedliskowe.dopuszczalne:
            v, d = cfg["typ_siedliskowy"]["dopuszczalny"], f"typ siedliskowy {tsl} — dopuszczalny"
        else:
            v, d = cfg["typ_siedliskowy"]["inny"], f"typ siedliskowy {tsl} — nietypowy dla gatunku"
        factors.append(Factor("typ_siedliskowy", v, w["typ_siedliskowy"], d))
        conf["typ_siedliskowy"] = cred["zrodlowa"]
        reasons.append(d[0].upper() + d[1:] + ".")
    else:
        factors.append(Factor("typ_siedliskowy", None, w["typ_siedliskowy"], "brak typu siedliskowego"))
        conf["typ_siedliskowy"] = 0.0

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
        factors.append(Factor("wiek", v, w["wiek"], f"wiek gatunku panującego {stand.wiek} lat"))
        conf["wiek"] = cred["zrodlowa"]
    else:
        factors.append(Factor("wiek", None, w["wiek"], "brak wieku drzewostanu"))
        conf["wiek"] = 0.0

    # gleba: najpierw opis z BDL (źródło), potem SoilGrids (model); niepewny model → cecha pominięta
    traits = soil_from_code(stand.gleba) if stand.gleba else None
    if traits and (traits.get("odczyn") or traits.get("zyznosc")):
        checks = []
        if traits.get("odczyn"):
            checks.append(traits["odczyn"] in sp.gleba.odczyn)
        if traits.get("zyznosc"):
            checks.append(traits["zyznosc"] in sp.gleba.zyznosc)
        ok = all(checks)
        v = cfg["gleba_zgodna"] if ok else cfg["gleba_niezgodna"]
        factors.append(Factor("gleba", v, w["gleba"], f"gleba {traits['nazwa']} ({traits['kod']}, BDL) — "
                                                     f"{'zgodna' if ok else 'mniej typowa'} z wymaganiami gatunku"))
        conf["gleba"] = cred["zrodlowa"]
    elif stand.ph_model is not None:
        classes = {ph_class(x) for x in (stand.ph_model, stand.ph_q05, stand.ph_q95) if x is not None}
        if len(classes) == 1:
            cls = classes.pop()
            ok = cls in sp.gleba.odczyn
            v = cfg["gleba_zgodna"] if ok else cfg["gleba_niezgodna"]
            factors.append(Factor("gleba", v, w["gleba"], f"pH {stand.ph_model:.1f} (SoilGrids, model 250 m; przedział "
                                                         f"{stand.ph_q05}–{stand.ph_q95}) — odczyn {cls}"))
            conf["gleba"] = cred["model"]
            reasons.append(f"Gleba: brak opisu w BDL — użyto modelu SoilGrids (pH {stand.ph_model:.1f}, 250 m; to nie pomiar).")
        else:
            factors.append(Factor("gleba", None, w["gleba"], f"pH z modelu niepewne ({stand.ph_q05}–{stand.ph_q95}) — pominięte"))
            conf["gleba"] = 0.0
            reasons.append("Gleba: brak opisu w BDL, model SoilGrids zbyt niepewny — cecha pominięta (niższa pewność).")
    else:
        desc = "brak danych glebowych" if not stand.gleba else f"gleba '{stand.gleba}' bez przełożenia na cechy"
        factors.append(Factor("gleba", None, w["gleba"], desc))
        conf["gleba"] = 0.0
        reasons.append("Brak danych glebowych — obniżona pewność, nie gorsze warunki.")

    if stand.wys_sr is not None:
        inside = sp.wysokosc_npm.min_m <= stand.wys_sr <= sp.wysokosc_npm.max_m
        v = 1.0 if inside else cfg["teren_poza_zakresem_wysokosci"]
        d = f"wysokość ok. {round(stand.wys_sr)} m n.p.m. (DSM)"
        if stand.nachylenie_sr is not None and stand.nachylenie_sr > cfg["teren_nachylenie_trudne_deg"]:
            v *= cfg["teren_nachylenie_trudne_mnoznik"]
            d += f", strome zbocza {round(stand.nachylenie_sr)}°"
        factors.append(Factor("teren", v, w["teren"], d))
        conf["teren"] = cfg["teren_pewnosc"]
    else:
        factors.append(Factor("teren", None, w["teren"], "brak danych o rzeźbie terenu"))
        conf["teren"] = 0.0

    # Warunki: średnia ważona dostępnych cech (brakujące nie obniżają) × drzewa (czynnik ograniczający).
    others = [f for f in factors if f.nazwa != "drzewa"]
    base, _ = _weighted(others)
    wsum = sum(f.waga for f in factors)
    certainty = sum(f.waga * conf.get(f.nazwa, 0.0) for f in factors) / wsum if wsum else 0.0
    if base is None:
        return Component(None, round(certainty, 3), factors, reasons)
    if trees_lo is None:
        lo = hi = base
    else:
        lo, hi = base * trees_lo, base * trees_hi
    comp = Component(round((lo + hi) / 2 * 100, 1), round(certainty, 3), factors, reasons)
    comp.zakres = (round(lo * 100, 1), round(hi * 100, 1))
    return comp


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
