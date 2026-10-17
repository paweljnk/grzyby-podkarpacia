# Pokrycie danych — pilotaż

## Stan danych rzeczywistych (2026-10-17, import z GitHub Actions)

Dane pobiera codziennie `.github/workflows/dane.yml` (serwery GitHuba mają dostęp do źródeł, którego nie ma
środowisko deweloperskie). Paczka: gałąź `dane/pilot` (manifest, raport `check-data`, log). Aplikacja wczytuje ją sama.

| Warstwa | Źródło | Rekordy | Braki |
|---|---|---|---|
| Granice nadleśnictw (obszary pilotażowe) | BDL, kolekcja `nadlesnictwa` | 2 (Głogów Małopolski 04-08, Baligród 04-01) | — |
| Wydzielenia (tylko drzewostany, `area_type=D-STAN`) | BDL OGC API, RDLP Krosno | 6256 (Głogów 3487, Baligród 2769) | gatunek panujący, wiek, TSL: 0%; **udziały gatunków i gleba: 100%** (usługa ich nie udostępnia) |
| Rzeźba terenu dla wydzieleń | Copernicus DEM GLO-30 (DSM) | 6256 | 0% |
| Pogoda | Open-Meteo: reanaliza (ERA5+ERA5-Land), analiza (ostatnie 10 dni), prognoza (7 dni) | 23 komórki, ok. 1770 dób | opad i ET₀ 100% |
| Granica województwa | PRG (WFS, warstwa `ms:A01_Granice_wojewodztw`) | 1 | pola TERYT nie zmapowane (wybór geometryczny) |
| Formy ochrony przyrody | GDOŚ | 0 | **HTTP 403 także z GitHub Actions** — do wyjaśnienia |
| Zakazy wstępu | — | 0 | brak źródła — aplikacja pokazuje „nie da się sprawdzić” |

Wnioski z prawdziwych danych (poprawione w kodzie):
- Model `era5_land` w Open-Meteo nie podaje opadu ani ET₀ — archiwum korzysta z domyślnego połączenia ERA5 + ERA5-Land.
- BDL używa dokładniejszych kodów siedlisk górskich (LGŚW, LMGŚW, BMGŚW, LŁG, OLJG…) — słownik ujednolicony.
- Kod `DB.C` (dąb czerwony, gatunek obcy) jest rozdzielony od dębów rodzimych.

# Pilotaż — Etap 1 (stan pierwotny)

Stan na: 2026-10-17. Obszary pilotażowe: **Nadleśnictwo Głogów Małopolski** (nizinne, bory sosnowe)
i **Nadleśnictwo Baligród** (górskie, buczyny i jodła). Do czasu pobrania granic nadleśnictw z BDL
oba obszary są zdefiniowane prostokątami roboczymi z `config/pilot.yaml` (`geom_origin = 'bbox_roboczy'`).
Prostokąt roboczy nie jest granicą nadleśnictwa.

Liczby poniżej pochodzą z `make check-data`. Uruchom je ponownie po każdym imporcie.

## 1. Co udało się pobrać

| Warstwa | Źródło | Rekordy | Obszar | Uwagi |
|---|---|---|---|---|
| Obszary pilotażowe | `config/pilot.yaml` | 2 | 2 prostokąty robocze | do zastąpienia granicami z BDL |
| Rastry rzeźby terenu (wysokość, nachylenie, ekspozycja) | Copernicus DEM GLO-30 | 6 rastrów (3 kafle 1×1°, ok. 100 MB) | oba obszary, EPSG:2180, 25 m | DSM, nie NMT (zob. niżej) |
| Granica województwa | PRG GUGiK | 0 | — | host zablokowany przez politykę sieci środowiska |
| Wydzielenia leśne z atrybutami | BDL OGC API | 0 | — | host zablokowany |
| Statystyki strefowe rzeźby terenu dla wydzieleń | DEM × wydzielenia | 0 | — | kod gotowy i przetestowany; brak wydzieleń |
| Formy ochrony przyrody | GDOŚ CRFOP | 0 | — | host zablokowany |

Braki w rastrach (piksele NaN):

| Raster | Pikseli | NaN | Przyczyna |
|---|---|---|---|
| baligrod: wysokość | 2 112 264 | 170 825 (8,1%) | narożniki siatki EPSG:2180 poza prostokątem WGS84 (po reprojekcji prostokąt staje się trapezem) |
| baligrod: nachylenie / ekspozycja | 2 112 264 | 8,4% / 9,4% | jak wyżej, plus 1 piksel brzegu (okno Horna 3×3); ekspozycja dodatkowo NaN na terenie idealnie płaskim |
| glogow_malopolski: wysokość | 2 751 826 | 215 818 (7,8%) | jak wyżej |
| glogow_malopolski: nachylenie / ekspozycja | 2 751 826 | 8,1% / 8,2% | jak wyżej |

Zakresy wysokości: Głogów Młp. 155,6–337,0 m, Baligród 324,5–1246,9 m n.p.m.

**Kontrola wiarygodności DEM** (nie jest to walidacja): maksimum w promieniu 2 km od Łopiennika
(1069 m n.p.m.) wynosi 1071,9 m. Dla Chryszczaty (997 m) maksimum w promieniu 2 km to 947,9 m.
Rozbieżność wynika najpewniej z niedokładnych współrzędnych referencyjnych, których użyłem,
a nie z danych. Tej kontroli nie uznaję za potwierdzenie. Rzetelne porównanie zrobimy z NMT GUGiK.

## 2. Ograniczenia użytego DEM

Copernicus DEM to **numeryczny model pokrycia terenu (DSM)**: obejmuje korony drzew i budynki.
W lesie wysokość jest zawyżona o wysokość drzewostanu, czyli w starodrzewiu o 20–35 m.
Na skrajach lasu i przy zrębach powstają sztuczne stoki. Do pilotażu wystarczy to do
ekspozycji i nachylenia w terenie górskim. W terenie płaskim (Kotlina Sandomierska) nachylenie
z DSM jest w dużej mierze artefaktem drzewostanu. Docelowym źródłem jest NMT GUGiK (DTM),
agregowany z 1 m do 25 m.

Natywna rozdzielczość GLO-30 to ok. 30 m (N–S) × ok. 20 m (E–W) na 50°N, a powyżej 50°N siatka
jest 1,5 raza szersza w długości. Siatka zapisu 25 m nie zwiększa rzeczywistej szczegółowości.
Wartości wysokości odnoszą się do geoidy EGM2008 według specyfikacji produktu. Metadane pliku
tego nie zawierają: plik ma `crs = EPSG:4326`, `nodata = null`, `AREA_OR_POINT = Point`
(zob. `docs/schemas/copernicus_dem_glo30.json`).

## 3. Lasy państwowe a pozostałe

Tego **nie udało się jeszcze zweryfikować na danych**, bo BDL jest niedostępny z tego środowiska.
Do sprawdzenia po odblokowaniu:

| Pytanie | Jak sprawdzimy |
|---|---|
| Czy OGC API BDL udostępnia opis taksacyjny (gatunki, udziały, wiek, typ siedliskowy, gleba) dla wydzieleń LP? | `make probe` → `docs/schemas/bdl_ogcapi.json`: lista kolekcji i próbka atrybutów |
| Czy dla lasów niepaństwowych (UPUL, inwentaryzacje) są te same pola? | porównanie wypełnienia pól w `make check-data` w podziale na rodzaj własności (po zmapowaniu pola własności) |
| Ile wydzieleń ma braki w poszczególnych polach? | `make check-data` drukuje braki dla kolumn znormalizowanych i dla każdego surowego klucza `attrs` |
| Czym uzupełniać lasy bez opisu taksacyjnego? | BDOT10k (pokrycie terenu), Copernicus HRL Tree Cover Density / Forest Type. HRL wymaga konta EU Login |

Dopóki pole nie zostanie zmapowane na podstawie rzeczywistego schematu, ma w bazie wartość `NULL`
i pochodzenie `brak`.

## 4. Licencje

| Źródło | Licencja | Wymagane oznaczenie | Status |
|---|---|---|---|
| Copernicus DEM GLO-30 | licencja Copernicus DEM GLO-30 Public (bezpłatna) | „© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved” | dane pobrane |
| PRG, NMT, BDOT10k (GUGiK) | dane otwarte GUGiK | Główny Urząd Geodezji i Kartografii | do weryfikacji |
| BDL | **nieustalona** — sprawdzić regulamin BDL | nieustalone | do weryfikacji |
| GDOŚ CRFOP | nieustalona | GDOŚ | do weryfikacji |
| Open-Meteo | dane CC BY 4.0; darmowe API tylko niekomercyjnie | Weather data by Open-Meteo.com | do weryfikacji |
| ERA5 / ERA5-Land | licencja Copernicus C3S | Copernicus Climate Change Service | do weryfikacji |
| IMGW-PIB | nieustalona — regulamin danepubliczne.imgw.pl | formuła z regulaminu | do weryfikacji |
| GBIF | per rekord; przyjmujemy tylko CC0 i CC BY | cytowanie DOI pobrania | do weryfikacji |
| SoilGrids | CC BY 4.0 | ISRIC | do weryfikacji |
| OpenFreeMap / OSM | ODbL | © OpenMapTiles, © OpenStreetMap contributors | do weryfikacji |

Pełny rejestr z URL, zasięgiem, rozdzielczością, metodą i datą importu: `sources.yaml`.

## 5. Niedostępne źródła (stan próbkowania 2026-10-17)

Wszystkie źródła poza Copernicus DEM zwróciły **403 przy zestawianiu tunelu przez proxy
środowiska**. To polityka sieci kontenera, a nie awaria usług. Szczegóły są w `docs/schemas/<id>.json`
i w polu `weryfikacja` w `sources.yaml`. Schematów tych źródeł nie zapisujemy, dopóki nie pobierzemy próbki.
