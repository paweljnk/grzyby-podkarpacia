import copy

import pytest
import yaml
from pydantic import ValidationError

from grzyby.species import SPECIES_DIR, Species, all_species, load_bibliography, validate_cross_refs

MVP = {"boletus_edulis", "imleria_badia", "cantharellus_cibarius"}


def test_mvp_species_present_and_valid():
    sp = all_species()
    assert MVP <= set(sp)


def test_cross_references_resolve():
    assert validate_cross_refs(all_species(), load_bibliography()) == []


def test_every_rule_has_reliability_grade():
    for sp in all_species().values():
        for name in ("typ_troficzny", "gleba", "typy_siedliskowe", "sezon", "status"):
            assert getattr(sp, name).wiarygodnosc in {"A", "B", "C"}, (sp.id, name)
        for p in sp.drzewa_partnerskie:
            assert p.wiarygodnosc in {"A", "B", "C"}


def test_weather_rules_are_marked_as_assumptions_until_calibrated():
    # Liczbowe progi pogodowe nie mają źródła naukowego podającego te wartości — muszą być klasy C.
    for sp in all_species().values():
        assert sp.pogoda.opoznienie_po_opadzie.wiarygodnosc == "C"
        assert "zalozenie_projektowe" in sp.pogoda.opoznienie_po_opadzie.zrodla


def test_unapproved_species_are_drafts():
    for sp in all_species().values():
        if sp.weryfikacja.status == "wersja_robocza":
            assert sp.weryfikacja.zatwierdzil is None


def _raw(name="boletus_edulis"):
    return yaml.safe_load((SPECIES_DIR / f"{name}.yaml").read_text())


def test_rejects_rule_without_source():
    d = _raw()
    d["gleba"]["zrodla"] = []
    with pytest.raises(ValidationError):
        Species.model_validate(d)


def test_rejects_unknown_field_and_bad_status():
    d = _raw()
    d["dzien_grzybowy"] = True
    with pytest.raises(ValidationError):
        Species.model_validate(d)
    d = _raw()
    d["status"]["wartosc"] = "chyba_jadalny"
    with pytest.raises(ValidationError):
        Species.model_validate(d)


def test_rejects_unordered_season_and_temperatures():
    d = _raw()
    d["sezon"]["koniec"] = "05-01"
    with pytest.raises(ValidationError):
        Species.model_validate(d)
    d = _raw()
    d["pogoda"]["temperatura"]["t_sr_min"] = 30
    with pytest.raises(ValidationError):
        Species.model_validate(d)


def test_rejects_gap_in_lag_thresholds():
    d = _raw()
    d["pogoda"]["opoznienie_po_opadzie"]["progi"][1]["t_sr_od"] = 13
    with pytest.raises(ValidationError):
        Species.model_validate(d)


def test_cross_ref_detects_unknown_tree():
    sp = copy.deepcopy(all_species())
    sp["boletus_edulis"].drzewa_partnerskie[0].drzewo = "XX"
    assert any("nieznane drzewo" in e for e in validate_cross_refs(sp, load_bibliography()))
