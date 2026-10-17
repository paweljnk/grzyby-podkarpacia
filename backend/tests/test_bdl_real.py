"""Mapowanie BDL na podstawie rzeczywistej próbki (docs/schemas/bdl_ogcapi.json z GitHub Actions, 2026-10-17)."""
import pytest

from grzyby.config import bdl_mapping
from grzyby.etl.bdl_codes import site_type, species, search_key
from grzyby.etl.vector import map_bdl_feature
from grzyby.weather.openmeteo import BadResponse, parse_hourly

# Właściwości skopiowane z rzeczywistej próbki RDLP_Krosno_wydzielenia (Nadl. Głogów, 04-08).
REAL = {"adr_for": "04-08-2-09-163   -k   -00", "site_type": "OLJ", "forest_fun": "GOSP", "rotat_age": 80,
        "prot_categ": "OCH USZK", "part_cd": "5", "a_year": 2026, "a_i_num": 408016782, "area_type": "D-STAN",
        "silvicult": "S", "stand_stru": "DRZEW", "sub_area": 0.07, "species_cd": "GB", "spec_age": 25,
        "nazwa": "BDL_04_08_GLOGOW_2026"}


@pytest.mark.parametrize("raw,norm", [("OLJ", "OlJ"), ("BMW", "BMw"), ("BSW", "Bśw"), ("LMSW", "LMśw"),
                                       ("LL", "Lł"), ("LGŚW", "LGśw"), ("LŁG", "LłG"), ("BMGB", "BMGb"), ("OLJG", "OlJG"), ("BMWYZ", "BMwyż"), ("XYZ", "XYZ"), (" ", None)])
def test_site_type_normalization(raw, norm):
    assert site_type(raw) == norm


@pytest.mark.parametrize("raw,norm", [("SO", "SO"), ("ŚW", "SW"), ("SW", "SW"), ("DB.S", "DB"), ("DB.C", "DBC"), ("OL.S", "OLS"), ("BRZ", "BRZ"),
                                       ("JD", "JD"), ("AK", "AK"), (None, None)])
def test_species_normalization(raw, norm):
    assert species(raw) == norm


def test_map_real_feature():
    v = map_bdl_feature(REAL, bdl_mapping()["bdl_ogcapi"])
    assert v["external_id"] == "408016782" and v["adres_lesny"].startswith("04-08-")
    assert v["gatunek_panujacy"] == "GB" and v["wiek"] == 25 and v["typ_siedliskowy"] == "OlJ"
    assert v["gleba"] is None and v["udzial_gatunkow"] is None            # usługa ich nie udostępnia
    assert v["pochodzenie"] == {"gatunek_panujacy": "opis_taksacyjny", "udzial_gatunkow": "brak", "wiek": "opis_taksacyjny",
                                "typ_siedliskowy": "opis_taksacyjny", "gleba": "brak"}


def test_search_key():
    assert "glogow" in search_key("Głogów Małopolski") and search_key("Baligród") == "baligrod"


def test_optional_weather_variables_become_null():
    payload = {"hourly": {"time": [0, 3600], "precipitation": [0.1, 0.0]}}
    _, v = parse_hourly(payload, {"opad_mm": "precipitation", "wilg_gleby_m3m3": "soil_x"}, {"wilg_gleby_m3m3"})
    assert v["wilg_gleby_m3m3"] == [None, None]
    with pytest.raises(BadResponse):
        parse_hourly(payload, {"opad_mm": "precipitation", "temp_c": "temperature_2m"}, {"wilg_gleby_m3m3"})


@pytest.mark.db
def test_snapshot_roundtrip(tmp_path):
    from grzyby import snapshot
    from grzyby.db import connect
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO forest.wydzielenie (source_id, external_id, adres_lesny, gatunek_panujacy,
                         gatunek_panujacy_pochodzenie, attrs, geom)
                       VALUES ('test_snap','1','99-99-test','SO','opis_taksacyjny','{}',
                               ST_Multi(ST_Buffer(ST_SetSRID(ST_MakePoint(700000,250000),2180),50)))""")
    daily = tmp_path / "dzienne"
    try:
        m = snapshot.export(tmp_path)
        snapshot.export(daily, "dzienne")      # baza czyści komórki pogody (CASCADE) — przywracamy pogodę po teście
        assert m["wiersze"]["forest.wydzielenie"] >= 1 and (tmp_path / "manifest.json").exists()
        with connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM forest.wydzielenie WHERE source_id='test_snap'")
        r = snapshot.load(str(tmp_path), force=True)
        assert r["wczytano"]
        snapshot.load(str(daily), force=True, pakiet="dzienne")
        assert snapshot.load(str(tmp_path))["wczytano"] is False           # ta sama paczka drugi raz — bez zmian
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT gatunek_panujacy, ST_SRID(geom) FROM forest.wydzielenie WHERE source_id='test_snap'")
            assert cur.fetchone() == ("SO", 2180)
        bad = tmp_path / "forest.wydzielenie.part001.copy.gz"
        bad.write_bytes(bad.read_bytes() + b"x")
        with pytest.raises(ValueError):
            snapshot.load(str(tmp_path), force=True)                        # zła suma kontrolna
    finally:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM forest.wydzielenie WHERE source_id='test_snap'")
            cur.execute("DELETE FROM meta.snapshot WHERE zrodlo_url LIKE %s", (str(tmp_path) + "%",))


def test_display_name_from_forest_address():
    from grzyby.service import display_name
    assert display_name("04-08-2-09-163   -k   -00", 1) == "oddz. 163k, leśn. 09"
    assert display_name("04-01-2-09-127A  -b   -00", 4) == "oddz. 127Ab, leśn. 09"
    assert display_name("R050720009-1001  -cx  -00", 5) == "las poza LP 1001cx"
    assert display_name("DEMO BAL-001", 2) == "DEMO BAL-001" and display_name(None, 3) == "Wydzielenie 3"



@pytest.mark.db
def test_verify_rejects_incomplete_weather():
    from grzyby import snapshot
    problems = snapshot.verify()
    # baza deweloperska może mieć albo nie mieć pogody na dziś — ważne, że kontrola zwraca listę i nie rzuca wyjątkiem
    assert isinstance(problems, list)
    from datetime import date
    assert any("prognoza" in p for p in snapshot.verify(today=date(2030, 1, 1)))



@pytest.mark.db
def test_snapshot_splits_large_tables_into_parts(tmp_path, monkeypatch):
    from grzyby import snapshot
    monkeypatch.setattr(snapshot, "PART_BYTES", 200)          # wymuszenie wielu części
    m = snapshot.export(tmp_path, "baza")
    files = m["tabele"]["weather.komorka"]["pliki"] + m["tabele"]["forest.wydzielenie"]["pliki"]
    assert all((tmp_path / f["plik"]).exists() for f in files)
    import gzip
    rows = sum(gzip.decompress((tmp_path / f["plik"]).read_bytes()).count(b"\n")
               for f in m["tabele"]["forest.wydzielenie"]["pliki"])
    assert rows == m["wiersze"]["forest.wydzielenie"]


@pytest.mark.db
def test_sql_cell_ids_match_python():
    from grzyby.db import connect
    from grzyby.weather.openmeteo import cell_center, cell_id, ensure_cells_for_forests
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO forest.wydzielenie (source_id, external_id, attrs, geom)
                       VALUES ('test_cell','1','{}', ST_Multi(ST_Transform(ST_Buffer(ST_SetSRID(ST_MakePoint(22.2836, 49.3326),4326)::geography, 30)::geometry, 2180)))
                       RETURNING id""")
        wid = cur.fetchone()[0]
        conn.commit()
        try:
            ensure_cells_for_forests(conn, 0.1)
            cur.execute("SELECT komorka_id FROM forest.wydzielenie_komorka WHERE wydzielenie_id=%s", (wid,))
            assert cur.fetchone()[0] == cell_id(*cell_center(49.3326, 22.2836, 0.1), 0.1)
        finally:
            cur.execute("DELETE FROM forest.wydzielenie WHERE source_id='test_cell'")
            conn.commit()
