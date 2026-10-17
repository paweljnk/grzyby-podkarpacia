"""Normalizacja kodów z BDL do słowników projektu (config/slowniki.yaml).

BDL podaje kody wielkimi literami bez znaków diakrytycznych (np. site_type 'BMW', 'OLJ', species_cd 'SO').
Porównujemy po kluczu: wielkie litery, bez diakrytyków, bez kropek i spacji. Kod bez odpowiednika zostaje
w postaci surowej (model traktuje go jako nieznany) — nie zgadujemy.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache

from ..config import load_yaml


def key(code: str) -> str:
    s = unicodedata.normalize("NFKD", code.replace("ł", "l").replace("Ł", "L"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.upper().replace(".", "").replace(" ", "")


@lru_cache
def _tsl_index() -> dict[str, str]:
    return {key(k): k for k in load_yaml("slowniki.yaml")["typy_siedliskowe"]}


@lru_cache
def _tree_index() -> dict[str, str]:
    return {key(k): k for k in load_yaml("slowniki.yaml")["drzewa"]}


def site_type(code: str | None) -> str | None:
    if not code or not code.strip():
        return None
    return _tsl_index().get(key(code), code.strip())


def species(code: str | None) -> str | None:
    if not code or not code.strip():
        return None
    c = code.strip()
    # Kody z podgatunkiem/odmianą (np. 'DB.S') sprowadzamy do rodzaju, jeśli rodzaj jest w słowniku.
    base = c.split(".")[0]
    return _tree_index().get(key(c)) or _tree_index().get(key(base)) or c


def search_key(name: str) -> str:
    return key(name).lower()
