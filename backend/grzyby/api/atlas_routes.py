"""API atlasu. Tylko nauka: brak rozpoznawania ze zdjęcia, brak oceny jadalności okazu, brak wysyłania plików."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import atlas
from ..config import DATA_DIR
from ..db import connect

router = APIRouter(prefix="/api/atlas", tags=["atlas"])
UJECIA = ["mlody", "dojrzaly", "spod", "trzon", "przekroj"]


def _env(body: dict) -> dict:
    b = atlas.bezpieczenstwo()
    return {"komunikat": b["komunikat"], "wersja_robocza": atlas.is_draft(), "atlas_nie_robi": b["atlas_nie_robi"], **body}


def _photos(species_ids: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {s: [] for s in species_ids}
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, gatunek_id, ujecie, autor, licencja, licencja_url, zrodlo_url, adnotacje, przerobka,
                              zatwierdzil, zatwierdzono_utc, pobrano_utc
                       FROM atlas.zdjecie WHERE status='zatwierdzone' AND gatunek_id = ANY(%s) ORDER BY id""",
                    (species_ids,))
        for r in cur.fetchall():
            out[r[1]].append({
                "id": r[0], "url": f"/api/atlas/zdjecie/{r[0]}.jpg", "ujecie": r[2], "autor": r[3], "licencja": r[4],
                "licencja_url": r[5], "zrodlo_url": r[6], "adnotacje": r[7], "przerobka": r[8],
                "podpis": f"Fot. {r[3]}, {r[4]}" + (" (kadr — udostępniony na tej samej licencji)" if r[8] and "SA" in r[4] else ""),
                "zatwierdzil": r[9], "zatwierdzono_utc": r[10].isoformat() if r[10] else None,
                "pobrano_utc": r[11].isoformat() if r[11] else None,
            })
    return out


def _by_view(photos: list[dict]) -> dict[str, list[dict] | None]:
    """Ujęcia wymagane: lista zdjęć albo None (= brak). Nie podstawiamy zdjęć innego gatunku."""
    return {u: ([p for p in photos if p["ujecie"] == u] or None) for u in UJECIA}


def _species_json(sid: str, photos: list[dict]) -> dict:
    o = atlas.opisy()[sid]
    return {**o.model_dump(), "zdjecia": _by_view(photos), "zdjecia_inne": [p for p in photos if p["ujecie"] == "inne"],
            "brakujace_ujecia": [u for u, v in _by_view(photos).items() if v is None]}


@router.get("")
def index():
    ids = list(atlas.opisy())
    ph = _photos(ids)
    gat = [{"id": s, "nazwa_polska": o.nazwa_polska, "nazwa_naukowa": o.nazwa_naukowa, "status": o.status,
            "grupa": o.grupa, "liczba_zdjec": len(ph[s]),
            "brakujace_ujecia": [u for u, v in _by_view(ph[s]).items() if v is None]} for s, o in atlas.opisy().items()]
    par = [{"id": p.id, "jadalny": p.jadalny, "sobowtor": p.sobowtor, "ryzyko_pomylki": p.ryzyko_pomylki,
            "kategoria_sobowtora": p.kategoria_sobowtora} for p in atlas.pary().values()]
    return _env({"gatunki": gat, "pary": par})


@router.get("/gatunek/{sid}")
def species(sid: str):
    if sid not in atlas.opisy():
        raise HTTPException(404, "Brak gatunku w atlasie")
    ph = _photos([sid])
    related = [p.model_dump() for p in atlas.pary().values() if sid in (p.jadalny, p.sobowtor)]
    return _env({"gatunek": _species_json(sid, ph[sid]), "pary": related})


@router.get("/para/{pid}")
def pair(pid: str):
    p = atlas.pary().get(pid)
    if not p:
        raise HTTPException(404, "Brak pary w atlasie")
    ph = _photos([p.jadalny, p.sobowtor])
    return _env({"para": p.model_dump(), "jadalny": _species_json(p.jadalny, ph[p.jadalny]),
                 "sobowtor": _species_json(p.sobowtor, ph[p.sobowtor]),
                 "ostrzezenie": "Pojedyncza cecha nigdy nie wystarcza. Okazy bywają nietypowe (wiek, pogoda, uszkodzenia)."})


@router.get("/bezpieczenstwo")
def safety():
    b = atlas.bezpieczenstwo()
    return _env({k: b[k] for k in ("zasady_zbioru", "mity", "zatrucie", "punkty_grzyboznawcze", "zrodla")})


@router.get("/zdjecie/{pid}.jpg")
def photo(pid: int):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT plik FROM atlas.zdjecie WHERE id=%s AND status='zatwierdzone'", (pid,))
        r = cur.fetchone()
    if not r:
        raise HTTPException(404, "Zdjęcie niedostępne")  # niezatwierdzone nie trafiają do aplikacji
    f = (DATA_DIR / r[0]).resolve()
    if DATA_DIR.resolve() not in f.parents or not f.is_file():
        raise HTTPException(404, "Brak pliku")
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=2592000, immutable"})
