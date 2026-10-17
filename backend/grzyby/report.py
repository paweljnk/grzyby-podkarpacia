"""Raport pokrycia danymi dla województwa (generowany w GitHub Actions po imporcie bazy)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .db import connect
from .etl.bdl_province import quality_report


def build() -> dict:
    conn = connect()
    r: dict = {"wygenerowano_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with conn.cursor() as cur:
        cur.execute("SELECT round(ST_Area(ST_Union(geom)) / 1e4) FROM ref.wojewodztwo")
        r["wojewodztwo_ha"] = cur.fetchone()[0]
        cur.execute("""SELECT n.kod, n.nazwa, round(n.w_wojewodztwie_ha), round(n.powierzchnia_ha),
                              count(w.id), round(coalesce(sum(ST_Area(w.geom) * w.w_wojewodztwie_frac), 0) / 1e4)
                       FROM ref.nadlesnictwo n LEFT JOIN forest.wydzielenie w ON w.nadl_kod = n.kod AND w.zarzad = 'LP'
                       GROUP BY n.kod, n.nazwa, n.w_wojewodztwie_ha, n.powierzchnia_ha ORDER BY n.kod""")
        r["nadlesnictwa"] = [dict(zip(["kod", "nazwa", "ha_nadlesnictwa_w_wojewodztwie", "ha_nadlesnictwa", "wydzielen_LP",
                                        "ha_drzewostanow_LP_w_wojewodztwie"], x)) for x in cur.fetchall()]
        cur.execute("""SELECT coalesce(wlasnosc, '(brak)'), count(*), round(sum(ST_Area(geom) * w_wojewodztwie_frac) / 1e4),
                              min(rok_danych), max(rok_danych)
                       FROM forest.wydzielenie WHERE zarzad = 'poza_LP' GROUP BY 1 ORDER BY 3 DESC""")
        r["poza_LP_wg_wlasnosci"] = [dict(zip(["wlasnosc", "wydzielen", "ha", "rok_od", "rok_do"], x)) for x in cur.fetchall()]
        cur.execute("""SELECT count(*), round(sum(las_ref_ha)), round(sum(LEAST(bdl_ha, las_ref_ha))), round(sum(bdl_ha)),
                              count(*) FILTER (WHERE klasa = 'pelniejsze'), count(*) FILTER (WHERE klasa = 'czesciowe'),
                              count(*) FILTER (WHERE klasa = 'brak_oceny'),
                              round(sum(las_ref_ha) FILTER (WHERE klasa = 'brak_oceny'))
                       FROM coverage.siatka""")
        n, ref, cov, bdl, full, part, none, none_ha = cur.fetchone()
        r["pokrycie"] = {
            "warstwa_referencyjna": "ESA WorldCover 2021 v200, klasa 10 'Tree cover' (10 m), w granicach województwa (PRG)",
            "komorek_1km_z_lasem": n, "las_referencyjny_ha": ref, "pokryty_danymi_BDL_ha_szac": cov,
            "procent_pokrycia": round(100 * cov / ref, 1) if ref else None,
            "komorki_pelniejsze": full, "komorki_czesciowe": part, "komorki_brak_oceny": none,
            "las_ref_w_komorkach_brak_oceny_ha": none_ha,
            "metoda": "dla każdej komórki 1 km: min(powierzchnia drzewostanów BDL, las wg WorldCover); suma / suma lasu "
                      "referencyjnego. 'Tree cover' ≠ las w rozumieniu ustawy — wartość przybliżona.",
        }
        cur.execute("""SELECT round(sum(ST_Area(geom) * w_wojewodztwie_frac) / 1e4) FROM forest.wydzielenie""")
        r["drzewostany_BDL_w_wojewodztwie_ha"] = cur.fetchone()[0]
        cur.execute("""SELECT count(*), count(*) FILTER (WHERE od <= current_date AND (do_dnia IS NULL OR do_dnia >= current_date))
                       FROM access.zakaz""")
        r["zakazy_wstepu"] = dict(zip(["w_wojewodztwie", "aktualne_dzis"], cur.fetchone()))
    r["jakosc"] = quality_report(conn)
    r["braki_danych"] = [
        "Pełny skład gatunkowy z udziałami — niedostępny w usługach BDL (OGC API, WFS, WMS, REST); tylko w paczce "
        "z formularza bdl.lasy.gov.pl/portal/wniosek (wymaga adresu e-mail i akceptacji warunków).",
        "pH gleby — brak w BDL; zastępczo SoilGrids (model 250 m, z przedziałem Q0.05–Q0.95).",
        "Słownik kodów uwilgotnienia (moisture_cd) — nieopublikowany; kod pokazywany bez interpretacji.",
        "Formy ochrony przyrody GDOŚ — usługa zwraca HTTP 403 z serwerów GitHub Actions; parki narodowe rozpoznawane "
        "z kategorii własności BDL ('SP w zarządzie Parków Narodowych').",
        "Lasy bez planu urządzenia lasu (poza LP i poza PUL, np. małe lasy prywatne z uproszczonym planem lub bez) — "
        "brak opisu w BDL; widoczne jako 'brak możliwości oceny' w siatce pokrycia.",
    ]
    conn.close()
    return r


def to_markdown(r: dict) -> str:
    p = r["pokrycie"]
    lines = [f"# Raport pokrycia danymi — województwo podkarpackie", "",
             f"Wygenerowano: {r['wygenerowano_utc']}", "",
             f"- Powierzchnia województwa (PRG): {r['wojewodztwo_ha']:,.0f} ha".replace(",", " "),
             f"- Drzewostany z BDL w granicach województwa: {r['drzewostany_BDL_w_wojewodztwie_ha']:,.0f} ha".replace(",", " "),
             f"- Las referencyjny ({p['warstwa_referencyjna']}): {p['las_referencyjny_ha']:,.0f} ha".replace(",", " "),
             f"- **Pokrycie danymi BDL względem warstwy referencyjnej: {p['procent_pokrycia']}%** "
             f"(komórki 1 km: pełniejsze {p['komorki_pelniejsze']}, częściowe {p['komorki_czesciowe']}, "
             f"bez możliwości oceny {p['komorki_brak_oceny']})",
             f"- Metoda: {p['metoda']}", "",
             "## Nadleśnictwa przecinające województwo", "",
             "| Kod | Nadleśnictwo | ha nadleśnictwa w województwie | wydzieleń LP | ha drzewostanów LP w województwie |",
             "|---|---|---|---|---|"]
    for n in r["nadlesnictwa"]:
        lines.append(f"| {n['kod']} | {n['nazwa']} | {n['ha_nadlesnictwa_w_wojewodztwie']} | {n['wydzielen_LP']} | "
                     f"{n['ha_drzewostanow_LP_w_wojewodztwie']} |")
    lines += ["", "## Lasy poza zarządem LP (wg planów urządzenia lasu, BDL)", "",
              "| Własność | wydzieleń | ha | rok danych |", "|---|---|---|---|"]
    for x in r["poza_LP_wg_wlasnosci"]:
        lines.append(f"| {x['wlasnosc']} | {x['wydzielen']} | {x['ha']} | {x['rok_od']}–{x['rok_do']} |")
    lines += ["", "## Kompletność i jakość", "", "```", json.dumps(r["jakosc"], ensure_ascii=False, indent=1), "```",
              "", f"Zakazy wstępu do lasu: {r['zakazy_wstepu']}", "", "## Brakujące dane", ""]
    lines += [f"- {b}" for b in r["braki_danych"]]
    return "\n".join(lines) + "\n"


def write(out_dir: Path) -> dict:
    r = build()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raport_pokrycia.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "raport_pokrycia.md").write_text(to_markdown(r), encoding="utf-8")
    return r
