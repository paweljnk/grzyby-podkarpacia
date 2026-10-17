# Grzyby Podkarpacia — polecenia projektu.
COMPOSE ?= docker compose
RUN := $(COMPOSE) run --rm etl

.PHONY: web up down build migrate probe import-pilot import-woj raport import-weather demo-data api check-data test test-db e2e reset-db

up:            ## baza + kontener ETL
	$(COMPOSE) up -d --build --wait db
	$(COMPOSE) up -d --build etl api

migrate:       ## idempotentne zastosowanie db/init/*.sql na istniejącej bazie
	for f in db/init/*.sql; do $(COMPOSE) exec -T db psql -q -v ON_ERROR_STOP=1 -c "SET client_min_messages=warning" -U grzyby -d grzyby -f /docker-entrypoint-initdb.d/$$(basename $$f) || exit 1; done

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build etl

probe:         ## próbki źródeł → docs/schemas/*.json + weryfikacja w sources.yaml
	$(RUN) python -m grzyby.cli probe

import-pilot:  ## PRG, BDL, DEM (+ statystyki strefowe), GDOŚ dla obszarów pilotażowych
	$(RUN) python -m grzyby.cli import all

import-woj:    ## całe województwo: PRG, BDL REST (LP + poza LP + siedliska), DEM, SoilGrids, WorldCover, pokrycie (przyrostowo)
	$(RUN) python -m grzyby.cli import wojewodztwo-all

raport:        ## raport pokrycia danymi → data/raport_pokrycia.md
	$(RUN) python -m grzyby.cli raport data

import-weather: ## pogoda Open-Meteo dla komórek siatki pokrywających wydzielenia
	$(RUN) python -m grzyby.cli import weather

demo-data:     ## DANE DEMONSTRACYJNE w schemacie demo (fikcyjne drzewostany i pogoda; prawdziwy DEM)
	$(RUN) python -m grzyby.cli demo

check-data:    ## liczba rekordów i braków w każdej warstwie
	$(RUN) python -m grzyby.cli check-data

web:           ## zbudowanie PWA (frontend/dist, serwowane przez API pod /)
	cd frontend && npm ci --no-audit --no-fund && npm run build

e2e:           ## Playwright, ekran 390x844 (wymaga działającego API z danymi demo)
	cd frontend && PW_CHROMIUM=$${PW_CHROMIUM:-$$(ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)} npx playwright test

test:          ## testy jednostkowe (bez sieci)
	$(RUN) pytest -q -m "not db" backend/tests

test-db:       ## testy integracyjne na bazie
	$(RUN) pytest -q -m db backend/tests

reset-db:      ## UWAGA: usuwa wolumen z danymi bazy
	$(COMPOSE) down -v
