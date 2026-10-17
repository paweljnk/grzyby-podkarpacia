"""Rozpoznanie, runda 4: skład gatunkowy w warstwie Drzewostany, słowniki kodów gleby/uwilgotnienia (wartości DISTINCT)."""
import json
import sys
from pathlib import Path

import httpx

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "recon")
OUT.mkdir(parents=True, exist_ok=True)
c = httpx.Client(timeout=180, headers={"User-Agent": "GrzybyPodkarpacia/0.5 (+https://github.com/paweljnk/grzyby-podkarpacia)"})
R = "https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services"
BB = {"geometry": "21.1,49.0,23.6,50.85", "geometryType": "esriGeometryEnvelope", "inSR": "4326", "f": "json"}
res = {}


def q(name, url, params):
    try:
        r = c.get(url, params=params)
        res[name] = r.json()
    except Exception as e:
        res[name] = {"blad": str(e)}


D = f"{R}/WMS_BDL_mapa_drzewostanow/MapServer"
for lid in (9, 10, 11, 12):
    q(f"L{lid}_meta_fields", f"{D}/{lid}", {"f": "json"})
    q(f"L{lid}_one", f"{D}/{lid}/query", {"where": "adress_forest = '04-01-1-01-39    -f   -00' OR adress_forest = '04-08-2-10-89    -b   -99'",
                                          "outFields": "*", "returnGeometry": "false", "f": "json"})
    q(f"L{lid}_count", f"{D}/{lid}/query", {**BB, "where": "1=1", "returnCountOnly": "true"})
# rozkład liczby wierszy na wydzielenie w warstwie Drzewostany PGL LP (próbka obszaru)
q("L11_sample", f"{D}/11/query", {"geometry": "22.25,49.28,22.32,49.33", "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                                  "outFields": "adress_forest,species_cd,part_cd,storey_cd,storey_rank_order,order_key",
                                  "returnGeometry": "false", "f": "json", "resultRecordCount": 2000})
S = f"{R}/WMS_BDL_mapa_siedlisk/MapServer/7/query"
for fld in ("soil_subtype_cd", "moisture_cd", "soil_species", "degradation_cd", "site_type_cd", "geol_depos", "valid_year", "data_source"):
    q(f"siedl_distinct_{fld}", S, {**BB, "where": "1=1", "outFields": fld, "returnDistinctValues": "true", "returnGeometry": "false"})
q("siedl_stats_moisture", S, {**BB, "where": "1=1", "groupByFieldsForStatistics": "moisture_cd",
                              "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "site_type_id", "outStatisticFieldName": "n"}])})
q("siedl_stats_soil", S, {**BB, "where": "1=1", "groupByFieldsForStatistics": "soil_subtype_cd",
                          "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "site_type_id", "outStatisticFieldName": "n"}])})
W6 = f"{D}/6/query"
q("pozaLP_stats_owner", W6, {**BB, "where": "1=1", "groupByFieldsForStatistics": "owner_cat_name",
                            "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "subarea_id", "outStatisticFieldName": "n"},
                                                         {"statisticType": "sum", "onStatisticField": "sub_area", "outStatisticFieldName": "ha"}])})
q("pozaLP_stats_year", W6, {**BB, "where": "1=1", "groupByFieldsForStatistics": "a_year",
                           "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "subarea_id", "outStatisticFieldName": "n"}])})
q("LP_stats_partcd", f"{D}/5/query", {**BB, "where": "1=1", "groupByFieldsForStatistics": "part_cd",
                                       "outStatistics": json.dumps([{"statisticType": "count", "onStatisticField": "subarea_id", "outStatisticFieldName": "n"}])})
q("zakazy_all", f"{R}/WMS_zakazy_wstepu_do_lasu/MapServer/0/query", {"where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json"})
(OUT / "recon4.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("ok", {k: ("blad" in v) for k, v in res.items()})
