"""Odczyt i zapis rejestru źródeł (sources.yaml) z zachowaniem komentarza nagłówka."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import SOURCES_FILE


def _split_header(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or not lines[i].strip()):
        i += 1
    return "".join(lines[:i]), "".join(lines[i:])


def load_sources(path: Path = SOURCES_FILE) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["zrodla"]


def update_source(source_id: str, path: Path = SOURCES_FILE, **fields: Any) -> None:
    text = path.read_text(encoding="utf-8")
    header, _ = _split_header(text)
    data = yaml.safe_load(text)
    if source_id not in data["zrodla"]:
        raise KeyError(f"Nieznane źródło w sources.yaml: {source_id}")
    data["zrodla"][source_id].update(fields)
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=110)
    path.write_text(header + body, encoding="utf-8")
