# Pokrycie danych — województwo podkarpackie

## Stan danych rzeczywistych (2026-10-17, import z GitHub Actions)

Pakiet `baza` (co miesiąc, `.github/workflows/dane-baza.yml`, gałąź `dane/baza`) i pakiet `dzienne` (codziennie,
`dane.yml`, gałąź `dane/dzienne`). Pełny raport: `raport_pokrycia.md` na gałęzi `dane/baza` (`make raport` lokalnie).

| Warstwa | Źródło | Rekordy (w granicach województwa) | Braki |
|---|---|---|---|
| Nadleśnictwa przecinające województwo (≥1 ha) | BDL ArcGIS REST, warstwa „Nadleśnictwa” | 38 (RDLP Krosno 26, Lublin 8, Kraków 4 — także częściowo poza województwem) | — |
| Drzewostany LP (`D-STAN%`) | BDL REST „Wydzielenia PGL LP” | 99 412 wydzieleń, 489 444 ha | udział panującego: 3; gleba: 18 645; uwilgotnienie: 21 471 |
| Drzewostany poza LP (wg PUL) | BDL REST „Wydzielenia poza PGL LP” | 145 121 wydzieleń, 178 544 ha (prywatne 112 tys. ha, parki narodowe 40 tys. ha, gminne 25 tys. ha) | gleba i uwilgotnienie: ~100% (warstwa siedlisk obejmuje lasy LP) |
| Siedliska (gleba, uwilgotnienie) | BDL REST „Siedliska leśne” | 97 842 płatów | słownik `moisture_cd` nieopublikowany |
| pH gleby | SoilGrids 2.0 (model 250 m, Q0.05–Q0.95) | 243 640 wydzieleń | 893 bez wartości |
| Rzeźba terenu | Copernicus DEM GLO-30 | 244 533 | — |
| Warstwa referencyjna lasów | ESA WorldCover 2021, „Tree cover” | 17 907 komórek 1 km, 963 380 ha | obejmuje też zadrzewienia |
| Zakazy wstępu do lasu | BDL REST | 789 w kraju, 0 w województwie (w RDLP Krosno brak zakazów 17.10.2026) | — |
| Formy ochrony przyrody | GDOŚ | 0 | HTTP 403 także z GitHub Actions; parki narodowe z kategorii własności BDL |

**Pokrycie** (min(BDL, WorldCover) w komórkach 1 km): **68,8%** całej klasy „Tree cover”; **79,8%** w komórkach
zdominowanych przez las (≥50 ha drzew/km²). Komórki: pełniejsze 5 799, częściowe 5 856, bez możliwości oceny 6 252.
Liczba nadleśnictw nie oznacza pełnego pokrycia: lasy prywatne bez planu urządzenia lasu nie mają opisu w BDL.

Kontrola jakości: duplikaty pominięte przy imporcie (LP 209, poza LP 15 141, siedliska 12 668 — nakładające się kafle);
naprawione geometrie: 116 / 257 / 135; niepoprawne geometrie po imporcie: 0; duplikaty adresu LP: 0; identyczne
geometrie: 30 par.

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
