"""Rozpoznanie, runda 2: WFS GeoServer BDL, SWDL, gleby i siedliska, WMS (siedliska, zakazy, pożar, własność)."""
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "recon")
OUT.mkdir(parents=True, exist_ok=True)
c = httpx.Client(timeout=120, follow_redirects=True,
                 headers={"User-Agent": "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"})
log = []


def get(name, url, maxbytes=5_000_000, params=None):
    try:
        r = c.get(url, params=params)
        ct = r.headers.get("content-type", "")
        ext = "json" if "json" in ct else "pdf" if "pdf" in ct else "xml" if "xml" in ct else "txt"
        (OUT / f"{name}.{ext}").write_bytes(r.content[:maxbytes])
        log.append(f"{name}: {r.status_code} {ct} {len(r.content)}B")
        return r
    except Exception as e:
        log.append(f"{name}: BŁĄD {e}")
        return None


def strip(n):
    return n.split("}", 1)[-1]


# 1. WFS GeoServer BDL
W = "https://wfs.bdl.lasy.gov.pl/geoserver/BDL/ows"
r = get("wfs_caps", W, params={"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"})
types = []
try:
    root = ET.fromstring(r.content)
    for ft in root.iter():
        if strip(ft.tag) == "FeatureType":
            d = {strip(ch.tag): (ch.text or "").strip() for ch in ft if strip(ch.tag) in ("Name", "Title", "Abstract")}
            types.append(d)
    (OUT / "wfs_types.json").write_text(json.dumps(types, ensure_ascii=False, indent=1))
except Exception as e:
    log.append(f"wfs parse: {e}")
for t in types[:60]:
    n = t["Name"]
    safe = re.sub(r"[^A-Za-z0-9_]", "_", n)
    get(f"wfs_desc_{safe}", W, params={"service": "WFS", "version": "2.0.0", "request": "DescribeFeatureType", "typeNames": n})
    get(f"wfs_sample_{safe}", W, maxbytes=400_000, params={"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": n,
                                                             "count": 3, "outputFormat": "application/json",
                                                             "bbox": "49.3,22.2,49.4,22.3,urn:ogc:def:crs:EPSG::4326"})

# 2. SWDL — dokumentacja standardu wymiany danych
r = get("swdl_opis", "https://www.dane.gov.pl/media/resources/20170915/Dokumentacja-SWDL-2.0---opis-ogolny.pdf", maxbytes=30_000_000)
if r is not None and r.status_code == 200:
    (OUT / "swdl_opis.pdf").write_bytes(r.content)
    subprocess.run(["pdftotext", "-layout", str(OUT / "swdl_opis.pdf"), str(OUT / "swdl_opis.txt")])

# 3. Portal: gleby i siedliska, dane urządzeniowe, usługi mapowe
for name, url in [("portal_gleby_siedliska", "https://www.bdl.lasy.gov.pl/portal/gleby-i-siedliska"),
                  ("portal_dane_urzadzeniowe", "https://www.bdl.lasy.gov.pl/portal/dane-urzadzeniowe"),
                  ("portal_uslugi_mapowe", "https://www.bdl.lasy.gov.pl/portal/uslugi-mapowe-ogc")]:
    r = get(name, url)
    if r is not None and r.status_code == 200:
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
        (OUT / f"{name}_text.txt").write_text(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt)))
        (OUT / f"{name}_links.txt").write_text("\n".join(sorted(set(re.findall(r'(?:href|src)="([^"]+)"', r.text)))))

# 4. WMS: warstwy + GetFeatureInfo w punkcie leśnym (Baligród) i (Głogów)
WMS = {
    "siedliska": "https://mapserver.bdl.lasy.gov.pl/arcgis/services/WMS_BDL_mapa_siedlisk/MapServer/WMSServer",
    "zakazy": "https://mapserver.bdl.lasy.gov.pl/ArcGIS/services/WMS_zakazy_wstepu_do_lasu/MapServer/WMSServer",
    "pozar": "https://mapserver.bdl.lasy.gov.pl/ArcGIS/services/WMS_zagrozenie_pozarowe_w_lasach/MapServer/WMSServer",
    "drzewostany": "https://mapserver.bdl.lasy.gov.pl/arcgis/services/WMS_BDL_mapa_drzewostanow/MapServer/WMSServer",
    "wlasnosc": "https://mapserver.bdl.lasy.gov.pl/arcgis/services/WMS_BDL_kat_wlasnosci/MapServer/WMSServer",
    "zbiorowiska": "https://mapserver.bdl.lasy.gov.pl/arcgis/services/WMS_BDL_mapa_zbiorowisk_roslinnych/MapServer/WMSServer",
}
for key, url in WMS.items():
    r = get(f"wms_{key}_caps", url, params={"service": "WMS", "request": "GetCapabilities"})
    names = []
    try:
        root = ET.fromstring(r.content)
        for lay in root.iter():
            if strip(lay.tag) == "Layer":
                nm = next((ch.text for ch in lay if strip(ch.tag) == "Name"), None)
                tt = next((ch.text for ch in lay if strip(ch.tag) == "Title"), None)
                if nm:
                    names.append((nm, tt, lay.get("queryable")))
        (OUT / f"wms_{key}_layers.json").write_text(json.dumps(names, ensure_ascii=False, indent=1))
    except Exception as e:
        log.append(f"wms {key} parse: {e}")
        continue
    lays = ",".join(n for n, _, q in names if q == "1")[:1500] or ",".join(n for n, _, _ in names)[:1500]
    for pname, (lon, lat) in {"baligrod": (22.284, 49.30), "glogow": (21.97, 50.20)}.items():
        d = 0.002
        get(f"wms_{key}_gfi_{pname}", url, params={
            "service": "WMS", "version": "1.1.1", "request": "GetFeatureInfo", "layers": lays, "query_layers": lays,
            "styles": "", "srs": "EPSG:4326", "bbox": f"{lon-d},{lat-d},{lon+d},{lat+d}", "width": 101, "height": 101,
            "x": 50, "y": 50, "info_format": "text/html", "feature_count": 10})

(OUT / "_log2.txt").write_text("\n".join(log))
print("\n".join(log))
