"""Nasłonecznienie stoku: względne dzienne promieniowanie bezpośrednie na stoku wobec terenu płaskiego.

Kąt padania promieni na powierzchnię nachyloną — Duffie & Beckman, „Solar Engineering of Thermal Processes”,
równanie 1.6.1; deklinacja wg wzoru Coopera (tamże, 1.6.1a). Suma cos(θ) dla Słońca nad horyzontem, krok 10 min.
Uproszczenia (model, nie pomiar): bez atmosfery i promieniowania rozproszonego, bez zacienienia przez sąsiednie
stoki i korony drzew. Ekspozycja: azymut kierunku spadku, 0° = N, zgodnie z ruchem wskazówek zegara.
"""
from __future__ import annotations

import math
from datetime import date
from functools import lru_cache


def _cos_incidence(phi: float, delta: float, beta: float, gamma: float, omega: float) -> float:
    sd, cd = math.sin(delta), math.cos(delta)
    sp, cp = math.sin(phi), math.cos(phi)
    sb, cb = math.sin(beta), math.cos(beta)
    sg, cg = math.sin(gamma), math.cos(gamma)
    so, co = math.sin(omega), math.cos(omega)
    return (sd * sp * cb - sd * cp * sb * cg + cd * cp * cb * co + cd * sp * sb * cg * co + cd * sb * sg * so)


@lru_cache(maxsize=4096)
def _index(lat10: int, slope: int, aspect15: int, doy: int) -> float:
    phi = math.radians(lat10 / 10)
    delta = math.radians(23.45 * math.sin(math.radians(360 * (284 + doy) / 365)))
    beta = math.radians(slope)
    gamma = math.radians(aspect15 * 15 - 180)            # azymut powierzchni od południa, zachód dodatni
    on_slope = flat = 0.0
    for k in range(-72, 73):                              # godziny słoneczne −12…+12, krok 10 min
        omega = math.radians(k * 15 / 6)
        cz = _cos_incidence(phi, delta, 0.0, 0.0, omega)
        if cz <= 0:                                       # Słońce pod horyzontem
            continue
        flat += cz
        on_slope += max(0.0, _cos_incidence(phi, delta, beta, gamma, omega))
    return on_slope / flat if flat else 1.0


def insolation_index(lat: float, slope_deg: float | None, aspect_deg: float | None, day: date) -> float | None:
    """1.0 = jak teren płaski; >1 stok silniej nasłoneczniony (południowy), <1 słabiej (północny)."""
    if slope_deg is None or lat is None:
        return None
    if slope_deg < 2 or aspect_deg is None:
        return 1.0
    return round(_index(round(lat * 10), round(slope_deg), round(aspect_deg / 15) % 24, day.timetuple().tm_yday), 3)
