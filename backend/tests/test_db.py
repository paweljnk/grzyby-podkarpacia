"""Testy integracyjne na działającej bazie (make test-db)."""
import pytest

from grzyby.check_data import LAYERS, layer_stats
from grzyby.db import connect, import_run
from grzyby.etl.http import SourceUnavailable

pytestmark = pytest.mark.db


@pytest.fixture
def conn():
    c = connect()
    yield c
    c.rollback()
    c.close()


def test_schemas_and_srid(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT Find_SRID('forest', 'wydzielenie', 'geom'), Find_SRID('protection','forma_ochrony','geom')")
        assert cur.fetchone() == (2180, 2180)
        cur.execute("SELECT count(*) FROM information_schema.schemata WHERE schema_name='demo'")
        assert cur.fetchone()[0] == 1


def test_import_log_records_skipped_source(conn):
    with pytest.raises(SourceUnavailable):
        with import_run(conn, "test_zrodlo", "test.target", "t"):
            raise SourceUnavailable("brak dostępu")
    with conn.cursor() as cur:
        cur.execute("SELECT status, message FROM meta.import_log WHERE source_id='test_zrodlo' ORDER BY id DESC LIMIT 1")
        status, msg = cur.fetchone()
        cur.execute("DELETE FROM meta.import_log WHERE source_id='test_zrodlo'")
    conn.commit()
    assert status == "skipped" and "brak dostępu" in msg


def test_layer_stats_runs_for_all_layers(conn):
    with conn.cursor() as cur:
        for table, _, _ in LAYERS:
            st = layer_stats(cur, table)
            assert st["rekordy"] >= 0 and isinstance(st["braki"], dict)


def test_mapping_missing_is_logged_as_skipped(conn):
    from grzyby.etl.vector import MappingMissing
    with pytest.raises(MappingMissing):
        with import_run(conn, "test_mapowanie", "test.target"):
            raise MappingMissing("brak mapowania")
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM meta.import_log WHERE source_id='test_mapowanie' ORDER BY id DESC LIMIT 1")
        status = cur.fetchone()[0]
        cur.execute("DELETE FROM meta.import_log WHERE source_id='test_mapowanie'")
    conn.commit()
    assert status == "skipped"


def test_dem_rasters_registered_in_2180(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), bool_and(crs='EPSG:2180'), bool_and(pochodzenie='model') FROM terrain.raster")
        n, crs_ok, prov_ok = cur.fetchone()
    if n == 0:
        pytest.skip("brak zaimportowanych rastrów — uruchom make import-pilot")
    assert crs_ok and prov_ok


def test_zonal_stats_on_real_dem_inside_rolled_back_transaction(conn):
    """Poligon testowy (nie dane rzeczywiste) — transakcja wycofywana, nic nie zostaje w bazie."""
    from grzyby.config import pilot_config
    from grzyby.etl.dem import compute_zonal_for_area
    with conn.cursor() as cur:
        cur.execute("SELECT warstwa, sciezka FROM terrain.raster WHERE obszar_id='baligrod'")
        paths = {w: __import__("pathlib").Path(p) for w, p in cur.fetchall()}
        if len(paths) < 3 or not all(p.exists() for p in paths.values()):
            pytest.skip("brak rastrów Baligrodu — uruchom make import-pilot")
        # 500 x 500 m wokół szczytu Łopiennika (stok górski → wyraźne nachylenie)
        cur.execute("""INSERT INTO forest.wydzielenie (source_id, external_id, obszar_id, attrs, geom)
                       VALUES ('test', 't1', 'baligrod', '{}',
                         ST_Multi(ST_Transform(ST_Buffer(ST_SetSRID(ST_MakePoint(22.3388, 49.2458), 4326)::geography, 250)::geometry, 2180)))""")
    flat = pilot_config()["teren"]["prog_plaskiego_terenu_deg"]
    n = compute_zonal_for_area(conn, "baligrod", paths, 25.0, flat, None)
    with conn.cursor() as cur:
        cur.execute("""SELECT t.n_pikseli, t.wys_max, t.nachylenie_sr_deg, t.pochodzenie FROM terrain.wydzielenie_teren t
                       JOIN forest.wydzielenie w ON w.id=t.wydzielenie_id WHERE w.source_id='test'""")
        npx, wmax, slope, prov = cur.fetchone()
    conn.rollback()
    assert n == 1 and npx > 250          # koło r=250 m ≈ 314 pikseli 25 m
    assert 1000 < wmax < 1120 and slope > 5 and prov == "model"



def test_weather_series_prefers_complete_precipitation(conn):
    """Doba z reanalizą bez opadu i analizą z opadem → wybór analizy (błąd znaleziony na danych z 2026-10-17)."""
    from datetime import date
    from grzyby.repo import weather_series
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO weather.komorka VALUES ('test_c', 50, 22, 0.1,
                         ST_Transform(ST_MakeEnvelope(21.95,49.95,22.05,50.05,4326),2180))""")
        cur.execute("""INSERT INTO weather.dzien (komorka_id, data_lokalna, typ, godzin, opad_mm, temp_sr_c, pochodzenie)
                       VALUES ('test_c','2026-10-10','reanaliza',24,NULL,8,'model'),
                              ('test_c','2026-10-10','analiza',24,3.2,8.5,'model'),
                              ('test_c','2026-10-09','reanaliza',24,1.0,9,'model'),
                              ('test_c','2026-10-09','analiza',24,2.0,9,'model')""")
    days, _ = weather_series(conn, "real", "test_c", date(2026, 10, 9), date(2026, 10, 10))
    conn.rollback()
    assert [(d.data.day, d.typ, d.opad_mm) for d in days] == [(9, "reanaliza", 1.0), (10, "analiza", 3.2)]
