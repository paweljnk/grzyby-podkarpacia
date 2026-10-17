"""Łączenie składowych w wskaźnik rekomendacji 0–100.

podstawa = A^wA · B^wB (ważona średnia geometryczna)
wynik    = clamp(podstawa + C + D, 0, 100)
Bramki (A < próg, silna susza, potwierdzony zakaz) wykluczają miejsce z rekomendacji wypraw niezależnie od C i D.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..config import load_yaml
from .components import Component


@dataclass
class Gate:
    kod: str
    opis: str


@dataclass
class Score:
    wynik: float | None
    podstawa: float | None
    A: Component
    B: Component
    C: float
    D: float
    D_szczegoly: dict | None
    bramki: list[Gate]
    rekomendowane: bool
    kompletnosc: float
    jakosc: str
    uzasadnienie: list[str] = field(default_factory=list)
    warunki_min: float | None = None     # przedział warunków (nieznana część danych)
    warunki_max: float | None = None


def weighted_geometric(a: float, b: float, wa: float, wb: float) -> float:
    if a <= 0 or b <= 0:
        return 0.0
    s = wa + wb
    return (a ** (wa / s)) * (b ** (wb / s))


def quality_label(completeness: float, cfg: dict) -> str:
    p = cfg["kompletnosc"]["progi"]
    return "wysoka" if completeness >= p["wysoka"] else "srednia" if completeness >= p["srednia"] else "niska"


def combine(A: Component, B: Component, C: float, D: float, D_details: dict | None,
            drought: bool, protection: list[dict], cfg: dict | None = None) -> Score:
    """Warunki (0–100, przedział) i pewność danych liczone ODDZIELNIE: brak danych obniża pewność, nie warunki."""
    cfg = cfg or load_yaml("model.yaml")
    gates: list[Gate] = []
    reasons: list[str] = []
    a_lo, a_hi = A.zakres if A.zakres else (A.wynik, A.wynik)
    # bramka siedliska wg GÓRNEJ granicy — nieznany skład nie może sam wykluczyć miejsca
    if a_hi is not None and a_hi < cfg["bramki"]["A_min"]:
        gates.append(Gate("siedlisko", f"Siedlisko poniżej progu ({a_hi:.0f} < {cfg['bramki']['A_min']}) nawet w wariancie korzystnym."))
    if drought:
        gates.append(Gate("susza", "Silna susza — miejsce wyłączone z rekomendacji wypraw."))
    for p in protection:
        if p.get("rodzaj") in cfg["bramki"]["zakaz_rodzaje"]:
            gates.append(Gate("zakaz", f"{p.get('nazwa') or 'Park narodowy'}: zbiór grzybów co do zasady zakazany "
                                       "(poza miejscami wyznaczonymi przez dyrektora parku)."))

    lo = hi = base = total = None
    if A.wynik is None or B.wynik is None:
        missing = [n for n, c in (("siedlisko (A)", A), ("pogoda (B)", B)) if c.wynik is None]
        reasons.append("Nie można ocenić warunków — brak danych: " + ", ".join(missing) + ".")
    else:
        w = cfg["podstawa"]["wagi"]
        clamp = lambda x: round(max(0.0, min(100.0, x + C + D)), 1)
        b_lo = weighted_geometric(a_lo, B.wynik, w["A"], w["B"])
        b_hi = weighted_geometric(a_hi, B.wynik, w["A"], w["B"])
        base = round((b_lo + b_hi) / 2, 1)
        lo, hi = clamp(b_lo), clamp(b_hi)
        total = round((lo + hi) / 2, 1)
        if hi < cfg["bramki"].get("wynik_min", 0) and not gates:
            gates.append(Gate("wynik_niski", f"Warunki {hi:.0f} poniżej progu rekomendacji ({cfg['bramki']['wynik_min']}) — "
                                             "np. poza sezonem albo przy niekorzystnej pogodzie."))
    width = (hi - lo) if lo is not None else 0.0
    certainty = (A.kompletnosc + B.kompletnosc) / 2 * (1 - cfg["kompletnosc"].get("kara_za_szerokosc_przedzialu", 0) * width / 100)
    certainty = round(max(0.0, certainty), 3)
    reasons += A.uzasadnienie + B.uzasadnienie
    if D_details is not None:
        reasons.append(f"Kalendarz (eksperymentalny, bez potwierdzenia naukowego): {D:+.1f} pkt.")
    reasons += [g.opis for g in gates]
    return Score(total, base, A, B, C, D, D_details, gates, not gates and total is not None,
                 certainty, quality_label(certainty, cfg), reasons, lo, hi)
