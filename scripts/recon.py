"""Rozpoznanie źródeł (uruchamiane w GitHub Actions). Zapisuje surowe odpowiedzi i streszczenia do recon/.
Nie interpretuje — tylko pobiera i zapisuje, żeby wnioski opierać na rzeczywistych odpowiedziach usług."""
import json
import re
import subprocess
import sys
from pathlib import Path

import httpx

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "recon")
OUT.mkdir(parents=True, exist_ok=True)
UA = "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"
c = httpx.Client(timeout=90, follow_redirects=True, headers={"User-Agent": UA})
log = []


def get(name, url, maxbytes=3_000_000, **kw):
    try:
        r = c.get(url, **kw)
        body = r.content[:maxbytes]
        ext = "json" if "json" in r.headers.get("content-type", "") else ("pdf" if "pdf" in r.headers.get("content-type", "") else "txt")
        (OUT / f"{name}.{ext}").write_bytes(body)
        log.append(f"{name}: {r.status_code} {r.headers.get('content-type')} {len(r.content)}B {r.url}")
        return r
    except Exception as e:
        log.append(f"{name}: BŁĄD {e.__class__.__name__}: {e} ({url})")
        return None


B = "https://ogcapi.bdl.lasy.gov.pl"
# 1. OGC API BDL: kolekcje, queryables, pełny obiekt, szukanie kolekcji spoza LP
get("bdl_collections", f"{B}/collections?f=json")
get("bdl_krosno_queryables", f"{B}/collections/RDLP_Krosno_wydzielenia/queryables?f=json")
get("bdl_krosno_collection", f"{B}/collections/RDLP_Krosno_wydzielenia?f=json")
r = get("bdl_krosno_item_list", f"{B}/collections/RDLP_Krosno_wydzielenia/items?f=json&limit=2&bbox=22.2,49.3,22.3,49.4")
try:
    fid = r.json()["features"][0]["id"]
    get("bdl_krosno_item_full", f"{B}/collections/RDLP_Krosno_wydzielenia/items/{fid}?f=json")
    get("bdl_krosno_item_html", f"{B}/collections/RDLP_Krosno_wydzielenia/items/{fid}?f=html")
except Exception as e:
    log.append(f"item_full: {e}")
# rozkład part_cd: czy to udział gatunku panującego?
r = get("bdl_partcd_sample", f"{B}/collections/RDLP_Krosno_wydzielenia/items?f=json&limit=500&skipGeometry=true&bbox=21.8,50.1,22.0,50.3")
try:
    from collections import Counter
    feats = r.json()["features"]
    (OUT / "bdl_partcd_stats.json").write_text(json.dumps({
        "part_cd": Counter(str(f["properties"].get("part_cd")) for f in feats).most_common(),
        "stand_stru": Counter(str(f["properties"].get("stand_stru")) for f in feats).most_common(),
        "area_type": Counter(str(f["properties"].get("area_type")) for f in feats).most_common(),
        "przyklady": [f["properties"] for f in feats[:15]],
    }, ensure_ascii=False, indent=1))
except Exception as e:
    log.append(f"partcd: {e}")
get("bdl_nadl_podkarpacie", f"{B}/collections/nadlesnictwa/items?f=json&limit=200&skipGeometry=true&bbox=21.1,49.0,23.6,50.85")

# 2. Portal BDL: usługi OGC, formularz pobierania (wniosek), warunki, raporty
for name, url in [("portal_uslugi_ogc", "https://www.bdl.lasy.gov.pl/portal/uslugi-ogc"),
                  ("portal_wniosek", "https://www.bdl.lasy.gov.pl/portal/wniosek"),
                  ("portal_mapy", "https://www.bdl.lasy.gov.pl/portal/mapy"),
                  ("portal_pobierz", "https://www.bdl.lasy.gov.pl/portal/pobierz"),
                  ("portal_regulamin", "https://www.bdl.lasy.gov.pl/portal/regulamin")]:
    r = get(name, url)
    if r is not None and r.status_code == 200:
        links = sorted(set(re.findall(r'(?:href|src|action)="([^"]+)"', r.text)))
        (OUT / f"{name}_links.txt").write_text("\n".join(links))
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
        txt = re.sub(r"<[^>]+>", " ", txt)
        (OUT / f"{name}_text.txt").write_text(re.sub(r"\s+", " ", txt))
# instrukcja nowego sposobu pobierania danych (gov.pl)
r = get("instrukcja_pobierania", "https://www.gov.pl/attachment/38526d4e-b0ff-4f1c-bab1-9ba18ba90479", maxbytes=20_000_000)
if r is not None and r.status_code == 200:
    p = OUT / "instrukcja_pobierania.pdf"
    p.write_bytes(r.content)
    subprocess.run(["pdftotext", "-layout", str(p), str(OUT / "instrukcja_pobierania_text.txt")])

# 3. Usługi mapowe BDL (WMS/WFS) — szukamy warstw lasów poza LP i siedlisk/gleb
for name, url in [
    ("bdl_wms_caps", "https://mapserver.bdl.lasy.gov.pl/ArcGIS/services/WMS_BDL/mapserver/WMSServer?request=GetCapabilities&service=WMS"),
    ("bdl_wfs_caps", "https://mapserver.bdl.lasy.gov.pl/ArcGIS/services/WFS_BDL/mapserver/WFSServer?request=GetCapabilities&service=WFS"),
    ("bdl_wms_mapserver_root", "https://mapserver.bdl.lasy.gov.pl/ArcGIS/services?f=json"),
    ("bdl_rest_root", "https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services?f=json"),
]:
    get(name, url)

# 4. dane.gov.pl — zbiory BDL
get("danegov_629", "https://api.dane.gov.pl/1.4/datasets/629")
get("danegov_629_resources", "https://api.dane.gov.pl/1.4/datasets/629/resources")
get("danegov_search_bdl", "https://api.dane.gov.pl/1.4/search?q=bank%20danych%20o%20lasach&per_page=50")
get("danegov_search_siedliska", "https://api.dane.gov.pl/1.4/search?q=siedliska%20le%C5%9Bne&per_page=50")

# 5. SoilGrids WCS
for v in ["phh2o", "clay", "soc"]:
    get(f"soilgrids_wcs_{v}_caps", f"https://maps.isric.org/mapserv?map=/map/{v}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities")
get("soilgrids_test_coverage", "https://maps.isric.org/mapserv?map=/map/phh2o.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage"
    "&COVERAGEID=phh2o_0-5cm_mean&FORMAT=image/tiff&SUBSET=long(22.2,22.3)&SUBSET=lat(49.3,49.4)"
    "&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326")

# 6. GDOŚ (nowy User-Agent), PRG nadleśnictwa, BDOT10k
get("gdos_wfs_caps", "https://sdi.gdos.gov.pl/wfs?service=WFS&request=GetCapabilities")
get("gdos_wfs_caps_v2", "https://sdi.gdos.gov.pl/wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities")
get("geoserwis_gdos", "https://geoserwis.gdos.gov.pl/mapy/")
get("commons_test", "https://commons.wikimedia.org/w/api.php?action=query&format=json&meta=siteinfo")

(OUT / "_log.txt").write_text("\n".join(log))
print("\n".join(log))
