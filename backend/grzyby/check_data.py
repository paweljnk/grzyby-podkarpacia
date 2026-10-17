"""`make check-data`: liczba rekordów i braków (NULL / pochodzenie 'brak') dla każdej warstwy."""
from __future__ import annotations

import sys
from typing import Any

from .db import connect

LAYERS = [
    ("ref.obszar_pilotazowy", "Obszary pilotażowe", ["prg_wojewodztwa"]),
    ("ref.wojewodztwo", "Granica województwa (PRG)", ["prg_wojewodztwa"]),
    ("forest.wydzielenie", "Wydzielenia leśne (BDL)", ["bdl_ogcapi"]),
    ("terrain.wydzielenie_teren", "Rzeźba terenu — statystyki wydzieleń", ["copernicus_dem_glo30"]),
    ("terrain.raster", "Rastry rzeźby terenu", ["copernicus_dem_glo30"]),
    ("protection.forma_ochrony", "Formy ochrony przyrody (GDOŚ)", ["gdos_crfop"]),
]
SKIP_COLS = {"id", "geom", "import_id", "imported_at"}


def layer_stats(cur, table: str) -> dict[str, Any]:
    schema, name = table.split(".")
    cur.execute(
        "SELECT column_name, udt_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
        "ORDER BY ordinal_position", (schema, name))
    cols = [(c, t) for c, t in cur.fetchall() if c not in SKIP_COLS]
    exprs = ["count(*)"]
    for c, t in cols:
        if t == "pochodzenie":
            exprs.append(f"count(*) FILTER (WHERE {c} = 'brak')")
        else:
            exprs.append(f"count(*) FILTER (WHERE {c} IS NULL)")
    cur.execute(f"SELECT {', '.join(exprs)} FROM {table}")
    row = cur.fetchone()
    return {"rekordy": row[0], "braki": {c: n for (c, _), n in zip(cols, row[1:])}}


def raw_attr_nulls(cur, table: str, limit: int = 50) -> dict[str, int]:
    """Braki w surowych atrybutach źródła (attrs jsonb): klucz nieobecny lub JSON null."""
    cur.execute(f"""
        WITH k AS (SELECT DISTINCT jsonb_object_keys(attrs) AS key FROM {table})
        SELECT key, (SELECT count(*) FROM {table} t
                     WHERE NOT (t.attrs ? k.key) OR jsonb_typeof(t.attrs -> k.key) = 'null')
        FROM k ORDER BY key LIMIT {limit}""")
    return dict(cur.fetchall())


def last_imports(cur) -> dict[str, tuple]:
    cur.execute("""SELECT DISTINCT ON (source_id, target, area) source_id, target, status, records, area, finished_at, message
                   FROM meta.import_log ORDER BY source_id, target, area, started_at DESC""")
    return {(r[0], r[1], r[4]): (r[2], r[3], r[4], r[5], r[6]) for r in cur.fetchall()}


def main(argv: list[str] | None = None) -> int:
    strict = "--strict" in (argv or sys.argv[1:])
    conn = connect()
    empty = []
    with conn.cursor() as cur:
        imports = last_imports(cur)
        for table, label, _ in LAYERS:
            st = layer_stats(cur, table)
            print(f"\n== {label} [{table}] — rekordów: {st['rekordy']}")
            if st["rekordy"] == 0:
                empty.append(table)
            for col, n in st["braki"].items():
                if st["rekordy"]:
                    print(f"   {col:32s} braki: {n:6d} ({100 * n / st['rekordy']:5.1f}%)")
            if st["rekordy"] and "attrs" in st["braki"]:
                raw = raw_attr_nulls(cur, table)
                if raw:
                    print("   -- surowe atrybuty źródła (attrs) --")
                    for k, n in raw.items():
                        print(f"   attrs.{k:26s} braki: {n:6d} ({100 * n / st['rekordy']:5.1f}%)")
            for (sid, target, _), (status, rec, area, fin, msg) in imports.items():
                if target == table:
                    when = fin.astimezone().strftime("%Y-%m-%d %H:%M %Z") if fin else "w toku"
                    print(f"   ostatni import: {sid} [{area}] status={status} rekordy={rec} ({when})")
                    if msg:
                        print(f"     {msg}")
        cur.execute("""SELECT id, warstwa, szerokosc_px*wysokosc_px, n_nodata, stat_min, stat_max
                       FROM terrain.raster ORDER BY id""")
        rasters = cur.fetchall()
        if rasters:
            print("\n== Rastry — piksele bez danych (NaN poza zasięgiem/na brzegach)")
            for rid, w, tot, nd, mn, mx in rasters:
                rng = f"{mn:.1f}..{mx:.1f}" if mn is not None else "brak"
                print(f"   {rid:48s} pikseli: {tot:9d} brak: {nd:8d} ({100 * nd / tot:4.1f}%) zakres: {rng}")
    conn.close()
    if empty:
        print(f"\nPuste warstwy ({len(empty)}): {', '.join(empty)}")
    return 1 if (strict and empty) else 0


if __name__ == "__main__":
    raise SystemExit(main())
