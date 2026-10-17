"""Testy API na bazie z danymi demo (make demo-data)."""
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def client():
    import os
    os.environ["GRZYBY_DEMO_AUTOREFRESH"] = "1"
    import os
    os.environ["GRZYBY_SNAPSHOT_AUTO"] = "0"
    from grzyby.api.main import app
    with TestClient(app) as c:
        yield c


Q = "species=boletus_edulis&lat=49.33&lon=22.28&radius_km=15&dataset=demo"


def test_ranking_has_breakdown_gates_completeness_and_reasons(client):
    for cal in ("on", "off"):
        r = client.get(f"/api/ranking?{Q}&calendar={cal}&pokaz_wykluczone=true")
        assert r.status_code == 200
        d = r.json()
        assert d["zbior_danych"] == "demo" and any("DEMONSTRACYJNE" in w for w in d["ostrzezenia"])
        m = d["miejsca"][0]
        for k in ("A", "B", "C", "D", "bramki", "kompletnosc", "jakosc", "uzasadnienie", "wynik", "rekomendowane"):
            assert k in m
        assert 0 <= (m["wynik"] or 0) <= 100
        assert m["uzasadnienie"]
        if cal == "off":
            assert all(x["D"] == 0 for x in d["miejsca"])


def test_ranking_sorted_and_excluded_hidden_by_default(client):
    d = client.get(f"/api/ranking?{Q}").json()
    scores = [m["wynik"] for m in d["miejsca"]]
    assert scores == sorted(scores, reverse=True)
    assert all(m["rekomendowane"] for m in d["miejsca"])


def test_national_park_gate_present_in_demo(client):
    d = client.get("/api/ranking?species=boletus_edulis&lat=49.25&lon=22.45&radius_km=15&dataset=demo"
                   "&pokaz_wykluczone=true&limit=500").json()
    assert any(any(g["kod"] == "zakaz" for g in m["bramki"]) for m in d["miejsca"])


def test_real_dataset_is_not_mixed_with_demo(client):
    d = client.get("/api/ranking?species=boletus_edulis&lat=49.33&lon=22.28&radius_km=15&dataset=real").json()
    assert d["zbior_danych"] == "real"
    assert not any(m["nazwa"].startswith("DEMO") for m in d["miejsca"])


def test_place_card_week_calendar_compare(client):
    pid = client.get(f"/api/ranking?{Q}").json()["miejsca"][0]["id"]
    card = client.get(f"/api/miejsce/{pid}?species=boletus_edulis&dataset=demo&calendar=on").json()["miejsce"]
    assert card["dostep"]["uwagi"] and card["dojazd"]["opis"] and card["kalendarz"]["typ_biodynamiczny"]
    wk = client.get(f"/api/miejsce/{pid}/7dni?species=boletus_edulis&dataset=demo").json()
    assert len(wk["dni"]) == 7 and wk["werdykt"]["decyzja"] in {"dzis", "poczekaj", "brak_rekomendacji"}
    cal = client.get(f"/api/kalendarz?species=boletus_edulis&month=2026-10&lat=49.33&lon=22.28&dataset=demo").json()
    assert len(cal["dni"]) == 31
    assert client.get(f"/api/porownanie?ids={pid}&species=boletus_edulis&dataset=demo").status_code == 422


def test_validation_errors(client):
    assert client.get("/api/ranking?species=nieznany&lat=49.3&lon=22.3").status_code == 404
    assert client.get("/api/ranking?species=boletus_edulis&lat=52.2&lon=21.0").status_code == 422
    assert client.get(f"/api/ranking?{Q}&calendar=maybe").status_code == 422


def test_map_bbox_modes_and_coverage(client):
    small = client.get("/api/mapa?species=boletus_edulis&bbox=22.20,49.28,22.32,49.36&dataset=demo").json()
    assert small["tryb"] == "wydzielenia"
    for f in small["geojson"]["features"]:
        p = f["properties"]
        assert "pewnosc" in p and "warunki_min" in p and "warunki_max" in p
    big = client.get("/api/mapa?species=boletus_edulis&bbox=21.1,49.0,23.6,50.85&dataset=demo").json()
    assert big["tryb"] == "przybliz" and big["geojson"]["features"] == []
    assert client.get("/api/mapa?species=boletus_edulis&bbox=1,2,3&dataset=demo").status_code == 422
    cov = client.get("/api/pokrycie?bbox=21.1,49.0,23.6,50.85")
    assert cov.status_code == 200 and cov.json()["type"] == "FeatureCollection"


def test_ranking_exposes_conditions_and_certainty_separately(client):
    m = client.get(f"/api/ranking?{Q}&limit=3").json()["miejsca"][0]
    assert m["warunki"] == m["wynik"] and 0 <= m["pewnosc"] <= 1 and m["pewnosc_opis"] in {"wysoka", "srednia", "niska"}
    assert m["warunki_min"] <= m["warunki"] <= m["warunki_max"]
    card = client.get(f"/api/miejsce/{m['id']}?species=boletus_edulis&dataset=demo").json()["miejsce"]
    kinds = {a["atrybut"]: a["oznaczenie"] for a in card["atrybuty"]}
    assert kinds["Pełny skład gatunkowy z udziałami"] == "brak"
    assert set(kinds.values()) <= {"źródłowa", "model", "brak"}
