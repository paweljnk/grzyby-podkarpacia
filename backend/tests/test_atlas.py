"""Atlas (Etap 4b): treści, zasady zdjęć i zakaz oceny jadalności okazów."""
import json
import re

import pytest

from grzyby import atlas
from grzyby.etl.commons import normalize_license, parse_candidates

ALLOWED = set(atlas.photo_config()["licencje_dozwolone"])
FORBIDDEN_ROUTE = re.compile(r"rozpozn|identyf|ocen|jadaln|upload|klasyfik|predict|scan", re.I)
FORBIDDEN_KEYS = {"pewnosc", "prawdopodobienstwo", "jadalnosc_okazu", "czy_jadalny", "wynik_rozpoznania", "confidence"}


def test_content_is_consistent():
    assert atlas.validate() == []


def test_mvp_species_and_their_doubles_present():
    ids = set(atlas.opisy())
    assert {"boletus_edulis", "imleria_badia", "cantharellus_cibarius"} <= ids
    assert {"tylopilus_felleus", "rubroboletus_satanas", "hygrophoropsis_aurantiaca"} <= ids
    for p in atlas.pary().values():
        assert any(c.waga == "kluczowa" for c in p.cechy) and p.ryzyko_pomylki


def test_fixed_notice_text():
    k = atlas.bezpieczenstwo()["komunikat"]
    assert "Atlas służy do nauki" in k and "100% pewnością" in k and "grzyboznawcy" in k


def test_no_taste_test_as_a_method():
    txt = json.dumps({"o": [o.model_dump() for o in atlas.opisy().values()],
                      "p": [p.model_dump() for p in atlas.pary().values()]}, ensure_ascii=False).lower()
    # smak może się pojawić tylko jako ostrzeżenie "nie próbuj", nigdy jako cecha do sprawdzenia
    for p in atlas.pary().values():
        for c in p.cechy:
            assert "smak" not in c.cecha.lower()
    assert "spróbuj" not in txt


def test_draft_until_approved():
    assert atlas.is_draft() is True


@pytest.mark.parametrize("raw,norm", [("CC BY-SA 4.0", "CC BY-SA 4.0"), ("cc-by-sa-3.0", "CC BY-SA 3.0"),
                                       ("CC BY 2.0", "CC BY 2.0"), ("CC0", "CC0"), ("Public domain", "Public domain"),
                                       ("CC BY-NC-SA 2.0", "CC BY-NC-SA 2.0")])
def test_license_normalization(raw, norm):
    assert normalize_license(raw) == norm


def _page(title, lic, artist="<a href='x'>Jan Kowalski</a>", mime="image/jpeg"):
    return {"title": title, "imageinfo": [{"mime": mime, "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
            "thumburl": "https://upload.wikimedia.org/x.jpg", "sha1": "abc", "thumbwidth": 1024, "thumbheight": 768,
            "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": artist},
                            "LicenseUrl": {"value": "https://creativecommons.org/"}}}]}


def test_candidates_filtered_by_license_author_and_format():
    payload = {"query": {"pages": {
        "1": _page("File:A.jpg", "CC BY-SA 4.0"),
        "2": _page("File:B.jpg", "CC BY-NC-SA 2.0"),
        "3": _page("File:C.jpg", "CC BY 4.0", artist=""),
        "4": _page("File:D.png", "CC0", mime="image/png"),
        "5": {"title": "File:E.jpg"},
    }}}
    ok, rejected = parse_candidates(payload, ALLOWED)
    assert [c["zrodlo_url"].rsplit("/", 1)[1] for c in ok] == ["File:A.jpg"]
    assert ok[0]["autor"] == "Jan Kowalski" and ok[0]["licencja"] == "CC BY-SA 4.0"
    assert len(rejected) == 4


# ------------------------------------------------------------ API (baza)
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import os
    os.environ["GRZYBY_SNAPSHOT_AUTO"] = "0"
    from grzyby.api.main import app
    with TestClient(app) as c:
        yield c


@pytest.mark.db
def test_no_endpoint_evaluates_a_specimen(client):
    from grzyby.api.main import app
    for r in app.routes:
        path = getattr(r, "path", "")
        methods = getattr(r, "methods", set()) or set()
        if path.startswith("/api"):
            assert methods <= {"GET", "HEAD"}, f"{path}: tylko odczyt, bez wysyłania zdjęć ({methods})"
            assert not FORBIDDEN_ROUTE.search(path), path
    docs = [client.get("/api/atlas").json(), client.get("/api/atlas/bezpieczenstwo").json()]
    docs += [client.get(f"/api/atlas/gatunek/{s}").json() for s in atlas.opisy()]
    docs += [client.get(f"/api/atlas/para/{p}").json() for p in atlas.pary()]

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    for d in docs:
        assert not (set(keys(d)) & FORBIDDEN_KEYS)
        assert d["komunikat"] and d["wersja_robocza"] is True
    rk = client.get("/api/ranking?species=boletus_edulis&lat=49.33&lon=22.28&radius_km=15&dataset=demo").json()
    assert "jadaln" not in json.dumps(rk["miejsca"], ensure_ascii=False).lower()
    # wysłanie zdjęcia do oceny jest niemożliwe
    assert client.post("/api/atlas/gatunek/boletus_edulis", files={"f": ("x.jpg", b"x")}).status_code in (404, 405)


@pytest.mark.db
def test_missing_views_are_marked_not_substituted(client):
    g = client.get("/api/atlas/gatunek/rubroboletus_satanas").json()["gatunek"]
    for u in ("mlody", "dojrzaly", "spod", "trzon", "przekroj"):
        if g["zdjecia"][u] is None:
            assert u in g["brakujace_ujecia"]
        else:
            assert all(p["autor"] and p["licencja"] for p in g["zdjecia"][u])


@pytest.mark.db
def test_only_approved_photos_published_with_author_and_license(client, tmp_path):
    from grzyby.config import DATA_DIR
    from grzyby.db import connect
    from grzyby.etl.commons import approve
    f = DATA_DIR / "atlas" / "_test" / "t.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\xff\xd8\xff\xd9")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO atlas.zdjecie (gatunek_id, autor, licencja, zrodlo_url, plik)
                       VALUES ('boletus_edulis','Test Autor','CC BY-SA 4.0','https://test.invalid/1', %s) RETURNING id""",
                    (str(f.relative_to(DATA_DIR)),))
        pid = cur.fetchone()[0]
    try:
        assert client.get(f"/api/atlas/zdjecie/{pid}.jpg").status_code == 404           # do_weryfikacji
        assert client.get("/api/atlas/gatunek/boletus_edulis").json()["gatunek"]["zdjecia"]["przekroj"] is None
        with pytest.raises(ValueError):
            approve(pid, "przekroj", "  ")                                                  # wymagana osoba
        approve(pid, "przekroj", "Testowy Mykolog", [{"x": 0.5, "y": 0.5, "tekst": "miąższ"}])
        g = client.get("/api/atlas/gatunek/boletus_edulis").json()["gatunek"]
        ph = g["zdjecia"]["przekroj"][0]
        assert ph["autor"] == "Test Autor" and ph["licencja"] == "CC BY-SA 4.0" and "Fot. Test Autor" in ph["podpis"]
        assert "przekroj" not in g["brakujace_ujecia"]
        assert client.get(f"/api/atlas/zdjecie/{pid}.jpg").status_code == 200
    finally:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM atlas.zdjecie WHERE id=%s", (pid,))
        f.unlink()
