"""Wiersz poleceń ETL: python -m grzyby.cli <polecenie>."""
from __future__ import annotations

import argparse
import logging


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="grzyby")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("probe", help="pobierz próbki i zapisz schematy źródeł")
    pr.add_argument("sources", nargs="*")
    imp = sub.add_parser("import", help="import danych pilotażowych")
    imp.add_argument("layer", choices=["prg", "bdl", "dem", "gdos", "all"])
    sub.add_parser("check-data")
    args = p.parse_args()

    if args.cmd == "probe":
        from .etl.probe import probe_all
        for r in probe_all(args.sources or None):
            print(f"{r['source_id']:24s} {r['status']:12s} {r.get('powod') or ''}")
        return 0
    if args.cmd == "import":
        from .etl import dem, vector
        steps = {"prg": vector.import_prg, "bdl": vector.import_bdl, "gdos": vector.import_gdos, "dem": dem.import_dem}
        # Kolejność: granice → wydzielenia → teren (statystyki strefowe wymagają wydzieleń) → ochrona.
        order = ["prg", "bdl", "dem", "gdos"] if args.layer == "all" else [args.layer]
        for name in order:
            steps[name]()
        return 0
    if args.cmd == "check-data":
        from .check_data import main as check
        return check([])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
