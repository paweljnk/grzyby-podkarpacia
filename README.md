# Grzyby Podkarpacia

Aplikacja ocenia **potencjał siedliska i sprzyjające warunki** dla wybranych gatunków grzybów
w województwie podkarpackim. Nie twierdzi, że grzyby gdzieś teraz rosną, i nie ocenia jadalności
żadnego okazu. Oznaczenie gatunku zawsze potwierdza grzyboznawca (punkty PSSE).

Stan: Etap 1 (pilotaż danych), Etap 2 (baza wiedzy o gatunkach MVP), Etap 3 (pogoda, Księżyc i biodynamika,
model rekomendacji, API) i Etap 4 (PWA) — zbudowane. Źródła BDL, GDOŚ, PRG i Open-Meteo są w tym środowisku
niedostępne (polityka sieci), dlatego aplikację można oglądać na **jawnie oznaczonych danych demonstracyjnych**.

## Instalacja na iPhonie

Krok po kroku (komputer w domu + tunel HTTPS, wystarczy Docker): [docs/instalacja_iphone.md](docs/instalacja_iphone.md).

## Szybki start (deweloperski)

```bash
make up            # PostGIS 16 + kontener ETL (Python 3.12)
make probe         # próbki źródeł → docs/schemas/*.json, status w sources.yaml
make import-pilot  # PRG, BDL, DEM + statystyki strefowe, GDOŚ dla obszarów pilotażowych
make check-data    # liczba rekordów i braków w każdej warstwie
make test          # testy jednostkowe (bez sieci)
make test-db       # testy integracyjne na bazie
make demo-data     # DANE DEMONSTRACYJNE (schemat demo): fikcyjne drzewostany i pogoda, prawdziwy DEM
make web           # zbudowanie PWA → frontend/dist (serwowane przez API)
make e2e           # Playwright, ekran 390×844
```

Aplikacja: http://localhost:8000 (API: `/api/ranking?species=&lat=&lon=&radius_km=&date=&calendar=on|off&dataset=real|demo`,
`/api/miejsce/{id}`, `/api/miejsce/{id}/7dni`, `/api/kalendarz`, `/api/porownanie`, `/api/mapa`, `/api/warstwy/ochrona`,
`/api/gatunki`, `/api/zrodla`; dokumentacja OpenAPI: `/docs`).

Za proxy HTTPS (kontener chmurowy): plik `.env` z
`COMPOSE_FILE=docker-compose.yml:docker-compose.proxy.yml` i certyfikat CA proxy w `backend/certs/*.crt`.

## Struktura

| Ścieżka | Zawartość |
|---|---|
| `sources.yaml` | rejestr źródeł: URL, zasięg, rozdzielczość, licencja, oznaczenie autorstwa, status weryfikacji, ostatni import |
| `config/pilot.yaml` | obszary pilotażowe i parametry analizy terenu (założenia) |
| `config/bdl_mapping.yaml` | mapowanie warstw i pól źródeł; wypełniane **po** odczytaniu rzeczywistego schematu |
| `db/init/` | schemat bazy (EPSG:2180, etykiety pochodzenia, log importów, schemat `demo`) |
| `backend/grzyby/etl/` | klient HTTP (cache, limity, backoff), próbkowanie, importery |
| `docs/schemas/` | rzeczywiste schematy próbek albo zapis o niedostępności |
| `docs/pokrycie_danych.md` | raport pokrycia danych i licencji |
| `docs/zalozenia.md` | założenia projektowe i metody (także model A/B/C/D) |
| `docs/weryfikacja_zrodel.md` | weryfikacja dokumentacji, licencji i bibliografii (2026-10-17) |
| `species/` | baza wiedzy o gatunkach (YAML + bibliografia `_zrodla.yaml`) |
| `config/model.yaml`, `config/kalendarz.yaml`, `config/pogoda.yaml` | wagi, progi i reguły (założenia projektowe) |
| `backend/grzyby/{weather,model,api}` | agregacja pogody, model rekomendacji, API |
| `frontend/` | PWA: React + TypeScript + Vite + MapLibre; testy e2e w `frontend/e2e` |
| `docs/zrzuty/` | zrzuty ekranów 390×844 (dane demo) |
| `data/` | surowe pliki, cache, rastry pochodne (poza repozytorium) |

## Zasady danych (skrót)

- Nie zgadujemy endpointów, warstw ani pól. Najpierw próbka i zapis schematu, potem mapowanie.
- Każda wartość ma etykietę pochodzenia (`meta.pochodzenie`). Brak danych to `NULL` z etykietą `brak`.
- Geometrie zapisujemy w EPSG:2180, a do API oddajemy w EPSG:4326. Czas zapisujemy w UTC, a pokazujemy w Europe/Warsaw.
- Dane demonstracyjne trzymamy tylko w schemacie `demo` i w katalogu `demo/`.
- Wagi i progi leżą w `config/`. To założenia projektowe, a nie ustalenia biologiczne.

## Oznaczenia autorstwa danych

- Rzeźba terenu: © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved.
