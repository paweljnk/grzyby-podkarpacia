"""Generator DANYCH DEMONSTRACYJNYCH (schemat demo).

Drzewostany, pogoda, obserwacje i formy ochrony są FIKCYJNE (deterministyczne, ziarno stałe) — służą wyłącznie do
pokazania działania aplikacji, dopóki źródła rzeczywiste są niedostępne. Rzeźba terenu jest liczona z prawdziwego
Copernicus DEM, ale dla fikcyjnych poligonów. Interfejs oznacza ten zbiór jako demonstracyjny.
"""
from __future__ import annotations

import json
import logging
import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import rasterio
from pyproj import Transformer
from shapely import wkb
from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.ops import transform as shp_transform

from .config import DERIVED_DIR, load_yaml, pilot_config
from .db import connect
from .etl.terrain import zonal_stats
from .weather.openmeteo import cell_center, cell_id

log = logging.getLogger(__name__)
SEED = 20261017
TO_2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True).transform

PROFILES = {
    "nizinny": [
        ({"SO": 0.8, "BRZ": 0.1, "DB": 0.1}, ["Bśw", "BMśw"], ["rdzawa", "bielicowa"], 4),
        ({"SO": 0.5, "DB": 0.3, "BRZ": 0.2}, ["BMśw", "LMśw"], ["rdzawa", "brunatna kwaśna"], 3),
        ({"SO": 0.6, "SW": 0.2, "BRZ": 0.2}, ["Bw", "BMw"], ["glejowa", "bielicowa"], 2),
        ({"DB": 0.5, "GB": 0.4, "LP": 0.1}, ["Lśw"], ["płowa", "brunatna właściwa"], 1),
        ({"OL": 0.9, "JS": 0.1}, ["Ol"], ["torfowa"], 1),
    ],
    "gorski": [
        ({"BK": 0.7, "JD": 0.2, "JW": 0.1}, ["LGśw"], ["brunatna kwaśna", "brunatna właściwa"], 4),
        ({"JD": 0.5, "BK": 0.4, "SW": 0.1}, ["LMGśw"], ["brunatna kwaśna"], 3),
        ({"SW": 0.7, "JD": 0.2, "BK": 0.1}, ["BMGśw"], ["brunatna kwaśna", "bielicowa"], 2),
        ({"OLS": 0.9, "JS": 0.1}, ["LłG"], ["mada"], 1),
    ],
}


def _polygon(rng: random.Random, lon: float, lat: float) -> Polygon:
    w = rng.uniform(250, 600)
    h = rng.uniform(200, 450)
    x, y = TO_2180(lon, lat)
    pts = [(x - w / 2 + rng.uniform(-40, 40), y - h / 2 + rng.uniform(-40, 40)),
           (x + w / 2 + rng.uniform(-40, 40), y - h / 2 + rng.uniform(-40, 40)),
           (x + w / 2 + rng.uniform(-40, 40), y + h / 2 + rng.uniform(-40, 40)),
           (x - w / 2 + rng.uniform(-40, 40), y + h / 2 + rng.uniform(-40, 40))]
    return rotate(Polygon(pts), rng.uniform(0, 90))


def _synthetic_weather(rng: random.Random, start: date, end: date, today: date, elev: float, region_rain: dict) -> list[tuple]:
    """Fikcyjna pogoda dobowa z prostym modelem 'wiadra' dla wilgotności gleby."""
    rows, soil = [], 0.28
    d = start
    while d <= end:
        doy = d.timetuple().tm_yday
        t = 8 + 11 * math.sin(2 * math.pi * (doy - 110) / 365) - 0.6 * (elev - 200) / 100 + rng.gauss(0, 1.5)
        rain = max(0.0, region_rain[d] * rng.uniform(0.7, 1.3))
        et0 = round(max(0.3, 0.13 * t + 0.6), 2)
        soil = min(0.45, max(0.08, soil + (rain - et0) * 0.004))
        rows.append((d, "reanaliza" if d < today else "prognoza", 24, round(rain, 1), round(t - rng.uniform(4, 7), 1),
                     round(t, 1), round(t + rng.uniform(4, 8), 1), round(rng.uniform(70, 95), 1), round(soil, 3),
                     round(t - 1.5, 1), et0))
        d += timedelta(days=1)
    return rows


def generate(today: date | None = None, per_area: int = 160) -> dict:
    today = today or datetime.now(timezone.utc).date()
    rng = random.Random(SEED)
    cfg = pilot_config()
    wcfg = load_yaml("pogoda.yaml")
    step = wcfg["siatka"]["krok_stopnie"]
    start, end = today - timedelta(days=60), today + timedelta(days=wcfg["prognoza_dni"] - 1)
    conn = connect()
    with conn.cursor() as cur:
        for t in ("wydzielenie_komorka", "wydzielenie_teren", "dzien", "komorka", "wydzielenie", "forma_ochrony",
                  "obserwacja", "zakaz", "metadane"):
            cur.execute(f"TRUNCATE demo.{t}")
        stand_points: list[tuple[int, float, float]] = []
        cells: dict[str, tuple[float, float, list[float]]] = {}
        for area in cfg["obszary"]:
            lon0, lat0, lon1, lat1 = area["bbox_roboczy_wgs84"]
            paths = {n: DERIVED_DIR / "teren" / f"{area['id']}_{n}.tif" for n in ("wysokosc", "nachylenie", "ekspozycja")}
            rasters = {}
            if all(p.exists() for p in paths.values()):
                for n, p in paths.items():
                    with rasterio.open(p) as ds:
                        rasters[n], tr = ds.read(1), ds.transform
            profiles = PROFILES[area["typ_terenu"]]
            weights = [p[3] for p in profiles]
            for i in range(per_area):
                lon = rng.uniform(lon0 + 0.03, lon1 - 0.03)
                lat = rng.uniform(lat0 + 0.03, lat1 - 0.03)
                geom = _polygon(rng, lon, lat)
                comp, tsls, soils, _ = rng.choices(profiles, weights)[0]
                comp = {k: round(max(0.05, v + rng.uniform(-0.1, 0.1)), 2) for k, v in comp.items()}
                s = sum(comp.values())
                comp = {k: round(v / s, 2) for k, v in comp.items()}
                dominant = max(comp, key=comp.get)
                drop_shares = rng.random() < 0.15
                tsl = None if rng.random() < 0.05 else rng.choice(tsls)
                soil = None if rng.random() < 0.2 else rng.choice(soils)
                age = rng.choice([rng.randint(8, 25), rng.randint(30, 140), rng.randint(40, 110)])
                addr = f"DEMO {area['id'][:3].upper()}-{i + 1:03d}"
                cur.execute(
                    """INSERT INTO demo.wydzielenie (source_id, external_id, obszar_id, adres_lesny, gatunek_panujacy,
                         gatunek_panujacy_pochodzenie, udzial_gatunkow, udzial_gatunkow_pochodzenie, wiek, wiek_pochodzenie,
                         typ_siedliskowy, typ_siedliskowy_pochodzenie, gleba, gleba_pochodzenie, attrs, geom)
                       VALUES ('demo', %s, %s, %s, %s, 'opis_taksacyjny', %s, %s, %s, 'opis_taksacyjny', %s, %s, %s, %s,
                               %s, ST_Multi(ST_GeomFromWKB(%s, 2180))) RETURNING id""",
                    (addr, area["id"], addr, dominant, None if drop_shares else json.dumps(comp),
                     "brak" if drop_shares else "opis_taksacyjny", age, tsl, "opis_taksacyjny" if tsl else "brak",
                     soil, "opis_taksacyjny" if soil else "brak", json.dumps({"demo": True}), wkb.dumps(geom)))
                sid = cur.fetchone()[0]
                elev = 300.0
                if rasters:
                    st = zonal_stats(geom, rasters["wysokosc"], rasters["nachylenie"], rasters["ekspozycja"], tr, 2.0)
                    if st.n_pikseli:
                        elev = st.wys_sr
                        cur.execute(
                            """INSERT INTO demo.wydzielenie_teren (wydzielenie_id, dem_source_id, rozdzielczosc_m, n_pikseli,
                                 wys_min, wys_sr, wys_max, nachylenie_sr_deg, nachylenie_max_deg, ekspozycja_sr_deg, ekspozycja_klasa)
                               VALUES (%s,'copernicus_dem_glo30',25,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (sid, st.n_pikseli, st.wys_min, st.wys_sr, st.wys_max, st.nachylenie_sr_deg,
                             st.nachylenie_max_deg, st.ekspozycja_sr_deg, st.ekspozycja_klasa))
                clat, clon = cell_center(lat, lon, step)
                cid = cell_id(clat, clon, step)
                cells.setdefault(cid, (clat, clon, []))[2].append(elev)
                cur.execute("INSERT INTO demo.wydzielenie_komorka VALUES (%s,%s)", (sid, cid))
                stand_points.append((sid, lat, lon))

        # wspólny regionalny ciąg opadów (fikcyjny) + zróżnicowanie komórek
        region_rain: dict[date, float] = {}
        d = start
        while d <= end:
            region_rain[d] = rng.expovariate(1 / 7.0) if rng.random() < 0.3 else 0.0
            d += timedelta(days=1)
        for k in (12, 11, 5):  # kilka wyraźnych epizodów opadowych
            region_rain[today - timedelta(days=k)] = rng.uniform(14, 24)
        for cid, (clat, clon, elevs) in cells.items():
            poly = box(clon - step / 2, clat - step / 2, clon + step / 2, clat + step / 2)
            cur.execute("INSERT INTO demo.komorka VALUES (%s,%s,%s,%s, ST_GeomFromWKB(%s,2180))",
                        (cid, clat, clon, step, wkb.dumps(shp_transform(TO_2180, poly))))
            crng = random.Random(f"{SEED}:{cid}")
            for r in _synthetic_weather(crng, start, end, today, sum(elevs) / len(elevs), region_rain):
                cur.execute(
                    """INSERT INTO demo.dzien (komorka_id, data_lokalna, typ, godzin, opad_mm, temp_min_c, temp_sr_c,
                         temp_max_c, wilg_powietrza_pct, wilg_gleby_m3m3, temp_gleby_c, et0_mm, pochodzenie, model,
                         rozdzielczosc_km) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DEMO (fikcyjna)',10)""",
                    (cid, *r, "prognoza" if r[1] == "prognoza" else "model"))

        # fikcyjny park narodowy w południowo-wschodniej części obszaru górskiego + fikcyjny zakaz wstępu
        mount = next(a for a in cfg["obszary"] if a["typ_terenu"] == "gorski")
        lo0, la0, lo1, la1 = mount["bbox_roboczy_wgs84"]
        park = shp_transform(TO_2180, box(lo1 - 0.15, la0 + 0.02, lo1 - 0.02, la0 + 0.12))
        cur.execute("""INSERT INTO demo.forma_ochrony (source_id, warstwa, rodzaj, nazwa, kod, attrs, geom)
                       VALUES ('demo','demo','park_narodowy','Fikcyjny Park Narodowy (DEMO)','DEMO-PN','{}',
                               ST_Multi(ST_GeomFromWKB(%s,2180)))""", (wkb.dumps(park),))
        rez = shp_transform(TO_2180, box(lo0 + 0.05, la1 - 0.1, lo0 + 0.1, la1 - 0.05))
        cur.execute("""INSERT INTO demo.forma_ochrony (source_id, warstwa, rodzaj, nazwa, kod, attrs, geom)
                       VALUES ('demo','demo','rezerwat','Fikcyjny rezerwat (DEMO)','DEMO-R','{}',
                               ST_Multi(ST_GeomFromWKB(%s,2180)))""", (wkb.dumps(rez),))
        ban = shp_transform(TO_2180, box(lo0 + 0.12, la0 + 0.05, lo0 + 0.17, la0 + 0.09))
        cur.execute("""INSERT INTO demo.zakaz (source_id, rodzaj, od, do_dnia, opis, geom)
                       VALUES ('demo','prace_lesne',%s,%s,'DEMO: fikcyjny zakaz wstępu', ST_Multi(ST_GeomFromWKB(%s,2180)))""",
                    (today - timedelta(days=5), today + timedelta(days=20), wkb.dumps(ban)))

        # fikcyjne obserwacje
        for sid, lat, lon in rng.sample(stand_points, 25):
            x, y = TO_2180(lon, lat)
            cur.execute("""INSERT INTO demo.obserwacja (species_id, czas_utc, znaleziono, liczba_okazow, czas_szukania_min,
                             jakosc, geom) VALUES (%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),2180))""",
                        (rng.choice(["boletus_edulis", "imleria_badia", "cantharellus_cibarius"]),
                         datetime.combine(today - timedelta(days=rng.randint(0, 20)), datetime.min.time(), timezone.utc),
                         rng.random() < 0.6, rng.randint(1, 30), rng.randint(30, 180),
                         rng.choice(["wysoka", "srednia", "niska"]), x, y))
        meta = {"wygenerowano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "dzien_odniesienia": today.isoformat(), "ziarno": str(SEED), "wydzielen": str(len(stand_points)),
                "komorek": str(len(cells)),
                "opis": "Dane demonstracyjne: fikcyjne drzewostany, pogoda, obserwacje i formy ochrony. "
                        "Rzeźba terenu z prawdziwego Copernicus DEM."}
        for k, v in meta.items():
            cur.execute("INSERT INTO demo.metadane VALUES (%s,%s)", (k, v))
    conn.commit()
    conn.close()
    return meta


def ensure_fresh(today: date | None = None) -> bool:
    """Regeneruje dane demo, gdy dzień odniesienia jest inny niż dziś (pogoda demo jest względna wobec 'dziś')."""
    today = today or datetime.now(timezone.utc).date()
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT wartosc FROM demo.metadane WHERE klucz='dzien_odniesienia'")
        r = cur.fetchone()
    conn.close()
    if r and r[0] == today.isoformat():
        return False
    generate(today)
    return True
