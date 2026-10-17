"""Ścieżki i ładowanie plików konfiguracyjnych."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("GRZYBY_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
DERIVED_DIR = DATA_DIR / "derived"
DOCS_DIR = ROOT / "docs"
SCHEMAS_DIR = DOCS_DIR / "schemas"
SOURCES_FILE = ROOT / "sources.yaml"

TIMEZONE = "Europe/Warsaw"
CRS_STORAGE = "EPSG:2180"
CRS_API = "EPSG:4326"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://grzyby:grzyby@localhost:5432/grzyby")


@lru_cache
def load_yaml(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def pilot_config() -> dict[str, Any]:
    return load_yaml("pilot.yaml")


def bdl_mapping() -> dict[str, Any]:
    return load_yaml("bdl_mapping.yaml")
