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
    imp.add_argument("layer", choices=["prg", "bdl", "dem", "gdos", "weather", "all", "wojewodztwo", "dem-woj",
                                        "soilgrids", "worldcover", "pokrycie", "zakazy", "wojewodztwo-all"])
    sub.add_parser("demo", help="wygeneruj DANE DEMONSTRACYJNE w schemacie demo")
    sub.add_parser("check-data")
    rp = sub.add_parser("raport", help="raport pokrycia danymi (json + md)")
    rp.add_argument("katalog", nargs="?", default="out")
    sn = sub.add_parser("snapshot", help="paczka danych rzeczywistych: eksport / wczytanie")
    sn.add_argument("akcja", choices=["export", "load", "verify"])
    sn.add_argument("cel", nargs="?", help="katalog (export) albo URL/katalog (load)")
    sn.add_argument("--force", action="store_true")
    sn.add_argument("--pakiet", choices=["baza", "dzienne", "wszystkie"], default="wszystkie")
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
        from .etl import bdl_province, soilgrids, worldcover
        import json as _json

        def _woj():
            rep = bdl_province.import_province()
            print(_json.dumps(rep, ensure_ascii=False, indent=1, default=str))

        def _zakazy():
            from .db import connect as _c
            from .config import load_yaml as _ly
            conn = _c()
            with HttpClient_() as client:
                print(bdl_province.import_bans(conn, client, _ly("zasieg.yaml"), bdl_province.province(conn)))
            conn.close()

        def _pokrycie():
            print(_json.dumps(worldcover.compute_coverage(), ensure_ascii=False))

        from .etl.http import HttpClient as HttpClient_
        steps.update({"wojewodztwo": _woj, "dem-woj": dem.import_dem_province, "soilgrids": soilgrids.import_soilgrids,
                      "worldcover": worldcover.import_reference, "pokrycie": _pokrycie, "zakazy": _zakazy})
        if args.layer == "all":
            order = ["prg", "bdl", "dem", "gdos"]
        elif args.layer == "wojewodztwo-all":
            order = ["prg", "wojewodztwo", "dem-woj", "soilgrids", "worldcover", "pokrycie"]
        else:
            order = [args.layer]
        for name in order:
            r = steps[name]()
            if r is not None and not isinstance(r, dict):
                print(name, r)
        return 0
    if args.cmd == "demo":
        from .demo import generate
        print(generate())
        return 0
    if args.cmd == "raport":
        from pathlib import Path
        from .report import write
        r = write(Path(args.katalog))
        print({"procent_pokrycia": r["pokrycie"]["procent_pokrycia"], "nadlesnictw": len(r["nadlesnictwa"])})
        return 0
    if args.cmd == "snapshot":
        from pathlib import Path
        from . import snapshot
        if args.akcja == "verify":
            problems = snapshot.verify()
            print("\n".join(problems) or "OK — paczka kompletna")
            return 1 if problems else 0
        if args.akcja == "export":
            m = snapshot.export(Path(args.cel) if args.cel else snapshot.default_export_dir(),
                                "baza" if args.pakiet == "wszystkie" else args.pakiet)
            print({"pakiet": m["pakiet"], "wygenerowano": m["wygenerowano_utc"], "wiersze": m["wiersze"]})
        elif args.pakiet == "wszystkie" and not args.cel:
            print(snapshot.load_all(args.force))
        else:
            print(snapshot.load(args.cel, args.force, "baza" if args.pakiet == "wszystkie" else args.pakiet))
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
