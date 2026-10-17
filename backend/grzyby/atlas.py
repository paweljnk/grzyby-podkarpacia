"""Atlas: treści (atlas/*.yaml) i zdjęcia (atlas.zdjecie). Tylko nauka — bez oceny jadalności okazów."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from .config import ROOT
from .species import load_bibliography

ATLAS_DIR = ROOT / "atlas"
Waga = Literal["kluczowa", "pomocnicza", "slaba"]
Ujecie = Literal["mlody", "dojrzaly", "spod", "trzon", "przekroj", "inne"]


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Weryf(_S):
    status: Literal["wersja_robocza", "zatwierdzone"]
    zatwierdzil: str | None
    data: str | None


class Opis(_S):
    id: str
    nazwa_polska: str
    nazwa_naukowa: str
    status: Literal["jadalny", "niejadalny", "trujacy", "smiertelnie_trujacy", "niepewny"]
    status_uwagi: str | None = None
    grupa: Literal["rurkowe", "blaszkowe", "listewkowe"]
    cechy: dict[Literal["kapelusz", "hymenofor", "trzon", "miazsz", "siedlisko"], str]
    zrodla: list[str]
    weryfikacja: Weryf


class Cecha(_S):
    cecha: str
    ujecie: Ujecie | None
    jadalny: str
    sobowtor: str
    waga: Waga
    zrodla: list[str]


class Para(_S):
    id: str
    jadalny: str
    sobowtor: str
    kategoria_sobowtora: str
    ryzyko_pomylki: Literal["wysokie", "srednie", "niskie"]
    skutek_pomylki: str
    cechy: list[Cecha]
    uwagi: list[str]
    zrodla: list[str]
    weryfikacja: Weryf


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def opisy() -> dict[str, Opis]:
    return {o.id: o for o in (Opis.model_validate(_load(p)) for p in sorted((ATLAS_DIR / "opisy").glob("*.yaml")))}


@lru_cache
def pary() -> dict[str, Para]:
    return {p.id: p for p in (Para.model_validate(_load(x)) for x in sorted((ATLAS_DIR / "pary").glob("*.yaml")))}


@lru_cache
def bezpieczenstwo() -> dict:
    return _load(ATLAS_DIR / "bezpieczenstwo.yaml")


@lru_cache
def photo_config() -> dict:
    return _load(ATLAS_DIR / "config_zdjecia.yaml")


def is_draft() -> bool:
    b = bezpieczenstwo()
    return b["weryfikacja"]["status"] != "zatwierdzone" or any(
        o.weryfikacja.status != "zatwierdzone" for o in opisy().values()) or any(
        p.weryfikacja.status != "zatwierdzone" for p in pary().values())


def validate() -> list[str]:
    """Spójność treści: odwołania do gatunków i źródeł, wymagane elementy bezpieczeństwa."""
    errors: list[str] = []
    bib = set(load_bibliography())
    o = opisy()
    for p in pary().values():
        for sid in (p.jadalny, p.sobowtor):
            if sid not in o:
                errors.append(f"{p.id}: brak opisu gatunku {sid}")
        if not any(c.waga == "kluczowa" for c in p.cechy):
            errors.append(f"{p.id}: brak cechy kluczowej")
        for c in p.cechy:
            for z in c.zrodla:
                if z not in bib:
                    errors.append(f"{p.id}: nieznane źródło {z}")
        if o.get(p.jadalny) and o[p.jadalny].status != "jadalny":
            errors.append(f"{p.id}: gatunek 'jadalny' ma status {o[p.jadalny].status}")
    for x in o.values():
        for z in x.zrodla:
            if z not in bib:
                errors.append(f"{x.id}: nieznane źródło {z}")
    b = bezpieczenstwo()
    srcs = set(b["zrodla"])
    for m in b["mity"]:
        if not m["zrodla"] and not m.get("uwaga_zrodla"):
            errors.append(f"mit bez źródła i bez adnotacji: {m['mit']}")
        for z in m["zrodla"]:
            if z not in srcs:
                errors.append(f"mit: nieznane źródło {z}")
    if "112" not in [t["numer"] for t in b["zatrucie"]["telefony"]]:
        errors.append("brak numeru 112")
    if "100%" not in b["komunikat"]:
        errors.append("komunikat stały niezgodny z wymaganiem")
    return errors


def mvp_species_with_doubles() -> list[str]:
    ids: list[str] = []
    for p in pary().values():
        for s in (p.jadalny, p.sobowtor):
            if s not in ids:
                ids.append(s)
    return ids
