import shutil

import yaml

from grzyby.config import SOURCES_FILE
from grzyby.sources import load_sources, update_source

REQUIRED = ["nazwa", "url", "zasieg", "rozdzielczosc", "aktualnosc", "licencja", "atrybucja",
            "uzyte_pola", "metoda", "ostatni_import", "weryfikacja", "do_weryfikacji"]


def test_every_source_has_required_fields():
    for sid, s in load_sources().items():
        missing = [k for k in REQUIRED if k not in s]
        assert not missing, f"{sid}: brak pól {missing}"
        assert s["url"].startswith("https://"), sid


def test_tile_openstreetmap_org_is_not_used():
    assert "tile.openstreetmap.org" not in SOURCES_FILE.read_text()


def test_update_preserves_header(tmp_path):
    p = tmp_path / "s.yaml"
    shutil.copy(SOURCES_FILE, p)
    header = SOURCES_FILE.read_text().split("zrodla:")[0]
    update_source("gbif", path=p, ostatni_import="2026-01-01T00:00:00+00:00")
    text = p.read_text()
    assert text.startswith(header)
    assert yaml.safe_load(text)["zrodla"]["gbif"]["ostatni_import"] == "2026-01-01T00:00:00+00:00"
