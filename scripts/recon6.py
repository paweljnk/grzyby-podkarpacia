"""Rekonesans źródeł gleby wskazanych przez użytkownika: IBL „Gleby leśne”, ESDAC LUCAS 2018, OSChR Rzeszów,
Geoportal — mapa glebowo-rolnicza (podkarpackie). Zapisuje tekst stron, linki i odpowiedzi usług."""
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import httpx

UA = "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
c = httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
res = {}


def text_of(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def page(name, url, keep_links=r".*"):
    try:
        r = c.get(url)
        links = sorted({urljoin(str(r.url), h) for h in re.findall(r'href="([^"#]+)"', r.text)})
        links = [l for l in links if re.search(keep_links, l, re.I)]
        res[name] = {"status": r.status_code, "url": str(r.url), "text": text_of(r.text)[:12000], "links": links[:300]}
    except Exception as e:
        res[name] = {"error": repr(e)}


def raw(name, url, params=None, keep=6000):
    try:
        r = c.get(url, params=params)
        res[name] = {"status": r.status_code, "url": str(r.url), "ct": r.headers.get("content-type"), "body": r.text[:keep]}
    except Exception as e:
        res[name] = {"error": repr(e)}


page("ibl_siedliska_lasowe", "https://www.ibles.pl/baza-danych/gleby-lesne/siedliska-lasowe/")
page("ibl_gleby_lesne", "https://www.ibles.pl/baza-danych/gleby-lesne/")
page("ibl_bazy", "https://www.ibles.pl/bazy-danych/")
page("esdac_lucas2018", "https://esdac.jrc.ec.europa.eu/content/lucas-2018-topsoil-data")
page("oschr_rzeszow", "https://www.rzeszow.oschr.gov.pl/")
page("geoportal_mgr", "https://www.geoportal.gov.pl/aktualnosci/uzupelniona-mapa-glebowo-rolnicza-dla-woj-podkarpackiego-dostepna-w-serwisie-www-geoportal-gov-pl/")
# usługi mapy glebowo-rolniczej — adresy z artykułu (poniżej) oraz katalog usług GUGiK
for name, d in list(res.items()):
    for l in d.get("links", []):
        if re.search(r"(wms|wfs|MapServer|service|uslug|glebow|soil|download|pobierz|\.zip|\.csv|licen)", l, re.I) and len(res) < 60:
            k = "link_" + re.sub(r"\W+", "_", l)[-60:]
            if k not in res:
                raw(k, l, keep=4000)
(out / "recon6.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print({k: v.get("status", v.get("error")) for k, v in res.items()})
