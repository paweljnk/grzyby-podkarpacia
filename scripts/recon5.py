"""Rekonesans źródeł katalogu grzybów: GBIF, Wikidata (właściwości mykologiczne), Wikipedia PL, Commons.
Zapisuje surowe odpowiedzi (skrócone) do katalogu wyjściowego. Uruchamiane w GitHub Actions."""
import json
import sys
from pathlib import Path

import httpx

UA = "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
c = httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
res = {}


def get(name, url, params=None, keep=4000):
    try:
        r = c.get(url, params=params)
        res[name] = {"status": r.status_code, "url": str(r.url), "ct": r.headers.get("content-type"), "body": r.text[:keep]}
        return r
    except Exception as e:
        res[name] = {"error": repr(e)}


g = "https://api.gbif.org/v1"
get("gbif_match_agaricomycetes", f"{g}/species/match", {"name": "Agaricomycetes", "rank": "CLASS"})
get("gbif_match_pezizomycetes", f"{g}/species/match", {"name": "Pezizomycetes", "rank": "CLASS"})
get("gbif_facet_pl", f"{g}/occurrence/search", {"country": "PL", "taxonKey": 5, "limit": 0, "facet": "speciesKey", "facetLimit": 5})
get("gbif_facet_bbox", f"{g}/occurrence/search", {"country": "PL", "taxonKey": 5, "limit": 0, "facet": "speciesKey", "facetLimit": 5,
                                                  "decimalLatitude": "49.0,50.9", "decimalLongitude": "21.1,23.6"})
get("gbif_species", f"{g}/species/5243306")
get("gbif_vernacular", f"{g}/species/5243306/vernacularNames", {"limit": 200}, keep=20000)

w = "https://www.wikidata.org/w/api.php"
for term in ["taxon name", "image", "hymenium type", "mushroom cap shape", "hymenium attachment", "stipe character",
             "spore print color", "mushroom ecological type", "edibility"]:
    get(f"wd_prop_{term.replace(' ', '_')}", w, {"action": "wbsearchentities", "search": term, "type": "property", "language": "en", "format": "json", "limit": 5})
q = """SELECT ?item ?plwiki ?image WHERE { VALUES ?name { "Boletus edulis" "Amanita phalloides" }
 ?item wdt:P225 ?name . OPTIONAL { ?item wdt:P18 ?image } OPTIONAL { ?plwiki schema:about ?item ; schema:isPartOf <https://pl.wikipedia.org/> } }"""
get("wd_sparql", "https://query.wikidata.org/sparql", {"query": q, "format": "json"})
get("wd_entity_boletus", w, {"action": "wbgetentities", "ids": "Q19576", "props": "claims", "format": "json"}, keep=200000)

p = "https://pl.wikipedia.org/w/api.php"
get("plwiki_intro", p, {"action": "query", "prop": "extracts|pageimages", "exintro": 1, "explaintext": 1, "titles": "Borowik szlachetny|Muchomor zielonawy",
                        "format": "json", "formatversion": 2, "redirects": 1})
get("plwiki_full", p, {"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki", "titles": "Borowik szlachetny",
                       "format": "json", "formatversion": 2, "redirects": 1}, keep=30000)
get("commons_imageinfo", "https://commons.wikimedia.org/w/api.php",
    {"action": "query", "titles": "File:Boletus edulis EtgHollande 041031 091.jpg", "prop": "imageinfo", "iiprop": "url|extmetadata",
     "iiurlwidth": 800, "format": "json", "formatversion": 2})
(out / "recon5.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print({k: v.get("status", v.get("error")) for k, v in res.items()})
