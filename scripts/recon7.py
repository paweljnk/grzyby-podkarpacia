"""Mapa glebowo-rolnicza (GUGiK): GetCapabilities WMS i GetFeatureInfo w punktach leśnych i rolnych na Podkarpaciu."""
import json
import sys
from pathlib import Path

import httpx

UA = "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
c = httpx.Client(headers={"User-Agent": UA}, timeout=90, follow_redirects=True)
W = "https://mapy.geoportal.gov.pl/wss/service/pub/guest/MapaGlebowoRolnicza/MapServer/WMSServer"
res = {}
try:
    r = c.get(W, params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"})
    res["caps"] = {"status": r.status_code, "body": r.text[:40000]}
except Exception as e:
    res["caps"] = {"error": repr(e)}
import re
layers = re.findall(r"<Layer[^>]*>\s*<Name>([^<]+)</Name>", res.get("caps", {}).get("body", ""))
res["layers"] = layers
# punkty: las (Puszcza Sandomierska k. Głogowa Młp., Bieszczady — Baligród), pole (okolice Rzeszowa, Jarosław)
pts = {"las_glogow": (50.18, 21.98), "las_baligrod": (49.33, 22.28), "pole_rzeszow": (50.02, 22.08), "pole_jaroslaw": (50.03, 22.68)}
for name, (lat, lon) in pts.items():
    d = 0.002
    for fmt in ("text/html", "application/vnd.ogc.gml", "text/plain"):
        try:
            r = c.get(W, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo", "CRS": "EPSG:4326",
                                 "BBOX": f"{lat-d},{lon-d},{lat+d},{lon+d}", "WIDTH": 101, "HEIGHT": 101, "I": 50, "J": 50,
                                 "LAYERS": ",".join(layers) or "0", "QUERY_LAYERS": ",".join(layers) or "0", "INFO_FORMAT": fmt,
                                 "FEATURE_COUNT": 10, "STYLES": ""})
            res[f"gfi_{name}_{fmt}"] = {"status": r.status_code, "body": r.text[:6000]}
        except Exception as e:
            res[f"gfi_{name}_{fmt}"] = {"error": repr(e)}
(out / "recon7.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print({k: (v.get("status") if isinstance(v, dict) else len(v)) for k, v in res.items()})
