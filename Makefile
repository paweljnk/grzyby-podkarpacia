# Grzyby Podkarpacia — polecenia projektu.
COMPOSE ?= docker compose
RUN := $(COMPOSE) run --rm etl

.PHONY: up down build probe import-pilot check-data test test-db reset-db

up:            ## baza + kontener ETL
	$(COMPOSE) up -d --build --wait db
	$(COMPOSE) up -d --build etl

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build etl

probe:         ## próbki źródeł → docs/schemas/*.json + weryfikacja w sources.yaml
	$(RUN) python -m grzyby.cli probe

import-pilot:  ## PRG, BDL, DEM (+ statystyki strefowe), GDOŚ dla obszarów pilotażowych
	$(RUN) python -m grzyby.cli import all

check-data:    ## liczba rekordów i braków w każdej warstwie
	$(RUN) python -m grzyby.cli check-data

test:          ## testy jednostkowe (bez sieci)
	$(RUN) pytest -q -m "not db" backend/tests

test-db:       ## testy integracyjne na bazie
	$(RUN) pytest -q -m db backend/tests

reset-db:      ## UWAGA: usuwa wolumen z danymi bazy
	$(COMPOSE) down -v
