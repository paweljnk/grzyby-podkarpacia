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
pts = {'LP:76920': (49.568689557148794, 22.43421400351065), 'LP:70657': (49.3820608246496, 22.432790357714687), 'LP:42447': (50.011966415922025, 21.18788809388776), 'LP:69597': (49.72025758070484, 22.590605187733043), 'LP:22897': (50.40826931970105, 22.239184300906892), 'LP:72305': (49.377762822847046, 22.35287399394847), 'LP:33252': (50.13391922769572, 22.01183453036225), 'LP:8879': (49.53721563662049, 21.646652641308787), 'poza_LP:234199': (50.47715565981077, 22.54172781142406), 'poza_LP:119700': (49.70858305805751, 21.949503399217857), 'poza_LP:193501': (50.22601677192463, 21.91726903263413), 'poza_LP:123222': (49.632921714901464, 22.206501350118042), 'poza_LP:173912': (50.19286826941404, 21.3183389005579), 'poza_LP:190810': (50.17101210612969, 22.07049065301255), 'poza_LP:102137': (49.438887612514506, 21.480855447268578), 'poza_LP:180037': (50.151941596002345, 21.609868720664338)}
for name, (lat, lon) in pts.items():
    d = 0.002
    for fmt in ("text/plain",):
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
