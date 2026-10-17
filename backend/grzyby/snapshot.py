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

# Pakiety: 'baza' (comiesięcznie: drzewostany, gleba, teren, pokrycie) i 'dzienne' (pogoda, zakazy wstępu).
# Kolejność w liście = kolejność wczytywania (rodzice przed dziećmi).
PACKAGES = {
    "baza": ["ref.obszar_pilotazowy", "ref.wojewodztwo", "ref.nadlesnictwo", "forest.wydzielenie",
             "terrain.wydzielenie_teren", "terrain.raster", "weather.komorka", "forest.wydzielenie_komorka",
             "protection.forma_ochrony", "coverage.siatka"],
    "dzienne": ["weather.dzien", "access.zakaz"],
}
TABLES = PACKAGES["baza"] + PACKAGES["dzienne"]
SEQUENCES = {"forest.wydzielenie": "id", "ref.wojewodztwo": "id", "protection.forma_ochrony": "id", "access.zakaz": "id"}
# Uproszczenie geometrii TYLKO w paczce dla aplikacji (analizy w GitHub Actions liczone na pełnych geometriach).
SIMPLIFY_M = {"forest.wydzielenie": 1.0, "ref.nadlesnictwo": 5.0, "ref.wojewodztwo": 5.0, "ref.obszar_pilotazowy": 5.0}
PART_BYTES = 45 * 1024 * 1024
DEFAULT_URL = "https://raw.githubusercontent.com/paweljnk/grzyby-podkarpacia/dane/{pakiet}/"
ATTRIBUTION_SOURCES = ["bdl_ogcapi", "open_meteo_archive", "open_meteo_forecast", "copernicus_dem_glo30", "prg_wojewodztwa"]


def _columns(cur, table: str) -> list[str]:
    schema, name = table.split(".")
    cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s
                   ORDER BY ordinal_position""", (schema, name))
    return [r[0] for r in cur.fetchall()]


def export(out_dir: Path, pakiet: str = "baza") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect()
    files, counts = {}, {}
    with conn.cursor() as cur:
        for t in PACKAGES[pakiet]:
            cols = [c for c in _columns(cur, t) if c != "import_id"]
            sel = [f"ST_ReducePrecision(ST_SimplifyPreserveTopology(geom, {SIMPLIFY_M[t]}), 0.01) AS geom"
                   if c == "geom" and t in SIMPLIFY_M else c for c in cols]
            parts, n, part_no = [], 0, 0
            fh = gz = None

            def new_part():
                nonlocal fh, gz, part_no
                part_no += 1
                path = out_dir / f"{t}.part{part_no:03d}.copy.gz"
                fh = open(path, "wb")
                gz = gzip.GzipFile(fileobj=fh, mode="wb", compresslevel=9)
                parts.append(path)

            new_part()
            pending = b""
            with cur.copy(f"COPY (SELECT {', '.join(sel)} FROM {t}) TO STDOUT") as cp:
                for chunk in cp:
                    data = pending + bytes(chunk)
                    cut = data.rfind(b"\n") + 1           # części dzielimy tylko na granicy wierszy
                    gz.write(data[:cut])
                    n += data[:cut].count(b"\n")
                    pending = data[cut:]
                    if fh.tell() > PART_BYTES:
                        gz.close(); fh.close()
                        new_part()
            gz.write(pending)
            n += pending.count(b"\n")
            gz.close(); fh.close()
            files[t] = {"pliki": [{"plik": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in parts],
                        "kolumny": cols, "uproszczenie_m": SIMPLIFY_M.get(t)}
            counts[t] = n
        cur.execute("""SELECT DISTINCT ON (source_id, target, area) source_id, target, area, status, records,
                              finished_at, message
                       FROM meta.import_log ORDER BY source_id, target, area, started_at DESC""")
        imports = [dict(zip(["source_id", "target", "area", "status", "records", "finished_at", "message"], r))
                   for r in cur.fetchall()]
    conn.close()
    src = load_sources()
    manifest = {
        "pakiet": pakiet,
        "wygenerowano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wersja": 2,
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


def current(conn, pakiet: str | None = None) -> dict | None:
    with conn.cursor() as cur:
        if pakiet:
            cur.execute("""SELECT wygenerowano, wczytano, zrodlo_url, manifest FROM meta.snapshot
                           WHERE coalesce(manifest->>'pakiet', 'baza') = %s ORDER BY id DESC LIMIT 1""", (pakiet,))
        else:
            cur.execute("SELECT wygenerowano, wczytano, zrodlo_url, manifest FROM meta.snapshot ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
    return dict(zip(["wygenerowano", "wczytano", "zrodlo_url", "manifest"], r)) if r else None


def _files(info: dict) -> list[dict]:
    return info.get("pliki") or [{"plik": info["plik"], "sha256": info["sha256"]}]   # format v1: jeden plik


def load(base: str | None = None, force: bool = False, pakiet: str = "baza") -> dict:
    """Wczytuje paczkę, jeśli jest nowsza niż ostatnio wczytana. Zastępuje tylko tabele tej paczki."""
    base = base or os.environ.get(f"GRZYBY_SNAPSHOT_URL_{pakiet.upper()}") or DEFAULT_URL.format(pakiet=pakiet)
    manifest = json.loads(_read(base, "manifest.json"))
    pakiet = manifest.get("pakiet", pakiet)
    generated = datetime.fromisoformat(manifest["wygenerowano_utc"])
    conn = connect()
    cur_snap = current(conn, pakiet)
    if cur_snap and not force and cur_snap["wygenerowano"] >= generated:
        conn.close()
        return {"pakiet": pakiet, "wczytano": False, "powod": "brak nowszej paczki", "wygenerowano": manifest["wygenerowano_utc"]}
    tables = [t for t in TABLES if t in manifest["tabele"]]
    for t in manifest["tabele"]:
        if t not in TABLES:
            raise ValueError(f"nieoczekiwana tabela w paczce: {t}")
    blobs: dict[str, list[bytes]] = {}
    for t in tables:
        blobs[t] = []
        for f in _files(manifest["tabele"][t]):
            data = _read(base, f["plik"])
            if hashlib.sha256(data).hexdigest() != f["sha256"]:
                raise ValueError(f"{f['plik']}: niezgodna suma SHA-256")
            blobs[t].append(gzip.decompress(data))
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(reversed(tables))} CASCADE")
        for t in tables:
            cols = manifest["tabele"][t]["kolumny"]
            with cur.copy(f"COPY {t} ({', '.join(cols)}) FROM STDIN") as cp:
                for b in blobs[t]:
                    cp.write(b)
        for t, col in SEQUENCES.items():
            if t in tables:
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', '{col}'), COALESCE((SELECT max({col}) FROM {t}), 0) + 1, false)")
        cur.execute("INSERT INTO meta.snapshot (wygenerowano, zrodlo_url, manifest) VALUES (%s,%s,%s)",
                    (generated, base, json.dumps({**manifest, "pakiet": pakiet}, default=str)))
    conn.commit()
    conn.close()
    log.info("Wczytano paczkę %s z %s (%s)", pakiet, base, manifest["wygenerowano_utc"])
    return {"pakiet": pakiet, "wczytano": True, "wygenerowano": manifest["wygenerowano_utc"], "wiersze": manifest["wiersze"]}


def load_all(force: bool = False) -> list[dict]:
    """Baza, potem dzienne. Nowa baza czyści komórki pogody (CASCADE), więc wtedy dzienne wczytujemy zawsze."""
    r1 = load(pakiet="baza", force=force)
    r2 = load(pakiet="dzienne", force=force or r1.get("wczytano", False))
    return [r1, r2]


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
        cur.execute("SELECT count(*) FROM ref.nadlesnictwo")
        if cur.fetchone()[0] == 0:
            problems.append("brak nadleśnictw")
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
