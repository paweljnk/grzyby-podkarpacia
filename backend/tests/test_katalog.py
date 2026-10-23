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


def test_key_matching_prefers_matching_and_flags_deadly_genus():
    from grzyby.katalog import match
    sp = [
        {"id": "amanita_phalloides", "rodzaj": "Amanita", "obserwacje_woj": 5,
         "cechy": {"hymenium": ["lamella"], "trzon": ["ring and volva stipe"]}, "siedlisko": {"drzewa": ["dąb", "buk"]}},
        {"id": "boletus_edulis", "rodzaj": "Boletus", "obserwacje_woj": 50,
         "cechy": {"hymenium": ["pores"], "trzon": ["bare stipe"]}, "siedlisko": {"drzewa": ["świerk"]}},
        {"id": "bez_danych", "rodzaj": "X", "obserwacje_woj": 99, "cechy": {}, "siedlisko": {}},
    ]
    r = match(sp, {"hymenium": ["blaszki"], "trzon": ["pochwa"], "drzewa": ["buk"]})
    assert r[0]["gatunek"]["id"] == "amanita_phalloides" and r[0]["ostrzezenie_rodzaj"]
    assert r[0]["zgodne"] == ["hymenium", "trzon", "drzewa"]
    # gatunek bez danych nie wygrywa z niezgodnym tylko dzięki popularności — ale też nie jest „zgodny”
    nd = next(x for x in r if x["gatunek"]["id"] == "bez_danych")
    assert nd["zgodne"] == [] and set(nd["brak_danych"]) == {"hymenium", "trzon", "drzewa"}
    b = next(x for x in r if x["gatunek"]["id"] == "boletus_edulis")
    assert set(b["niezgodne"]) == {"hymenium", "trzon", "drzewa"} and b["punkty"] < nd["punkty"]


def test_key_ignores_unknown_answers():
    from grzyby.katalog import match
    r = match([{"id": "a", "cechy": {"hymenium": ["gills"]}, "siedlisko": {}}], {"hymenium": ["nieznane"], "x": ["y"]})
    assert r[0]["punkty"] == 0 and r[0]["niezgodne"] == []
