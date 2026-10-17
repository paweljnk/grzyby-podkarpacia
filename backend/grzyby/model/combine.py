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
    cfg = cfg or load_yaml("model.yaml")
    gates: list[Gate] = []
    reasons: list[str] = []
    if A.wynik is not None and A.wynik < cfg["bramki"]["A_min"]:
        gates.append(Gate("siedlisko", f"Siedlisko poniżej progu ({A.wynik:.0f} < {cfg['bramki']['A_min']})."))
    if drought:
        gates.append(Gate("susza", "Silna susza — miejsce wyłączone z rekomendacji wypraw."))
    for p in protection:
        if p.get("rodzaj") in cfg["bramki"]["zakaz_rodzaje"]:
            gates.append(Gate("zakaz", f"{p.get('nazwa') or 'Park narodowy'}: zbiór grzybów co do zasady zakazany "
                                       "(poza miejscami wyznaczonymi przez dyrektora parku)."))

    if A.wynik is None or B.wynik is None:
        missing = [n for n, c in (("siedlisko (A)", A), ("pogoda (B)", B)) if c.wynik is None]
        reasons.append("Nie można policzyć wskaźnika — brak danych: " + ", ".join(missing) + ".")
        base = total = None
    else:
        w = cfg["podstawa"]["wagi"]
        base = round(weighted_geometric(A.wynik, B.wynik, w["A"], w["B"]), 1)
        total = round(max(0.0, min(100.0, base + C + D)), 1)

    if total is not None and total < cfg["bramki"].get("wynik_min", 0) and not gates:
        gates.append(Gate("wynik_niski", f"Wskaźnik {total:.0f} poniżej progu rekomendacji ({cfg['bramki']['wynik_min']}) — "
                                         "np. poza sezonem albo przy niekorzystnej pogodzie."))
    # Kompletność: średnia kompletności A i B (C i D to modyfikatory — ich brak nie obniża kompletności).
    completeness = round((A.kompletnosc + B.kompletnosc) / 2, 3)
    reasons += A.uzasadnienie + B.uzasadnienie
    if D_details is not None:
        reasons.append(f"Kalendarz (eksperymentalny, bez potwierdzenia naukowego): {D:+.1f} pkt.")
    reasons += [g.opis for g in gates]
    return Score(total, base, A, B, C, D, D_details, gates, not gates and total is not None,
                 completeness, quality_label(completeness, cfg), reasons)
