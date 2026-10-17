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
    imp.add_argument("layer", choices=["prg", "bdl", "dem", "gdos", "weather", "all"])
    sub.add_parser("demo", help="wygeneruj DANE DEMONSTRACYJNE w schemacie demo")
    sub.add_parser("check-data")
    at = sub.add_parser("atlas", help="atlas: kandydaci zdjęć, zatwierdzanie, kontrola treści")
    asub = at.add_subparsers(dest="acmd", required=True)
    k = asub.add_parser("kandydaci", help="pobierz kandydatów z Wikimedia Commons (status do_weryfikacji)")
    k.add_argument("gatunek", help="id gatunku albo 'wszystkie'")
    li = asub.add_parser("lista")
    li.add_argument("--status", default="do_weryfikacji")
    z = asub.add_parser("zatwierdz")
    z.add_argument("id", type=int)
    z.add_argument("--ujecie", required=True, choices=["mlody", "dojrzaly", "spod", "trzon", "przekroj", "inne"])
    z.add_argument("--przez", required=True, help="imię i nazwisko osoby z wiedzą mykologiczną")
    z.add_argument("--adnotacje", default="[]", help='JSON: [{"x":0.4,"y":0.7,"tekst":"siateczka"}]')
    o = asub.add_parser("odrzuc")
    o.add_argument("id", type=int)
    o.add_argument("--przez", required=True)
    o.add_argument("--powod", required=True)
    asub.add_parser("sprawdz", help="kontrola spójności treści atlasu")
    args = p.parse_args()

    if args.cmd == "probe":
        from .etl.probe import probe_all
        for r in probe_all(args.sources or None):
            print(f"{r['source_id']:24s} {r['status']:12s} {r.get('powod') or ''}")
        return 0
    if args.cmd == "import":
        from .etl import dem, vector
        from .weather.openmeteo import import_weather
        steps = {"prg": vector.import_prg, "bdl": vector.import_bdl, "gdos": vector.import_gdos, "dem": dem.import_dem,
                 "weather": import_weather}
        # Kolejność: granice → wydzielenia → teren (statystyki strefowe wymagają wydzieleń) → ochrona.
        order = ["prg", "bdl", "dem", "gdos"] if args.layer == "all" else [args.layer]
        for name in order:
            steps[name]()
        return 0
    if args.cmd == "demo":
        from .demo import generate
        print(generate())
        return 0
    if args.cmd == "atlas":
        import json
        from . import atlas
        from .etl import commons
        if args.acmd == "kandydaci":
            ids = atlas.mvp_species_with_doubles() if args.gatunek == "wszystkie" else [args.gatunek]
            for sid in ids:
                print(sid, commons.fetch_candidates(sid))
        elif args.acmd == "lista":
            from .db import connect
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT id, gatunek_id, ujecie, licencja, autor, zrodlo_url FROM atlas.zdjecie WHERE status=%s ORDER BY gatunek_id, id",
                            (args.status,))
                for r in cur.fetchall():
                    print(*r, sep=" | ")
        elif args.acmd == "zatwierdz":
            commons.approve(args.id, args.ujecie, args.przez, json.loads(args.adnotacje))
            print("zatwierdzono", args.id)
        elif args.acmd == "odrzuc":
            commons.reject(args.id, args.przez, args.powod)
            print("odrzucono", args.id)
        elif args.acmd == "sprawdz":
            errs = atlas.validate()
            print("\n".join(errs) or "OK")
            return 1 if errs else 0
        return 0
    if args.cmd == "check-data":
        from .check_data import main as check
        return check([])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
