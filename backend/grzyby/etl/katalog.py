"""Katalog gatunków grzybów do przeglądania.

Źródła (sprawdzone rekonesansem `scripts/recon5.py`):
- GBIF: lista gatunków najczęściej notowanych w Polsce (facet speciesKey), liczba obserwacji w rejonie województwa,
  systematyka i polskie nazwy zwyczajowe;
- Wikidata: element gatunku (P225), zdjęcie (P18), artykuł w pl.wikipedia, cechy mykologiczne P783–P788
  (P789 „jadalność” celowo pomijamy — aplikacja nie ocenia jadalności);
- Wikipedia PL: wstęp i sekcje „Morfologia”, „Występowanie i siedlisko”, „Gatunki podobne”, „Ochrona” (CC BY-SA 4.0);
- Wikimedia Commons: miniatura zdjęcia z autorem i licencją (tylko licencje z atlas/config_zdjecia.yaml).

To materiał poglądowy, nie klucz do oznaczania okazów.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import unquote

from ..config import load_yaml, ROOT
from ..db import connect, import_run
from .commons import normalize_license, strip_html
from .http import HttpClient, SourceUnavailable

log = logging.getLogger(__name__)
GBIF = "https://api.gbif.org/v1"
SPARQL = "https://query.wikidata.org/sparql"
PLWIKI = "https://pl.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
MONTH_S = 30 * 86400


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


# ---------------------------------------------------------------- Wikipedia
def split_sections(text: str) -> dict[str, str]:
    """Tekst z explaintext + exsectionformat=wiki → {nagłówek poziomu 2: treść (z podsekcjami)}."""
    out: dict[str, str] = {}
    parts = re.split(r"^(==[^=].*?==)\s*$", text, flags=re.M)
    out["_wstep"] = parts[0].strip()
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].strip("= ").strip()
        out[title] = parts[i + 1].strip()
    return out


def clean_section(s: str, limit: int) -> str | None:
    s = re.sub(r"^(=+)\s*(.*?)\s*\1\s*$", r"\2:", s, flags=re.M)      # podsekcje (=== Kapelusz ===) → „Kapelusz:”
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    if not s:
        return None
    if len(s) > limit:
        cut = s[:limit]
        s = cut[:max(cut.rfind(". "), cut.rfind("\n"), limit // 2) + 1].strip() + " […]"
    return s


def pick_sections(text: str, cfg: dict) -> dict[str, str | None]:
    secs = split_sections(text)
    out = {"opis_wstep": clean_section(secs.get("_wstep", ""), 900)}
    for field, names in cfg["sekcje_wikipedii"].items():
        val = next((secs[n] for n in names if n in secs), None)
        out[field] = clean_section(val, cfg["max_znakow_sekcji"]) if val else None
    return out


def habitat_tags(text: str | None, cfg: dict) -> dict[str, list[str]]:
    """Cechy siedliska z opisu występowania: dopasowanie początków wyrazów (np. 'świerk' → świerkami)."""
    if not text:
        return {}
    t = text.lower()
    out = {}
    for group in ("gleba", "drzewa"):
        hits = [label for label, stems in cfg[group].items()
                if any(re.search(r"(?<![a-ząćęłńóśźż])" + re.escape(s), t) for s in stems)]
        if hits:
            out[group] = hits
    return out


# ---------------------------------------------------------------- GBIF
def gbif_species_list(client: HttpClient, cfg: dict) -> list[dict]:
    counts_pl: dict[int, int] = {}
    counts_woj: dict[int, int] = {}
    box = cfg["prostokat_wojewodztwa"]
    for key in cfg["klasy_gbif"].values():
        base = {"country": "PL", "taxonKey": key, "limit": 0, "facet": "speciesKey", "facetLimit": cfg["facet_limit"]}
        for target, extra in ((counts_pl, {}), (counts_woj, {"decimalLatitude": box["lat"], "decimalLongitude": box["lon"]})):
            r = client.get(f"{GBIF}/occurrence/search", params={**base, **extra}, max_age_s=MONTH_S).json()
            for f in r.get("facets", []):
                for c in f["counts"]:
                    target[int(c["name"])] = target.get(int(c["name"]), 0) + c["count"]
    ranked = sorted(counts_pl, key=lambda k: -counts_pl[k])
    out = []
    for k in ranked:
        if len(out) >= cfg["limit_gatunkow"]:
            break
        sp = client.get(f"{GBIF}/species/{k}", max_age_s=MONTH_S).json()
        if sp.get("rank") != "SPECIES" or not sp.get("canonicalName"):
            continue
        vn = client.get(f"{GBIF}/species/{k}/vernacularNames", params={"limit": 200}, max_age_s=MONTH_S).json()
        pl = []
        for v in vn.get("results", []):
            if v.get("language") in ("pol", "pl") and v.get("vernacularName"):
                n = v["vernacularName"].strip()
                if n.lower() not in [x.lower() for x in pl]:
                    pl.append(n)
        out.append({"gbif_key": k, "nazwa_naukowa": sp["canonicalName"], "rodzaj": sp.get("genus"), "rodzina": sp.get("family"),
                    "rzad": sp.get("order"), "klasa": sp.get("class"), "nazwy_polskie": pl,
                    "obserwacje_pl": counts_pl.get(k, 0), "obserwacje_woj": counts_woj.get(k, 0)})
    return out


# ---------------------------------------------------------------- Wikidata
def wikidata(client: HttpClient, names: list[str], cfg: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for batch in chunks(names, 80):
        values = " ".join(json.dumps(n) for n in batch)
        q = f"""SELECT ?name ?item ?plwiki ?image WHERE {{ VALUES ?name {{ {values} }}
          ?item wdt:P225 ?name .
          OPTIONAL {{ ?item wdt:P18 ?image }}
          OPTIONAL {{ ?plwiki schema:about ?item ; schema:isPartOf <https://pl.wikipedia.org/> }} }}"""
        res = client.get(SPARQL, params={"query": q, "format": "json"}, max_age_s=MONTH_S).json()
        for b in res["results"]["bindings"]:
            n = b["name"]["value"]
            o = out.setdefault(n, {"item": b["item"]["value"].rsplit("/", 1)[-1], "cechy": {}})
            if "plwiki" in b and "plwiki" not in o:
                o["plwiki"] = unquote(b["plwiki"]["value"].rsplit("/wiki/", 1)[-1]).replace("_", " ")
            if "image" in b and "image" not in o:
                o["image"] = "File:" + unquote(b["image"]["value"].rsplit("/Special:FilePath/", 1)[-1])
    props = cfg["wikidata_cechy"]
    pmap = {v: k for k, v in props.items()}
    items = {o["item"]: n for n, o in out.items()}
    for batch in chunks(list(items), 80):
        q = f"""SELECT ?item ?p ?valLabel WHERE {{ VALUES ?item {{ {" ".join("wd:" + i for i in batch)} }}
          VALUES ?p {{ {" ".join("wdt:" + p for p in props.values())} }}
          ?item ?p ?val . SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}"""
        res = client.get(SPARQL, params={"query": q, "format": "json"}, max_age_s=MONTH_S).json()
        for b in res["results"]["bindings"]:
            n = items[b["item"]["value"].rsplit("/", 1)[-1]]
            field = pmap.get(b["p"]["value"].rsplit("/", 1)[-1])
            label = b.get("valLabel", {}).get("value")
            if field and label and not re.fullmatch(r"Q\d+", label):
                lst = out[n]["cechy"].setdefault(field, [])
                if label not in lst:
                    lst.append(label)
    return out


# ---------------------------------------------------------------- Wikipedia PL i Commons
def plwiki_text(client: HttpClient, title: str) -> tuple[str, str] | None:
    r = client.get(PLWIKI, params={"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki",
                                   "titles": title, "redirects": 1, "format": "json", "formatversion": 2},
                   max_age_s=MONTH_S).json()
    pages = r.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    return pages[0]["title"], pages[0].get("extract", "")


def commons_info(client: HttpClient, files: list[str], allowed: set[str]) -> dict[str, dict]:
    out = {}
    for batch in chunks(files, 40):
        r = client.get(COMMONS, params={"action": "query", "titles": "|".join(batch), "prop": "imageinfo",
                                        "iiprop": "url|extmetadata", "iiurlwidth": 800, "format": "json", "formatversion": 2},
                       max_age_s=MONTH_S).json()
        norm = {n["to"]: n["from"] for n in r.get("query", {}).get("normalized", [])}
        for p in r.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [None])[0]
            if not ii:
                continue
            md = ii.get("extmetadata", {})
            lic = normalize_license((md.get("LicenseShortName") or {}).get("value"))
            author = strip_html((md.get("Artist") or {}).get("value"))
            if lic not in allowed or not author:
                continue
            clean = lambda u: u.split("?", 1)[0] if u else u
            out[norm.get(p["title"], p["title"])] = {
                "zdjecie_url": clean(ii.get("url")), "zdjecie_miniatura": clean(ii.get("thumburl")),
                "zdjecie_strona": ii.get("descriptionurl"), "zdjecie_autor": author[:300], "zdjecie_licencja": lic,
                "zdjecie_licencja_url": (md.get("LicenseUrl") or {}).get("value")}
    return out


# ---------------------------------------------------------------- import
def import_katalog() -> int:
    cfg = load_yaml("katalog.yaml")
    allowed = set(load_yaml_root("atlas/config_zdjecia.yaml")["licencje_dozwolone"])
    conn = connect()
    n = 0
    with import_run(conn, "gbif", "atlas.katalog", "Polska", {"limit": cfg["limit_gatunkow"]}) as run:
        with HttpClient(min_interval_s=0.25) as gbif:
            species = gbif_species_list(gbif, cfg)
        log.info("GBIF: %d gatunków", len(species))
        with HttpClient(min_interval_s=1.0, timeout_s=120) as wm:
            wd = wikidata(wm, [s["nazwa_naukowa"] for s in species], cfg)
            files = sorted({o["image"] for o in wd.values() if o.get("image")})
            photos = commons_info(wm, files, allowed)
            rows = []
            for s in species:
                w = wd.get(s["nazwa_naukowa"], {})
                rec = {**s, "id": slug(s["nazwa_naukowa"]), "wikidata": w.get("item"), "cechy": w.get("cechy", {}),
                       "wiki_tytul": None, "wiki_url": None, "nazwa_polska": s["nazwy_polskie"][0] if s["nazwy_polskie"] else None,
                       "opis_wstep": None, "opis_budowa": None, "opis_wystepowanie": None, "opis_podobne": None,
                       "opis_ochrona": None, "siedlisko": {}}
                if w.get("plwiki"):
                    try:
                        got = plwiki_text(wm, w["plwiki"])
                    except SourceUnavailable as e:
                        log.warning("Wikipedia: %s", e)
                        got = None
                    if got:
                        title, text = got
                        rec["wiki_tytul"] = title
                        rec["wiki_url"] = "https://pl.wikipedia.org/wiki/" + title.replace(" ", "_")
                        rec.update(pick_sections(text, cfg))
                        rec["siedlisko"] = habitat_tags(rec["opis_wystepowanie"], cfg)
                        # tytuł polskiego artykułu to zwykle polska nazwa gatunku (jeśli nie jest nazwą łacińską)
                        if title.lower() != s["nazwa_naukowa"].lower():
                            rec["nazwa_polska"] = title
                            if title.lower() not in [x.lower() for x in rec["nazwy_polskie"]]:
                                rec["nazwy_polskie"] = [title] + rec["nazwy_polskie"]
                rec.update(photos.get(w.get("image"), {}))
                rows.append(rec)
        cols = ["id", "gbif_key", "nazwa_naukowa", "nazwa_polska", "nazwy_polskie", "rodzaj", "rodzina", "rzad", "klasa",
                "obserwacje_pl", "obserwacje_woj", "wikidata", "wiki_tytul", "wiki_url", "opis_wstep", "opis_budowa",
                "opis_wystepowanie", "opis_podobne", "opis_ochrona", "cechy", "siedlisko", "zdjecie_url", "zdjecie_miniatura",
                "zdjecie_strona", "zdjecie_autor", "zdjecie_licencja", "zdjecie_licencja_url"]
        with conn.cursor() as cur:
            cur.execute("TRUNCATE atlas.katalog")
            for r in {r["id"]: r for r in rows}.values():
                vals = [json.dumps(r.get(c), ensure_ascii=False) if c in ("cechy", "siedlisko") else r.get(c) for c in cols]
                cur.execute(f"INSERT INTO atlas.katalog ({', '.join(cols)}, import_id) VALUES ({', '.join(['%s'] * len(cols))}, %s)",
                            vals + [run.id])
                n += 1
        run.records = n
        conn.commit()
        stats = {"gatunki": n, "z_artykulem": sum(1 for r in rows if r["wiki_url"]),
                 "ze_zdjeciem": sum(1 for r in rows if r.get("zdjecie_miniatura")),
                 "z_cechami": sum(1 for r in rows if r["cechy"]), "z_polska_nazwa": sum(1 for r in rows if r["nazwa_polska"])}
        log.info("Katalog: %s", stats)
        print(json.dumps(stats, ensure_ascii=False))
    conn.close()
    return n


def load_yaml_root(rel: str) -> dict:
    import yaml
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))
