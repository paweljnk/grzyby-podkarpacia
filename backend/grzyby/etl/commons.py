"""Kandydaci zdjęć z Wikimedia Commons → atlas.zdjecie (status 'do_weryfikacji').

Pobieramy tylko pliki z licencją z listy dozwolonej (atlas/config_zdjecia.yaml). Autor, licencja i link
do strony pliku pochodzą z `extmetadata` API MediaWiki; plik bez tych pól jest pomijany (nie zgadujemy).
Zdjęcie trafia do aplikacji dopiero po ręcznym zatwierdzeniu (`grzyby.cli atlas zatwierdz`).
"""
from __future__ import annotations

import html
import logging
import re
from pathlib import Path

from ..atlas import photo_config
from ..config import DATA_DIR
from ..db import connect, import_run
from .http import HttpClient, SourceUnavailable

log = logging.getLogger(__name__)
API = "https://commons.wikimedia.org/w/api.php"
ATLAS_IMG_DIR = DATA_DIR / "atlas"


def strip_html(s: str | None) -> str | None:
    if s is None:
        return None
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip() or None


def normalize_license(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().replace("_", " ")
    n = re.sub(r"(?i)^cc[- ]?zero$|^cc0( 1\.0)?$", "CC0", n)
    n = re.sub(r"(?i)^public domain.*$|^pd.*$", "Public domain", n)
    n = re.sub(r"(?i)^cc[- ]by[- ]sa[- ](\d\.\d).*$", r"CC BY-SA \1", n)
    n = re.sub(r"(?i)^cc[- ]by[- ](\d\.\d).*$", r"CC BY \1", n)
    return n


def parse_candidates(payload: dict, allowed: set[str]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Zwraca (akceptowane, odrzucone[(tytuł, powód)]) z odpowiedzi API (prop=imageinfo, extmetadata)."""
    ok, rejected = [], []
    for page in (payload.get("query", {}).get("pages") or {}).values():
        title = page.get("title", "?")
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            rejected.append((title, "brak imageinfo"))
            continue
        if not str(info.get("mime", "")).startswith("image/jpeg"):
            rejected.append((title, f"format {info.get('mime')}"))
            continue
        meta = info.get("extmetadata") or {}
        get = lambda k: (meta.get(k) or {}).get("value")
        lic = normalize_license(get("LicenseShortName"))
        author = strip_html(get("Artist"))
        if lic not in allowed:
            rejected.append((title, f"licencja {get('LicenseShortName')!r} spoza listy"))
            continue
        if not author:
            rejected.append((title, "brak autora"))
            continue
        ok.append({
            "autor": author, "licencja": lic, "licencja_url": get("LicenseUrl"),
            "zrodlo_url": info.get("descriptionurl"), "plik_url": info.get("thumburl") or info.get("url"),
            "sha1": info.get("sha1"), "szerokosc": info.get("thumbwidth") or info.get("width"),
            "wysokosc": info.get("thumbheight") or info.get("height"),
            "opis_zrodla": (strip_html(get("ImageDescription")) or "")[:500] or None,
        })
    return ok, rejected


def fetch_candidates(species_id: str, limit: int = 30) -> dict:
    cfg = photo_config()
    allowed = set(cfg["licencje_dozwolone"])
    conn = connect()
    added, rejected = 0, []
    with HttpClient(min_interval_s=1.0) as client:
        try:
            with import_run(conn, "wikimedia_commons", "atlas.zdjecie", species_id) as run:
                for cat in cfg["kategorie_commons"].get(species_id, []):
                    params = {"action": "query", "format": "json", "generator": "categorymembers",
                              "gcmtitle": cat, "gcmtype": "file", "gcmlimit": limit, "prop": "imageinfo",
                              "iiprop": "url|extmetadata|size|mime|sha1", "iiurlwidth": cfg["szerokosc_px"]}
                    ok, rej = parse_candidates(client.get(API, params=params).json(), allowed)
                    rejected += rej
                    for c in ok:
                        dest = ATLAS_IMG_DIR / species_id / f"{c['sha1']}.jpg"
                        client.download(c["plik_url"], dest)
                        with conn.cursor() as cur:
                            cur.execute(
                                """INSERT INTO atlas.zdjecie (gatunek_id, autor, licencja, licencja_url, zrodlo_url,
                                     plik_url, plik, sha1, szerokosc, wysokosc, opis_zrodla)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (zrodlo_url) DO NOTHING""",
                                (species_id, c["autor"], c["licencja"], c["licencja_url"], c["zrodlo_url"],
                                 c["plik_url"], str(dest.relative_to(DATA_DIR)), c["sha1"], c["szerokosc"],
                                 c["wysokosc"], c["opis_zrodla"]))
                            added += cur.rowcount
                run.records = added
                conn.commit()
        except SourceUnavailable as e:
            log.warning("Wikimedia Commons niedostępne: %s", e)
            return {"dodano": 0, "blad": str(e)}
    conn.close()
    return {"dodano": added, "odrzucono": len(rejected), "powody_odrzucenia": rejected[:20]}


def approve(photo_id: int, ujecie: str, reviewer: str, adnotacje: list | None = None, uwagi: str | None = None) -> None:
    import json
    if ujecie not in ("mlody", "dojrzaly", "spod", "trzon", "przekroj", "inne"):
        raise ValueError(f"nieznane ujęcie {ujecie}")
    if not reviewer.strip():
        raise ValueError("wymagane imię i nazwisko osoby zatwierdzającej")
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("""UPDATE atlas.zdjecie SET status='zatwierdzone', ujecie=%s, zatwierdzil=%s, zatwierdzono_utc=now(),
                         adnotacje=%s, uwagi=COALESCE(%s, uwagi) WHERE id=%s AND plik IS NOT NULL""",
                    (ujecie, reviewer.strip(), json.dumps(adnotacje or []), uwagi, photo_id))
        if cur.rowcount != 1:
            raise ValueError(f"brak zdjęcia {photo_id} z pobranym plikiem")
    conn.commit()
    conn.close()


def reject(photo_id: int, reviewer: str, reason: str) -> None:
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("UPDATE atlas.zdjecie SET status='odrzucone', zatwierdzil=%s, zatwierdzono_utc=now(), uwagi=%s WHERE id=%s",
                    (reviewer, reason, photo_id))
    conn.commit()
    conn.close()
