"""Katalog gatunków: parsowanie sekcji Wikipedii i cech siedliska (bez sieci)."""
from grzyby.config import load_yaml
from grzyby.etl.katalog import habitat_tags, pick_sections, slug, split_sections

TEXT = """Borowik szlachetny (Boletus edulis Bull.) – gatunek grzybów z rodziny borowikowatych.

== Systematyka i nazewnictwo ==
Nazwa polska...

== Morfologia ==
=== Kapelusz ===
Średnicy 5–25 cm, brązowy.
=== Trzon ===
Z białą siateczką.

== Występowanie i siedlisko ==
Tworzy mikoryzę ze świerkami, sosnami i bukami. Rośnie na glebach kwaśnych i piaszczystych.

== Gatunki podobne ==
Goryczak żółciowy (Tylopilus felleus) ma gorzki miąższ.

== Znaczenie ==
Grzyb jadalny.
"""


def test_sections_split_and_selected_without_edibility():
    cfg = load_yaml("katalog.yaml")
    secs = split_sections(TEXT)
    assert "Morfologia" in secs and secs["_wstep"].startswith("Borowik")
    out = pick_sections(TEXT, cfg)
    assert "Kapelusz:" in out["opis_budowa"] and "Trzon:" in out["opis_budowa"]
    assert out["opis_podobne"].startswith("Goryczak")
    assert out["opis_ochrona"] is None
    assert all("jadalny" not in (v or "") for v in out.values())    # sekcja „Znaczenie” pomijana


def test_habitat_tags_from_description():
    cfg = load_yaml("katalog.yaml")
    t = habitat_tags(pick_sections(TEXT, cfg)["opis_wystepowanie"], cfg)
    assert set(t["drzewa"]) == {"świerk", "sosna", "buk"}
    assert set(t["gleba"]) == {"kwaśna", "piaszczysta"}
    assert habitat_tags(None, cfg) == {}
    assert habitat_tags("Rośnie w zaroślach.", cfg) == {}


def test_long_section_cut_at_sentence():
    cfg = {**load_yaml("katalog.yaml"), "max_znakow_sekcji": 60}
    long = "== Morfologia ==\n" + "Zdanie numer jeden jest tutaj. " * 10
    out = pick_sections(long, cfg)["opis_budowa"]
    assert out.endswith("[…]") and len(out) <= 70


def test_slug():
    assert slug("Boletus edulis") == "boletus_edulis"
    assert slug("Lactarius deliciosus var. x") == "lactarius_deliciosus_var_x"
