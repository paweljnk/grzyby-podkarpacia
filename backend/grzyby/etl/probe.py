"""Próbkowanie źródeł: pobiera małą próbkę i zapisuje RZECZYWISTY schemat do docs/schemas/<id>.json.

Gdy źródło jest niedostępne, zapisuje to wprost (status 'niedostepne' + powód) — bez zgadywania schematu.
"""
from __future__ import annotations

import json
import logging
import os
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from ..config import SCHEMAS_DIR, pilot_config
from ..sources import load_sources, update_source
from .http import HttpClient, SourceUnavailable

log = logging.getLogger(__name__)

MAX_COLLECTIONS = 40
SAMPLE_ITEMS = 3


def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def infer_json_schema(obj: Any, depth: int = 0, max_depth: int = 4) -> Any:
    """Zwięzły opis struktury JSON na podstawie próbki (typy, klucze)."""
    t = _type_name(obj)
    if depth >= max_depth:
        return t
    if t == "object":
        return {k: infer_json_schema(v, depth + 1, max_depth) for k, v in obj.items()}
    if t == "array":
        if not obj:
            return ["<pusta lista>"]
        return [infer_json_schema(obj[0], depth + 1, max_depth), f"<{len(obj)} elementów>"]
    return t


def feature_properties_schema(features: list[dict]) -> dict[str, Any]:
    """Pola atrybutów z próbki obiektów GeoJSON: typy wartości i liczba NULL."""
    types: dict[str, Counter] = {}
    examples: dict[str, Any] = {}
    for f in features:
        for k, v in (f.get("properties") or {}).items():
            types.setdefault(k, Counter())[_type_name(v)] += 1
            if v is not None and k not in examples:
                examples[k] = v if not isinstance(v, (dict, list)) else "<złożone>"
    geom_types = Counter((f.get("geometry") or {}).get("type", "null") for f in features)
    return {
        "liczba_obiektow_w_probce": len(features),
        "typ_geometrii": dict(geom_types),
        "pola": {k: {"typy": dict(c), "przyklad": examples.get(k)} for k, c in types.items()},
    }


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def parse_wfs_capabilities(xml: bytes) -> dict[str, Any]:
    root = ET.fromstring(xml)
    out = {"wersja": root.get("version"), "typy_obiektow": [], "formaty_wyjsciowe": []}
    for el in root.iter():
        name = _strip_ns(el.tag)
        if name == "FeatureType":
            ft = {}
            for child in el:
                cn = _strip_ns(child.tag)
                if cn in ("Name", "Title", "DefaultCRS", "DefaultSRS"):
                    ft[cn] = (child.text or "").strip()
            out["typy_obiektow"].append(ft)
        elif name == "Parameter" and el.get("name") == "outputFormat":
            out["formaty_wyjsciowe"] += [(v.text or "").strip() for v in el.iter() if _strip_ns(v.tag) == "Value"]
    return out


def parse_xsd_elements(xml: bytes) -> dict[str, dict[str, str]]:
    """Z DescribeFeatureType (XSD) wyciąga pola: {typ_obiektu: {pole: typ}}."""
    root = ET.fromstring(xml)
    result: dict[str, dict[str, str]] = {}
    for ctype in root.iter():
        if _strip_ns(ctype.tag) != "complexType":
            continue
        fields = {}
        for el in ctype.iter():
            if _strip_ns(el.tag) == "element" and el.get("name"):
                fields[el.get("name")] = el.get("type", "?")
        result[ctype.get("name", "?")] = fields
    return result


def parse_wcs_capabilities(xml: bytes) -> dict[str, Any]:
    root = ET.fromstring(xml)
    ids = [(e.text or "").strip() for e in root.iter() if _strip_ns(e.tag) in ("CoverageId", "Identifier")]
    return {"wersja": root.get("version"), "pokrycia": ids}


def _pilot_bbox() -> list[float]:
    return pilot_config()["obszary"][0]["bbox_roboczy_wgs84"]


def probe_http_get(client: HttpClient, url: str) -> dict[str, Any]:
    r = client.get(url, use_cache=False)
    ctype = r.headers.get("content-type", "")
    out: dict[str, Any] = {"http_status": r.status_code, "content_type": ctype, "rozmiar_b": len(r.content)}
    if "json" in ctype:
        out["schemat"] = infer_json_schema(r.json())
    return out


def probe_http_head(client: HttpClient, url: str) -> dict[str, Any]:
    r = client.request("HEAD", url, use_cache=False)
    return {"http_status": r.status_code, "content_length": r.headers.get("content-length"),
            "last_modified": r.headers.get("last-modified")}


def probe_ogcapi(client: HttpClient, url: str) -> dict[str, Any]:
    base = url.rstrip("/")
    landing = client.get(base + "/", params={"f": "json"}, use_cache=False).json()
    cols = client.get(base + "/collections", params={"f": "json"}, use_cache=False).json()
    bbox = ",".join(map(str, _pilot_bbox()))
    out: dict[str, Any] = {"landing": infer_json_schema(landing, max_depth=2), "kolekcje": []}
    for c in cols.get("collections", [])[:MAX_COLLECTIONS]:
        entry = {"id": c.get("id"), "title": c.get("title"), "extent": c.get("extent")}
        try:
            items = client.get(f"{base}/collections/{c['id']}/items",
                               params={"f": "json", "limit": SAMPLE_ITEMS, "bbox": bbox}, use_cache=False).json()
            entry["probka"] = feature_properties_schema(items.get("features", []))
            entry["numberMatched"] = items.get("numberMatched")
        except Exception as e:  # pojedyncza kolekcja może nie działać — zapisujemy błąd
            entry["blad_probki"] = str(e)
        out["kolekcje"].append(entry)
    return out


def probe_wfs_capabilities(client: HttpClient, url: str) -> dict[str, Any]:
    caps = client.get(url, params={"service": "WFS", "request": "GetCapabilities"}, use_cache=False)
    out = parse_wfs_capabilities(caps.content)
    for ft in out["typy_obiektow"][:MAX_COLLECTIONS]:
        try:
            d = client.get(url, params={"service": "WFS", "request": "DescribeFeatureType",
                                        "typeName": ft["Name"]}, use_cache=False)
            ft["pola"] = parse_xsd_elements(d.content)
        except Exception as e:
            ft["blad_opisu"] = str(e)
    return out


def probe_wcs_capabilities(client: HttpClient, url: str) -> dict[str, Any]:
    caps = client.get(url, params={"service": "WCS", "request": "GetCapabilities"}, use_cache=False)
    return parse_wcs_capabilities(caps.content)


def probe_s3_cog(client: HttpClient, url: str) -> dict[str, Any]:
    import rasterio

    head = client.request("HEAD", url, use_cache=False)
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}
    if os.environ.get("HTTPS_PROXY"):
        env["GDAL_HTTP_PROXY"] = os.environ["HTTPS_PROXY"]
    with rasterio.Env(**env), rasterio.open("/vsicurl/" + url) as ds:
        return {
            "http_status": head.status_code,
            "content_length": head.headers.get("content-length"),
            "last_modified": head.headers.get("last-modified"),
            "crs": ds.crs.to_string() if ds.crs else None,
            "rozmiar_px": [ds.width, ds.height],
            "pasma": ds.count,
            "dtype": ds.dtypes[0],
            "nodata": ds.nodata,
            "transform": list(ds.transform)[:6],
            "rozdzielczosc_stopnie": list(ds.res),
            "tagi": ds.tags(),
            "przeglady": ds.overviews(1),
        }


PROBES: dict[str, Callable[[HttpClient, str], dict[str, Any]]] = {
    "http_get": probe_http_get,
    "http_head": probe_http_head,
    "ogcapi": probe_ogcapi,
    "wfs_capabilities": probe_wfs_capabilities,
    "wcs_capabilities": probe_wcs_capabilities,
    "s3_cog": probe_s3_cog,
}


def run_probe(source_id: str, spec: dict[str, Any], client: HttpClient) -> dict[str, Any]:
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: dict[str, Any] = {"source_id": source_id, "sprawdzono_utc": checked, "url": spec["url"], "typ": spec["typ"]}
    try:
        result["wynik"] = PROBES[spec["typ"]](client, spec["url"])
        result["status"] = "ok"
    except SourceUnavailable as e:
        result["status"] = "niedostepne"
        result["powod"] = str(e)
    except Exception as e:
        result["status"] = "blad"
        result["powod"] = f"{e.__class__.__name__}: {e}"
    return result


def probe_all(only: list[str] | None = None, write_sources: bool = True) -> list[dict[str, Any]]:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    with HttpClient(max_retries=2, backoff_base_s=1.0, timeout_s=40) as client:
        for sid, src in load_sources().items():
            if only and sid not in only:
                continue
            spec = src.get("probe")
            if not spec:
                continue
            log.info("Próbka: %s", sid)
            res = run_probe(sid, spec, client)
            path = SCHEMAS_DIR / f"{sid}.json"
            path.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            if write_sources:
                update_source(sid, weryfikacja={
                    "data_utc": res["sprawdzono_utc"],
                    "status": res["status"],
                    "powod": res.get("powod"),
                    "schemat": f"docs/schemas/{sid}.json",
                })
            results.append(res)
    return results
