# Weryfikacja źródeł — 2026-10-17

Sprawdzone na prośbę: BDL (portal, OGC API, OpenAPI), IMGW (API i archiwum), Open-Meteo (prognoza i historia),
Geoportal GUGiK, SoilGrids, GDOŚ, publikacje LP, literatura mykologiczna, astronomia i biodynamika.

## Jak sprawdzano

| Kanał | Wynik |
|---|---|
| Kontener (curl przez proxy) | wszystkie wskazane hosty: **403 przy CONNECT** — polityka sieci środowiska |
| Narzędzie WebFetch | **błąd DNS dla każdej domeny** (także wikipedia.org) — awaria narzędzia, nie serwisów |
| Wyszukiwarka (WebSearch) | działa — poniższe ustalenia pochodzą z wyników wyszukiwania, nie z odczytu samych usług |

Wniosek: **żaden schemat danych nie został odczytany z usługi.** Ustalenia poniżej dotyczą dokumentacji,
licencji i bibliografii. Mapowanie pól (`config/bdl_mapping.yaml`) pozostaje puste do czasu `make probe`.

## Ustalenia, które zmieniają projekt

| Źródło | Ustalenie | Zmiana w projekcie |
|---|---|---|
| SoilGrids | **REST API wstrzymane przez ISRIC**, bez terminu przywrócenia; licencja CC BY 4.0 potwierdzona | `sources.yaml`: pobieranie rastrów (WCS/WebDAV) zamiast REST |
| Open-Meteo | dane **CC BY 4.0** (komercyjnie z oznaczeniem); darmowe API **tylko niekomercyjnie**, 10 000 wywołań/dzień, 5 000/h | licencja i limity w `sources.yaml`; publikacja komercyjna wymaga płatnego API |
| Open-Meteo, historia | ERA5 0,25° od 1940; **ERA5-Land 0,1° (~9 km) od 1950**; gleba 0–7 cm; ET₀ wg FAO-56 (suma z poprzedzającej godziny) | zgodne z `config/pogoda.yaml` (archiwum) |
| Open-Meteo, prognoza | nazwy `soil_moisture_3_to_9cm` / `soil_temperature_6cm` **niepotwierdzone**; strony modeli ECMWF podają warstwy 0–7/7–28/28–100/100–255 cm | oznaczone jako niezweryfikowane; parser odrzuci odpowiedź bez tych zmiennych |
| GDOŚ | WFS `https://sdi.gdos.gov.pl/wfs`, WMS `https://sdi.gdos.gov.pl/wms`; parki narodowe, krajobrazowe, rezerwaty, Natura 2000 (OSO/SOO). **Dane Geoserwisu nie są prawnym ustaleniem przebiegu granic** | adres potwierdzony; ostrzeżenie trafi do karty miejsca |
| BDL | portal udostępnia WMS, WMTS, WFS i **OGC API Features**; w WMS są warstwy wydzieleń „w PGL LP” i „poza PGL LP wg UPUL” | lasy niepaństwowe z UPUL prawdopodobnie dostępne — do potwierdzenia próbką |
| BDL | **licencji / regulaminu nie znaleziono** | `licencja: null` pozostaje; blokuje publikację |
| IMGW | regulaminu danepubliczne.imgw.pl nie odczytano; inne serwisy IMGW wymagają wskazania IMGW-PIB i oznaczenia danych przetworzonych | przyjęte tymczasowo, `do_weryfikacji` |
| LP — „Grzyby polskich lasów” | atlas P. Zarzyńskiego dla Centrum Informacyjnego LP (ok. 508 s., >200 gatunków); rok i ISBN nieustalone | dodany do `species/_zrodla.yaml` (klasa B, niezweryfikowany); treści nie cytujemy bez dostępu do książki |
| Zbiór w rezerwatach | część mediów pisze o „całkowitym zakazie” w rezerwatach; zasada projektu: wg aktu ustanawiającego | bez zmian — rezerwat = „sprawdź akt”, nie automatyczny zakaz, dopóki nie mamy aktów |

## Bibliografia mykologiczna (potwierdzone metadane)

| Klucz | Potwierdzono |
|---|---|
| `dentinger_2010` | Mol. Phylogenet. Evol. 57(3): 1276–1292, doi:10.1016/j.ympev.2010.10.004 |
| `vizzini_2014` | Index Fungorum 147: 1 — rodzaj *Imleria*, *I. badia* (Fr.) Vizzini; data wydania podawana jako 12.05 lub 12.06.2014 |
| `olariaga_2017` | Fungal Diversity 83(1): 263–292, doi:10.1007/s13225-016-0376-7; 8 gatunków *Cantharellus* w Europie, epityp *C. cibarius* |
| `boddy_2014` | Fungal Ecology 10: 20–33, doi:10.1016/j.funeco.2013.10.006 — przegląd, **bez progów liczbowych dla gatunków** |
| `kauserud_2008` | PNAS 105: 3811–3814, doi:10.1073/pnas.0709037105 |

Treści publikacji nie czytano (tylko streszczenia z wyników wyszukiwania). Reguły pogodowe w `species/*.yaml`
pozostają klasy C — żadne ze znalezionych źródeł nie podaje progów opadów ani opóźnień dla tych gatunków.
Przewodniki B (Gumińska i Wojewoda 1985, Funga Nordica 2012, Wojewoda 2003) nie zostały potwierdzone wyszukiwaniem.

## Astronomia i biodynamika

- Efemerydy: JPL DE421 z pakietu `skyfield-data` (PyPI). Momenty 3 faz zgodne z tabelami USNO z dokładnością < 2 min (test `test_astro.py`).
- Granice gwiazdozbiorów: IAU (Delporte 1930), tabela Roman 1987 (CDS VI/42) dołączona do `skyfield`.
- Biodynamika: wyszukiwanie potwierdza podział M. Thun na dni korzenia, liścia, kwiatu i owocu według przejścia Księżyca
  i związek z cyklem **syderycznym**. **Nie znaleziono pierwotnego, udokumentowanego zestawu granic gwiazdozbiorów
  Thun** (strony internetowe opisują system przez znaki zodiaku, co jest niezgodne z metodą). Dlatego używamy
  jawnych granic IAU — wyniki mogą się różnić od publikowanych kalendarzy Thun. Znaleziono też wzmiankę
  o szwedzkich doświadczeniach z marchwią, które nie potwierdziły teorii Thun (repozytorium GUPEA, Uniwersytet w Göteborgu).

## Linki z wyszukiwania

- BDL: [usługi OGC (EN)](https://bdl.lasy.gov.pl/portal/uslugi-ogc-en), [instrukcja OGC (PDF)](https://www.bdl.lasy.gov.pl/portal/Media/ogc/instrukcja_ogc.pdf), [usługi mapowe OGC](https://bdl.lasy.gov.pl/portal/uslugi-mapowe-ogc-en)
- GUGiK: [OGC API Features dla PRG i PRNG](https://www.geoportal.gov.pl/aktualnosci/nowe-uslugi-ogc-api-features-dla-danych-prg-i-prng/), [usługi OGC API Features](https://www.geoportal.gov.pl/pl/usluga/uslugi-ogc-api-features/)
- GDOŚ: [RDOŚ Poznań — dostęp do danych](https://www.gov.pl/web/rdos-poznan/dostep-do-danych-geoprzestrzennych), [RDOŚ Bydgoszcz — dane](https://www.gov.pl/web/rdos-bydgoszcz/dane)
- Open-Meteo: [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), [ECMWF API](https://open-meteo.com/en/docs/ecmwf-api), [Pricing](https://open-meteo.com/en/pricing), [strona główna](https://open-meteo.com/), [DWD ICON API](https://open-meteo.com/en/docs/dwd-api)
- SoilGrids: [ISRIC SoilGrids](https://www.isric.org/explore/soilgrids), [dokumentacja](https://docs.isric.org/globaldata/soilgrids/), [katalog GEE](https://gee-community-catalog.org/projects/isric/)
- IMGW: [regulamin projektu PMAXTP](https://klimat.imgw.pl/opady-maksymalne)
- LP: [atlas „Grzyby polskich lasów”](https://www.designandpaper.com/explore-the-funghi-world-of-poland-with-the-grzyby-polskich-lasow-atlas/), [wykaz grzybów, SGGW](https://cepl.sggw.edu.pl/wp-content/uploads/sites/75/2021/08/Grzywacz_Pietka_Szczepkowski.pdf)
- Mykologia: [Olariaga i in. 2017](https://www.ehu.eus/en/web/numaps/-/cantharellus-cantharellales-basidiomycota-revisited-in-europe-through-a-multigene-phylogeny), [Boddy i in. 2014](https://pure.royalholloway.ac.uk/en/publications/climate-variation-effects-on-fungal-fruiting/), [Kauserud i in. 2008](https://mn.uio.no/ibv/english/people/aca/haavarka/Kauserud%20et%20al%202008.pdf), [Dentinger i in. 2010](https://db.cngb.org/data_resources/literature/20970511), [Imleria — GBIF](https://gbif.org/species/7621106)
- Biodynamika: [Gardening for Life (Thun)](https://steiner.presswarehouse.com/browse/book/9781869890322/Gardening-for-Life), [GUPEA](https://gupea.ub.gu.se/handle/2077/51320)
