"""Paczka danych rzeczywistych (snapshot): eksport po imporcie w GitHub Actions, wczytanie w aplikacji.

Format: katalog z plikami `<schemat>.<tabela>.copy.gz` (PostgreSQL COPY, format tekstowy — geometrie jako
HEXEWKB w EPSG:2180) oraz `manifest.json` (czas wygenerowania, liczby wierszy, sumy SHA-256, ostatnie importy,
oznaczenia autorstwa). Wczytanie zastępuje dane rzeczywiste w jednej transakcji; schemat `demo` nie jest ruszany.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR
from .db import connect
from .sources import load_sources

log = logging.getLogger(__name__)

# Kolejność = kolejność wczytywania (rodzice przed dziećmi).
TABLES = [
    "ref.obszar_pilotazowy", "ref.wojewodztwo", "forest.wydzielenie", "terrain.wydzielenie_teren", "terrain.raster",
    "weather.komorka", "weather.dzien", "forest.wydzielenie_komorka", "protection.forma_ochrony", "access.zakaz",
]
SEQUENCES = {"forest.wydzielenie": "id", "ref.wojewodztwo": "id", "protection.forma_ochrony": "id", "access.zakaz": "id"}
DEFAULT_URL = "https://raw.githubusercontent.com/paweljnk/grzyby-podkarpacia/dane/pilot/"
ATTRIBUTION_SOURCES = ["bdl_ogcapi", "open_meteo_archive", "open_meteo_forecast", "copernicus_dem_glo30", "prg_wojewodztwa"]


def _columns(cur, table: str) -> list[str]:
    schema, name = table.split(".")
    cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s
                   ORDER BY ordinal_position""", (schema, name))
    return [r[0] for r in cur.fetchall()]


def export(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect()
    files, counts = {}, {}
    with conn.cursor() as cur:
        for t in TABLES:
            cols = _columns(cur, t)
            # import_id odnosi się do meta.import_log tej bazy — w paczce nie ma sensu
            cols = [c for c in cols if c != "import_id"]
            buf = io.BytesIO()
            with cur.copy(f"COPY (SELECT {', '.join(cols)} FROM {t}) TO STDOUT") as cp:
                for chunk in cp:
                    buf.write(chunk)
            raw = buf.getvalue()
            path = out_dir / f"{t}.copy.gz"
            with gzip.open(path, "wb", compresslevel=9) as f:
                f.write(raw)
            files[t] = {"plik": path.name, "kolumny": cols, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            counts[t] = raw.count(b"\n")
        cur.execute("""SELECT DISTINCT ON (source_id, target, area) source_id, target, area, status, records,
                              finished_at, message
                       FROM meta.import_log ORDER BY source_id, target, area, started_at DESC""")
        imports = [dict(zip(["source_id", "target", "area", "status", "records", "finished_at", "message"], r))
                   for r in cur.fetchall()]
    conn.close()
    src = load_sources()
    manifest = {
        "wygenerowano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wersja": 1,
        "tabele": files,
        "wiersze": counts,
        "importy": imports,
        "atrybucja": [{"id": k, "nazwa": src[k]["nazwa"], "licencja": src[k].get("licencja"),
                       "atrybucja": src[k].get("atrybucja")} for k in ATTRIBUTION_SOURCES if k in src],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return manifest


def _read(base: str, name: str) -> bytes:
    if base.startswith("http"):
        from .etl.http import HttpClient
        with HttpClient(min_interval_s=0, timeout_s=300) as c:
            r = c.get(base.rstrip("/") + "/" + name, use_cache=False)
            if r.status_code != 200:
                raise RuntimeError(f"{name}: HTTP {r.status_code}")
            return r.content
    return (Path(base) / name).read_bytes()


def current(conn) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT wygenerowano, wczytano, zrodlo_url, manifest FROM meta.snapshot ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
    return dict(zip(["wygenerowano", "wczytano", "zrodlo_url", "manifest"], r)) if r else None


def load(base: str | None = None, force: bool = False) -> dict:
    """Wczytuje paczkę, jeśli jest nowsza niż ostatnio wczytana. Zwraca opis wyniku."""
    base = base or os.environ.get("GRZYBY_SNAPSHOT_URL", DEFAULT_URL)
    manifest = json.loads(_read(base, "manifest.json"))
    generated = datetime.fromisoformat(manifest["wygenerowano_utc"])
    conn = connect()
    cur_snap = current(conn)
    if cur_snap and not force and cur_snap["wygenerowano"] >= generated:
        conn.close()
        return {"wczytano": False, "powod": "brak nowszej paczki", "wygenerowano": manifest["wygenerowano_utc"]}
    blobs = {}
    for t, info in manifest["tabele"].items():
        if t not in TABLES:
            raise ValueError(f"nieoczekiwana tabela w paczce: {t}")
        data = _read(base, info["plik"])
        if hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise ValueError(f"{info['plik']}: niezgodna suma SHA-256")
        blobs[t] = gzip.decompress(data)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(reversed(TABLES))} CASCADE")
        for t in TABLES:
            if t not in blobs:
                continue
            cols = manifest["tabele"][t]["kolumny"]
            with cur.copy(f"COPY {t} ({', '.join(cols)}) FROM STDIN") as cp:
                cp.write(blobs[t])
        for t, col in SEQUENCES.items():
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', '{col}'), COALESCE((SELECT max({col}) FROM {t}), 0) + 1, false)")
        cur.execute("INSERT INTO meta.snapshot (wygenerowano, zrodlo_url, manifest) VALUES (%s,%s,%s)",
                    (generated, base, json.dumps(manifest, default=str)))
    conn.commit()
    conn.close()
    log.info("Wczytano paczkę danych z %s (%s)", base, manifest["wygenerowano_utc"])
    return {"wczytano": True, "wygenerowano": manifest["wygenerowano_utc"], "wiersze": manifest["wiersze"]}


def default_export_dir() -> Path:
    return DATA_DIR / "snapshot"


def verify(today=None, min_cell_share: float = 0.8) -> list[str]:
    """Kontrola jakości przed publikacją. Pusta lista = paczka nadaje się do publikacji."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    today = today or datetime.now(ZoneInfo("Europe/Warsaw")).date()
    problems = []
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM forest.wydzielenie")
        if cur.fetchone()[0] == 0:
            problems.append("brak wydzieleń")
        cur.execute("SELECT count(*) FROM weather.komorka")
        cells = cur.fetchone()[0]
        for label, d0, d1 in (("ostatnie 14 dni", today - timedelta(days=14), today - timedelta(days=1)),
                              ("dziś i prognoza", today, today + timedelta(days=4))):
            cur.execute("""SELECT count(*) FROM (SELECT komorka_id FROM weather.dzien
                             WHERE data_lokalna BETWEEN %s AND %s AND opad_mm IS NOT NULL
                             GROUP BY komorka_id HAVING count(DISTINCT data_lokalna) = %s) s""",
                        (d0, d1, (d1 - d0).days + 1))
            ok = cur.fetchone()[0]
            if cells == 0 or ok < min_cell_share * cells:
                problems.append(f"pogoda ({label}): kompletne komórki {ok}/{cells}")
    conn.close()
    return problems
