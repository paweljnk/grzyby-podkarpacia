"""Ocena warunków vs pewność danych; gleba z BDL i z SoilGrids; geometrie z ArcGIS REST."""
import pytest
from shapely.geometry import Polygon

from grzyby.etl.arcgis import esri_to_shapely, fix_geometry, tiles
from grzyby.etl.bdl_province import part_share
from grzyby.model.combine import combine
from grzyby.model.components import Component, Stand, habitat, ph_class, soil_from_code
from grzyby.species import all_species

SP = all_species()["imleria_badia"]
B_OK = Component(70.0, 0.9)


def stand(**kw):
    base = dict(id=1, gatunek_panujacy="SO", udzial_gatunkow=None, wiek=80, typ_siedliskowy="BMśw", gleba="RDb",
                wys_sr=220.0, nachylenie_sr=3.0, udzial_panujacego=1.0)
    base.update(kw)
    return Stand(**base)


def test_missing_soil_lowers_certainty_not_conditions():
    full = habitat(stand(), SP)
    nosoil = habitat(stand(gleba=None), SP)
    assert nosoil.kompletnosc < full.kompletnosc
    assert nosoil.wynik >= full.wynik - 0.01          # brak gleby nie pogarsza warunków
    s_full, s_nosoil = combine(full, B_OK, 0, 0, None, False, []), combine(nosoil, B_OK, 0, 0, None, False, [])
    assert s_nosoil.kompletnosc < s_full.kompletnosc and s_nosoil.wynik >= s_full.wynik - 0.01


def test_unknown_composition_gives_interval_and_lower_certainty():
    # gatunek panujący nie jest partnerem (OL), 60% udziału; 40% składu nieznane
    a = habitat(stand(gatunek_panujacy="OL", udzial_panujacego=0.6), SP)
    lo, hi = a.zakres
    assert lo < hi and lo == pytest.approx(0, abs=1e-6)
    full_ol = habitat(stand(gatunek_panujacy="OL", udzial_panujacego=1.0), SP)
    assert full_ol.zakres[0] == full_ol.zakres[1] == 0          # 100% olszy: na pewno brak partnera
    s = combine(a, B_OK, 0, 0, None, False, [])
    assert s.warunki_min < s.warunki_max
    assert not any(g.kod == "siedlisko" for g in s.bramki)        # przedział sięga wysoko → bez bramki
    s_full = combine(full_ol, B_OK, 0, 0, None, False, [])
    assert any(g.kod == "siedlisko" for g in s_full.bramki)       # pewny brak partnera → bramka


def test_dominant_share_used_not_assumed():
    a100 = habitat(stand(udzial_panujacego=1.0), SP)
    a30 = habitat(stand(udzial_panujacego=0.3), SP)
    assert a100.zakres[0] == a100.zakres[1]
    assert a30.zakres[0] < a100.zakres[0] <= a30.zakres[1]
    assert a30.kompletnosc < a100.kompletnosc


def test_soilgrids_used_as_model_only_when_certain():
    certain = habitat(stand(gleba=None, ph_model=4.3, ph_q05=4.0, ph_q95=4.8), SP)
    f = next(x for x in certain.czynniki if x.nazwa == "gleba")
    assert f.wartosc == 1.0 and "SoilGrids" in f.opis
    uncertain = habitat(stand(gleba=None, ph_model=5.4, ph_q05=4.6, ph_q95=6.3), SP)
    assert next(x for x in uncertain.czynniki if x.nazwa == "gleba").wartosc is None
    source = habitat(stand(), SP)
    assert certain.kompletnosc < source.kompletnosc               # model < źródło
    assert uncertain.kompletnosc < certain.kompletnosc


@pytest.mark.parametrize("code,odczyn,zyznosc", [("BRk", "kwasny", "srednia"), ("BRwy", "lekko_kwasny", "srednia"),
                                                  ("RDb", "kwasny", "uboga"), ("Bgw", "kwasny", "uboga"),
                                                  ("MDbr", "obojetny", "zyzna"), ("OGw", None, "srednia")])
def test_bdl_soil_codes(code, odczyn, zyznosc):
    t = soil_from_code(code)
    assert t["odczyn"] == odczyn and t["zyznosc"] == zyznosc


def test_ph_classes():
    assert ph_class(4.2) == "kwasny" and ph_class(6.0) == "lekko_kwasny" and ph_class(7.0) == "obojetny"


@pytest.mark.parametrize("code,share", [("10 ", 1.0), ("5", 0.5), ("1", 0.1), ("PJD", None), (None, None), ("11", None)])
def test_part_share(code, share):
    assert part_share(code) == share


def test_esri_rings_with_hole_and_invalid_fix():
    outer = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]          # zgodnie z ruchem wskazówek = zewnętrzny
    hole = [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]               # przeciwnie = otwór
    g = esri_to_shapely({"rings": [outer, hole]})
    assert g.area == pytest.approx(100 - 4)
    bow = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
    fixed, was = fix_geometry(bow)
    assert was and fixed.is_valid and fixed.geom_type == "MultiPolygon"


def test_tiles_cover_bounds():
    t = tiles((21.1, 49.0, 21.6, 49.3), 0.25)
    assert len(t) == 4 and t[-1][1][2] == pytest.approx(21.6) and t[-1][1][3] == pytest.approx(49.3)
