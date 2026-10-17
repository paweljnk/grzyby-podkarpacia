"""Pobieranie pogody z Open-Meteo dla komórek siatki i zapis dób do weather.dzien.

Schemat odpowiedzi przyjęty wg dokumentacji Open-Meteo (`hourly.time` + tablice zmiennych), ale parser
sprawdza obecność każdej żądanej zmiennej i odrzuca odpowiedź niepełną — bez wartości zastępczych.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from shapely import wkb
from shapely.geometry import box
from shapely.ops import transform as shp_transform
from pyproj import Transformer

from ..config import load_yaml
from ..db import connect, import_run
from ..etl.http import HttpClient, SourceUnavailable
from .aggregate import DailyWeather, hourly_to_daily

log = logging.getLogger(__name__)
_TO_2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True).transform


class BadResponse(ValueError):
    pass


def cell_id(lat: float, lon: float, step: float) -> str:
    return f"g{step}:{lat:.2f}:{lon:.2f}"


def cell_center(lat: float, lon: float, step: float) -> tuple[float, float]:
    """Środek komórki siatki o kroku `step` zawierającej punkt."""
    return (round((math.floor(lat / step) + 0.5) * step, 4), round((math.floor(lon / step) + 0.5) * step, 4))


def parse_hourly(payload: dict[str, Any], variables: dict[str, str]) -> tuple[list[datetime], dict[str, list]]:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise BadResponse("brak sekcji hourly.time w odpowiedzi")
    missing = [api for api in variables.values() if api not in hourly]
    if missing:
        raise BadResponse(f"brak zmiennych w odpowiedzi: {missing}")
    times = [datetime.fromtimestamp(int(t), tz=timezone.utc) for t in hourly["time"]]
    n = len(times)
    out = {}
    for ours, api in variables.items():
        arr = hourly[api]
        if len(arr) != n:
            raise BadResponse(f"zmienna {api}: {len(arr)} wartości, oczekiwano {n}")
        out[ours] = arr
    return times, out


def fetch_cell(client: HttpClient, kind: str, lat: float, lon: float, start: date, end: date) -> tuple[list[DailyWeather], dict]:
    cfg = load_yaml("pogoda.yaml")
    api = cfg["open_meteo"][kind]
    params = {
        "latitude": lat, "longitude": lon, "hourly": ",".join(api["zmienne"].values()),
        "timezone": "GMT", "timeformat": "unixtime",
        # doba lokalna zaczyna się 1-2 h przed północą UTC — pobieramy dzień zapasu z obu stron
        "start_date": (start - timedelta(days=1)).isoformat(), "end_date": (end + timedelta(days=1)).isoformat(),
    }
    if api.get("model"):
        params["models"] = api["model"]
    payload = client.get(api["url"], params=params, max_age_s=3 * 3600).json()
    times, values = parse_hourly(payload, api["zmienne"])
    days = [d for d in hourly_to_daily(times, values, api["typ"], cfg["min_godzin_w_dobie"]) if start <= d.data <= end]
    meta = {"lat": payload.get("latitude"), "lon": payload.get("longitude"),
            "model": api.get("model"), "rozdzielczosc_km": api.get("rozdzielczosc_km")}
    return days, meta


def ensure_cells_for_forests(conn, step: float) -> list[tuple[str, float, float]]:
    """Tworzy komórki dla wydzieleń (wg centroidu) i przypisuje wydzielenia do komórek."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id, ST_Y(c), ST_X(c) FROM (
                         SELECT id, ST_Transform(ST_PointOnSurface(geom), 4326) c FROM forest.wydzielenie) s""")
        rows = cur.fetchall()
        cells: dict[str, tuple[float, float]] = {}
        for wid, lat, lon in rows:
            clat, clon = cell_center(lat, lon, step)
            cid = cell_id(clat, clon, step)
            cells[cid] = (clat, clon)
        for cid, (clat, clon) in cells.items():
            poly = box(clon - step / 2, clat - step / 2, clon + step / 2, clat + step / 2)
            cur.execute("""INSERT INTO weather.komorka (id, lat, lon, krok_st, geom)
                           VALUES (%s,%s,%s,%s, ST_GeomFromWKB(%s,2180)) ON CONFLICT (id) DO NOTHING""",
                        (cid, clat, clon, step, wkb.dumps(shp_transform(_TO_2180, poly))))
        for wid, lat, lon in rows:
            clat, clon = cell_center(lat, lon, step)
            cur.execute("""INSERT INTO forest.wydzielenie_komorka VALUES (%s,%s)
                           ON CONFLICT (wydzielenie_id) DO UPDATE SET komorka_id=EXCLUDED.komorka_id""",
                        (wid, cell_id(clat, clon, step)))
    conn.commit()
    return [(cid, la, lo) for cid, (la, lo) in cells.items()]


def store_days(cur, cid: str, days: list[DailyWeather], meta: dict) -> None:
    for d in days:
        cur.execute(
            """INSERT INTO weather.dzien (komorka_id, data_lokalna, typ, model, rozdzielczosc_km, godzin, opad_mm,
                   temp_min_c, temp_sr_c, temp_max_c, wilg_powietrza_pct, wilg_gleby_m3m3, temp_gleby_c, et0_mm,
                   pochodzenie, zrodlo_lat, zrodlo_lon, pobrano_utc)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (komorka_id, data_lokalna, typ) DO UPDATE SET
                   godzin=EXCLUDED.godzin, opad_mm=EXCLUDED.opad_mm, temp_min_c=EXCLUDED.temp_min_c,
                   temp_sr_c=EXCLUDED.temp_sr_c, temp_max_c=EXCLUDED.temp_max_c,
                   wilg_powietrza_pct=EXCLUDED.wilg_powietrza_pct, wilg_gleby_m3m3=EXCLUDED.wilg_gleby_m3m3,
                   temp_gleby_c=EXCLUDED.temp_gleby_c, et0_mm=EXCLUDED.et0_mm, pobrano_utc=now()""",
            (cid, d.data, d.typ, meta.get("model"), meta.get("rozdzielczosc_km"), d.godzin, d.opad_mm,
             d.temp_min_c, d.temp_sr_c, d.temp_max_c, d.wilg_powietrza_pct, d.wilg_gleby_m3m3, d.temp_gleby_c,
             d.et0_mm, "prognoza" if d.typ == "prognoza" else "model", meta.get("lat"), meta.get("lon")),
        )


def import_weather(today: date | None = None) -> None:
    cfg = load_yaml("pogoda.yaml")
    today = today or datetime.now(timezone.utc).date()
    conn = connect()
    cells = ensure_cells_for_forests(conn, cfg["siatka"]["krok_stopnie"])
    if not cells:
        log.warning("Brak wydzieleń w bazie — brak komórek pogodowych do pobrania")
    with HttpClient(min_interval_s=0.3) as client:
        for kind, start, end in (
            ("archive", today - timedelta(days=cfg["historia_dni"]), today - timedelta(days=1)),
            ("forecast", today, today + timedelta(days=cfg["prognoza_dni"] - 1)),
        ):
            source_id = f"open_meteo_{kind}"
            try:
                with import_run(conn, source_id, "weather.dzien", f"{len(cells)} komórek",
                                {"start": start.isoformat(), "end": end.isoformat()}) as run:
                    with conn.cursor() as cur:
                        for cid, lat, lon in cells:
                            days, meta = fetch_cell(client, kind, lat, lon, start, end)
                            store_days(cur, cid, days, meta)
                            run.records += len(days)
                    conn.commit()
            except SourceUnavailable as e:
                log.warning("%s pominięte: %s", source_id, e)
    conn.close()
