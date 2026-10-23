"""Katalog gatunków i „Pomóż oznaczyć”: dopasowanie odpowiedzi o cechach do danych katalogu.
To podpowiedź, nie oznaczenie — wynik nigdy nie mówi, że okaz należy do gatunku, i nie ocenia jadalności."""
from __future__ import annotations

from .config import load_yaml


def cfg() -> dict:
    return load_yaml("klucz.yaml")


def species_values(sp: dict, q: dict) -> list[str]:
    src = sp.get(q["zrodlo"]) or {}
    return [str(v) for v in (src.get(q["id"]) or [])]


def match(species: list[dict], answers: dict[str, list[str]], c: dict | None = None) -> list[dict]:
    """answers: {id_pytania: [klucze odpowiedzi]}. Zwraca gatunki z punktacją, posortowane."""
    c = c or cfg()
    pts = c["punkty"]
    qs = {q["id"]: q for q in c["pytania"]}
    out = []
    for sp in species:
        score, ok, bad, unknown = 0, [], [], []
        for qid, keys in answers.items():
            q = qs.get(qid)
            if not q or not keys:
                continue
            wanted = {v.lower() for k in keys if k in q["odpowiedzi"] for v in q["odpowiedzi"][k]["wartosci"]}
            if not wanted:                      # odpowiedź spoza słownika — pytanie pomijamy
                continue
            have = {v.lower() for v in species_values(sp, q)}
            if not have:
                unknown.append(qid)
                score += pts["brak_danych"]
            elif wanted & have:
                ok.append(qid)
                score += pts["zgodne"]
            else:
                bad.append(qid)
                score += pts["niezgodne"]
        out.append({"gatunek": sp, "punkty": score, "zgodne": ok, "niezgodne": bad, "brak_danych": unknown,
                    "ostrzezenie_rodzaj": (sp.get("rodzaj") in c["rodzaje_smiertelne"])})
    # najpierw liczba zgodnych cech, potem brak sprzeczności, potem częstość w województwie
    out.sort(key=lambda r: (-r["punkty"], -len(r["zgodne"]), -(r["gatunek"].get("obserwacje_woj") or 0)))
    return out


def label(field: str, value: str, c: dict | None = None) -> str:
    c = c or cfg()
    return c["wartosci"].get(value, value)
