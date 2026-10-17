"""Rozpoznanie, runda 3: interfejs REST ArcGIS usług BDL (siedliska, drzewostany, własność, zakazy)."""
import json
import sys
from pathlib import Path

import httpx

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "recon")
OUT.mkdir(parents=True, exist_ok=True)
c = httpx.Client(timeout=120, follow_redirects=True,
                 headers={"User-Agent": "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"})
log = []
R = "https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services"
SERVICES = ["WMS_BDL_mapa_siedlisk", "WMTS_BDL_mapa_siedlisk", "WMS_BDL_mapa_drzewostanow", "WMTS_BDL_mapa_drzewostanow",
            "WMS_BDL_kat_wlasnosci", "WMTS_BDL_kat_wlasnosci", "WMS_zakazy_wstepu_do_lasu", "WMS_zagrozenie_pozarowe_w_lasach"]


def get(name, url, params=None):
    try:
        r = c.get(url, params=params)
        (OUT / f"{name}.json").write_bytes(r.content[:3_000_000])
        log.append(f"{name}: {r.status_code} {r.headers.get('content-type')} {len(r.content)}B")
        return r
    except Exception as e:
        log.append(f"{name}: BŁĄD {e}")


env = {"geometry": "22.25,49.28,22.32,49.33", "geometryType": "esriGeometryEnvelope", "inSR": "4326",
       "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false", "f": "json"}
for s in SERVICES:
    r = get(f"rest_{s}_info", f"{R}/{s}/MapServer", {"f": "json"})
    try:
        info = r.json()
        layers = info.get("layers", [])
    except Exception:
        layers = []
    for lay in layers[:8]:
        lid = lay["id"]
        get(f"rest_{s}_L{lid}_meta", f"{R}/{s}/MapServer/{lid}", {"f": "json"})
        get(f"rest_{s}_L{lid}_query", f"{R}/{s}/MapServer/{lid}/query", {**env, "resultRecordCount": 5})
        get(f"rest_{s}_L{lid}_count", f"{R}/{s}/MapServer/{lid}/query",
            {"where": "1=1", "geometry": "21.1,49.0,23.6,50.85", "geometryType": "esriGeometryEnvelope", "inSR": "4326",
             "returnCountOnly": "true", "f": "json"})
# wszystkie wiersze drzewostanu dla jednego wydzielenia (czy jest pełny skład?)
for s in ("WMS_BDL_mapa_drzewostanow", "WMTS_BDL_mapa_drzewostanow"):
    for lid in range(0, 4):
        get(f"rest_{s}_L{lid}_one_subarea", f"{R}/{s}/MapServer/{lid}/query",
            {"where": "adress_forest = '04-01-1-01-39    -f   -00'", "outFields": "*", "returnGeometry": "false", "f": "json"})
(OUT / "_log3.txt").write_text("\n".join(log))
print("\n".join(log))
