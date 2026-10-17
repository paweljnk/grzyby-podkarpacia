"""API aplikacji Grzyby Podkarpacia (EPSG:4326 na wyjściu, daty lokalne Europe/Warsaw)."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import repo, service
from ..config import ROOT
from ..db import connect
from ..sources import load_sources
from ..species import all_species

log = logging.getLogger(__name__)
WARSAW = ZoneInfo("Europe/Warsaw")
STALE_WEATHER_DAYS = 2

DISCLAIMER = ("Wskaźnik rekomendacji 0–100 ocenia potencjał siedliska i warunki — nie oznacza, że grzyby tu rosną "
              "ani nie jest prawdopodobieństwem. Aplikacja nie ocenia jadalności grzybów. W razie wątpliwości oddaj "
              "zbiór do sprawdzenia grzyboznawcy (punkty Państwowej Inspekcji Sanitarnej).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("GRZYBY_AUTOMIGRATE", "1") == "1":
        try:
            from ..db import migrate
            log.info("Migracje: %s", migrate())
        except Exception as e:
            log.warning("Migracja nieudana: %s", e)
    if os.environ.get("GRZYBY_DEMO_AUTOREFRESH", "1") == "1":
        try:
            from ..demo import ensure_fresh
            if ensure_fresh():
                log.info("Odświeżono dane demonstracyjne")
        except Exception as e:  # brak DEM / bazy nie może blokować startu API
            log.warning("Nie odświeżono danych demo: %s", e)
    yield


app = FastAPI(title="Grzyby Podkarpacia API", version="0.4.0", lifespan=lifespan)

from .atlas_routes import router as atlas_router  # noqa: E402

app.include_router(atlas_router)
Dataset = Literal["real", "demo"]


def today_local() -> date:
    return datetime.now(WARSAW).date()


def _sp(species: str):
    try:
        return service.get_species(species)
    except KeyError:
        raise HTTPException(404, f"Nieznany gatunek: {species}")


def _sources_footer(keys: list[str]) -> list[dict]:
    src = load_sources()
    out = []
    for k in keys:
        s = src.get(k)
        if s:
            out.append({"id": k, "nazwa": s["nazwa"], "licencja": s.get("licencja"), "atrybucja": s.get("atrybucja"),
                        "ostatni_import": s.get("ostatni_import"), "status": (s.get("weryfikacja") or {}).get("status")})
    return out


FOOTER_REAL = ["bdl_ogcapi", "copernicus_dem_glo30", "open_meteo_archive", "open_meteo_forecast", "gdos_crfop"]


def _envelope(conn, ds: Dataset, params: dict, body: dict, day: date | None = None) -> dict:
    info = repo.dataset_info(conn, ds)
    warnings = []
    if ds == "demo":
        warnings.append("DANE DEMONSTRACYJNE: fikcyjne drzewostany, pogoda i obserwacje. Nie używaj do planowania wypraw.")
    elif info["wydzielen"] == 0:
        warnings.append("Brak rzeczywistych danych o drzewostanach (BDL niedostępny w tym wdrożeniu). Ranking jest pusty.")
    if info["pogoda_do"] is None:
        warnings.append("Brak danych pogodowych.")
    elif ds == "real" and info["pogoda_pobrano_utc"] and \
            datetime.now(timezone.utc) - info["pogoda_pobrano_utc"] > timedelta(days=STALE_WEATHER_DAYS):
        warnings.append("Dane pogodowe są nieaktualne — ograniczona wiarygodność wyniku.")
    if day and info["pogoda_do"] and day > info["pogoda_do"]:
        warnings.append(f"Wybrany dzień jest poza zakresem danych pogodowych (do {info['pogoda_do']}).")
    return {"zbior_danych": ds, "parametry": params, "ostrzezenia": warnings, "zastrzezenie": DISCLAIMER,
            "dane": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in info.items()},
            "zrodla": _sources_footer(FOOTER_REAL) + ([{"id": "demo", "nazwa": "Dane demonstracyjne (fikcyjne)",
                                                        "licencja": None, "atrybucja": None,
                                                        "ostatni_import": info["metadane"].get("wygenerowano_utc"),
                                                        "status": "demo"}] if ds == "demo" else []),
            **body}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/gatunki")
def species_list():
    return [{"id": s.id, "nazwa_polska": s.nazwa_polska, "nazwa_naukowa": s.nazwa_naukowa.aktualna,
             "nazwy_zwyczajowe": s.nazwy_zwyczajowe, "weryfikacja": s.weryfikacja.status}
            for s in all_species().values()]


@app.get("/api/ranking")
def ranking(species: str, lat: float = Query(ge=48.9, le=51.0), lon: float = Query(ge=21.0, le=23.7),
            radius_km: float = Query(25, gt=0, le=100), date_: date | None = Query(None, alias="date"),
            calendar: Literal["on", "off"] = "off", dataset: Dataset = "real", limit: int = Query(50, le=500),
            pokaz_wykluczone: bool = False):
    sp = _sp(species)
    day = date_ or today_local()
    params = {"species": species, "lat": lat, "lon": lon, "radius_km": radius_km, "date": day.isoformat(),
              "calendar": calendar}
    with connect() as conn:
        body = service.ranking(conn, dataset, sp, lat, lon, radius_km, day, calendar == "on", limit, pokaz_wykluczone)
        return _envelope(conn, dataset, params, body, day)


@app.get("/api/miejsce/{sid}")
def place(sid: int, species: str, date_: date | None = Query(None, alias="date"),
          calendar: Literal["on", "off"] = "off", dataset: Dataset = "real",
          lat: float | None = None, lon: float | None = None):
    sp = _sp(species)
    day = date_ or today_local()
    with connect() as conn:
        card = service.place_card(conn, dataset, sp, sid, day, calendar == "on", lat, lon)
        if not card:
            raise HTTPException(404, "Nie ma takiego miejsca")
        return _envelope(conn, dataset, {"species": species, "date": day.isoformat(), "calendar": calendar},
                         {"miejsce": card}, day)


@app.get("/api/miejsce/{sid}/7dni")
def place_week(sid: int, species: str, calendar: Literal["on", "off"] = "off", dataset: Dataset = "real",
               start: date | None = None):
    sp = _sp(species)
    day = start or today_local()
    with connect() as conn:
        res = service.seven_days(conn, dataset, sp, sid, day, calendar == "on")
        if not res:
            raise HTTPException(404, "Nie ma takiego miejsca")
        return _envelope(conn, dataset, {"species": species, "start": day.isoformat(), "calendar": calendar}, res)


@app.get("/api/kalendarz")
def month(species: str, month: str, lat: float, lon: float, dataset: Dataset = "real", place_id: int | None = None):
    sp = _sp(species)
    try:
        y, m = map(int, month.split("-"))
        date(y, m, 1)
    except ValueError:
        raise HTTPException(422, "month w formacie RRRR-MM")
    with connect() as conn:
        res = service.month_calendar(conn, dataset, sp, y, m, lat, lon, place_id)
        return _envelope(conn, dataset, {"species": species, "month": month, "place_id": place_id}, res)


@app.get("/api/porownanie")
def compare(ids: str, species: str, date_: date | None = Query(None, alias="date"),
            calendar: Literal["on", "off"] = "off", dataset: Dataset = "real"):
    sp = _sp(species)
    id_list = [int(x) for x in ids.split(",") if x.strip()][:4]
    if not 2 <= len(id_list) <= 4:
        raise HTTPException(422, "Porównanie wymaga 2–4 miejsc")
    day = date_ or today_local()
    with connect() as conn:
        res = service.compare(conn, dataset, sp, id_list, day, calendar == "on")
        return _envelope(conn, dataset, {"ids": id_list, "species": species, "date": day.isoformat()}, {"miejsca": res})


@app.get("/api/mapa")
def map_layer(species: str, lat: float, lon: float, radius_km: float = Query(25, le=100),
              date_: date | None = Query(None, alias="date"), calendar: Literal["on", "off"] = "off",
              dataset: Dataset = "real"):
    """GeoJSON wydzieleń z wskaźnikiem (także wykluczonych — z bramkami), do kolorowania mapy."""
    sp = _sp(species)
    day = date_ or today_local()
    with connect() as conn:
        r = service.ranking(conn, dataset, sp, lat, lon, radius_km, day, calendar == "on", 5000, True)
        geoms = repo.stand_geojson(conn, dataset, [m["id"] for m in r["miejsca"]])
        feats = [{"type": "Feature", "id": m["id"], "geometry": geoms.get(m["id"]),
                  "properties": {"id": m["id"], "nazwa": m["nazwa"], "wynik": m["wynik"],
                                 "rekomendowane": m["rekomendowane"], "jakosc": m["jakosc"],
                                 "gatunek_panujacy": m["gatunek_panujacy"], "typ_siedliskowy": m["typ_siedliskowy"],
                                 "opad_7d_mm": m["pogoda"]["opad_7d_mm"]}} for m in r["miejsca"]]
        return _envelope(conn, dataset, {"species": species, "date": day.isoformat()},
                         {"geojson": {"type": "FeatureCollection", "features": feats}}, day)


@app.get("/api/warstwy/ochrona")
def protection_layer(dataset: Dataset = "real"):
    t = repo.T(dataset)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"""SELECT id, rodzaj, nazwa, ST_AsGeoJSON(ST_Transform(geom,4326),5) FROM {t['ochrona']}
                        UNION ALL SELECT -id, 'zakaz_wstepu', opis, ST_AsGeoJSON(ST_Transform(geom,4326),5) FROM {t['zakaz']}""")
        import json
        feats = [{"type": "Feature", "id": i, "geometry": json.loads(g), "properties": {"rodzaj": r, "nazwa": n}}
                 for i, r, n, g in cur.fetchall()]
    return {"type": "FeatureCollection", "features": feats}


@app.get("/api/zrodla")
def sources():
    return load_sources()


# --- frontend (zbudowany PWA) ---
DIST = Path(os.environ.get("GRZYBY_WEB_DIST", ROOT / "frontend" / "dist"))
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        if path and f.is_file() and DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
