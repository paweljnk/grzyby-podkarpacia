"""API katalogu gatunków (przeglądanie) i podpowiedzi „Pomóż oznaczyć”.
Zdjęcie użytkownika nie jest wysyłane na serwer — porównanie odbywa się w telefonie."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from .. import katalog
from ..db import connect

router = APIRouter(prefix="/api/katalog", tags=["katalog"])
COLS = ["id", "nazwa_naukowa", "nazwa_polska", "nazwy_polskie", "rodzaj", "rodzina", "rzad", "klasa", "obserwacje_pl",
        "obserwacje_woj", "wikidata", "wiki_tytul", "wiki_url", "opis_wstep", "opis_budowa", "opis_wystepowanie",
        "opis_podobne", "opis_ochrona", "cechy", "siedlisko", "zdjecie_url", "zdjecie_miniatura", "zdjecie_strona",
        "zdjecie_autor", "zdjecie_licencja", "zdjecie_licencja_url", "pobrano_utc"]
LIST_COLS = ["id", "nazwa_naukowa", "nazwa_polska", "rodzaj", "rodzina", "obserwacje_pl", "obserwacje_woj",
             "zdjecie_miniatura", "zdjecie_autor", "zdjecie_licencja", "cechy", "siedlisko"]
UWAGA = ("Katalog to materiał poglądowy — nie służy do oznaczania okazów i nie ocenia jadalności. "
         "Każdy zebrany grzyb, co do którego masz wątpliwość, pokaż grzyboznawcy (punkty Państwowej Inspekcji Sanitarnej).")
ZRODLA = [
    {"nazwa": "GBIF.org", "opis": "lista gatunków i liczba obserwacji", "licencja": "CC0 / CC BY (zbiory danych)"},
    {"nazwa": "Wikidata", "opis": "cechy budowy (P783–P788)", "licencja": "CC0"},
    {"nazwa": "Wikipedia, wolna encyklopedia", "opis": "opisy gatunków", "licencja": "CC BY-SA 4.0"},
    {"nazwa": "Wikimedia Commons", "opis": "zdjęcia (autor i licencja przy zdjęciu)", "licencja": "per plik"},
]


def _rows(where: str = "", params: tuple = (), cols: list[str] = COLS) -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(cols)} FROM atlas.katalog {where}", params)
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _labels(sp: dict, c: dict) -> dict:
    """Cechy z polskimi etykietami do wyświetlenia."""
    return {c["etykiety"].get(k, k): [katalog.label(k, v, c) for v in vals] for k, vals in (sp.get("cechy") or {}).items()}


@router.get("")
def list_species(q: str = "", rodzina: str = "", sort: str = Query("woj", pattern="^(woj|pl|nazwa)$"),
                 offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=200)):
    where, params = [], []
    if q.strip():
        where.append("(nazwa_polska ILIKE %s OR nazwa_naukowa ILIKE %s OR array_to_string(nazwy_polskie, ' ') ILIKE %s)")
        params += [f"%{q.strip()}%"] * 3
    if rodzina:
        where.append("rodzina = %s")
        params.append(rodzina)
    order = {"woj": "obserwacje_woj DESC NULLS LAST, obserwacje_pl DESC", "pl": "obserwacje_pl DESC",
             "nazwa": "lower(coalesce(nazwa_polska, nazwa_naukowa))"}[sort]
    w = ("WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM atlas.katalog {w}", params)
        total = cur.fetchone()[0]
        cur.execute("SELECT rodzina, count(*) FROM atlas.katalog WHERE rodzina IS NOT NULL GROUP BY 1 ORDER BY 1")
        fam = [{"rodzina": r[0], "liczba": r[1]} for r in cur.fetchall()]
        cur.execute("SELECT max(pobrano_utc) FROM atlas.katalog")
        when = cur.fetchone()[0]
    rows = _rows(f"{w} ORDER BY {order} OFFSET %s LIMIT %s", tuple(params + [offset, limit]), LIST_COLS)
    return {"uwaga": UWAGA, "zrodla": ZRODLA, "pobrano_utc": when.isoformat() if when else None,
            "razem": total, "rodziny": fam, "gatunki": rows}


@router.get("/klucz")
def key(request: Request):
    c = katalog.cfg()
    answers = {k: request.query_params.getlist(k) for k in request.query_params.keys()}
    pytania = [{"id": q["id"], "pytanie": q["pytanie"], "wiele": q.get("wiele", False),
                "odpowiedzi": [{"id": k, "etykieta": v["etykieta"]} for k, v in q["odpowiedzi"].items()]} for q in c["pytania"]]
    if not any(answers.values()):
        return {"uwaga": UWAGA, "pytania": pytania, "wyniki": [], "ostrzezenia": []}
    res = katalog.match(_rows(cols=LIST_COLS), answers, c)[: c["wynikow"]]
    warn = [c["ostrzezenie_blaszki"]] if "blaszki" in answers.get("hymenium", []) else []
    return {"uwaga": UWAGA, "pytania": pytania, "ostrzezenia": warn, "wyniki": [
        {**r["gatunek"], "punkty": r["punkty"], "zgodne": r["zgodne"], "niezgodne": r["niezgodne"],
         "brak_danych": r["brak_danych"], "ostrzezenie_rodzaj": r["ostrzezenie_rodzaj"]} for r in res]}


@router.get("/{sid}")
def species(sid: str):
    rows = _rows("WHERE id = %s", (sid,))
    if not rows:
        raise HTTPException(404, "Brak gatunku w katalogu")
    sp = rows[0]
    c = katalog.cfg()
    sp["pobrano_utc"] = sp["pobrano_utc"].isoformat() if sp["pobrano_utc"] else None
    sp["cechy_opis"] = _labels(sp, c)
    sp["ostrzezenie_rodzaj"] = sp.get("rodzaj") in c["rodzaje_smiertelne"]
    similar = _rows("WHERE rodzaj = %s AND id <> %s ORDER BY obserwacje_woj DESC NULLS LAST LIMIT 8",
                    (sp.get("rodzaj"), sid), LIST_COLS) if sp.get("rodzaj") else []
    return {"uwaga": UWAGA, "zrodla": ZRODLA, "gatunek": sp, "ten_sam_rodzaj": similar}
