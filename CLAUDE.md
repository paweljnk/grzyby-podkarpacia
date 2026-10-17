# CLAUDE.md — Grzyby Podkarpacia

Przed pracą przeczytaj `README.md`, `sources.yaml`, `docs/pokrycie_danych.md` i `docs/zalozenia.md`.

Zasady obowiązujące w każdym etapie:
- Nie wymyślaj endpointów, warstw ani atrybutów. Uruchom `make probe` i mapuj pola wyłącznie na
  podstawie `docs/schemas/<id>.json` (w `config/bdl_mapping.yaml`). Gdy źródło jest niedostępne, napisz to wprost.
- Każde nowe źródło dopisz do `sources.yaml`. Importer musi pisać do `meta.import_log` przez `grzyby.db.import_run`.
- Pobieranie danych idzie tylko przez `grzyby.etl.http.HttpClient`: cache, limit na host, backoff, bez ponawiania 401/403/407.
- EPSG:2180 w bazie, EPSG:4326 w API. Czas: UTC w bazie, Europe/Warsaw w prezentacji.
- Brak danych zapisuj jako NULL z pochodzeniem `brak`. Nie wstawiaj wartości zastępczych.
- Dane demonstracyjne tylko w schemacie `demo`.
- Wagi i progi trzymaj w `config/`, nie w kodzie.
- Nie używaj tile.openstreetmap.org.
- Aplikacja nie ocenia jadalności okazów.

Polecenia: `make up | probe | import-pilot | check-data | test | test-db`.
Na końcu etapu raportuj: co pobrano (źródło, liczba rekordów, obszar), testy (komendy i wyniki),
co uruchomiono, co nie zadziałało i czego brakuje.
