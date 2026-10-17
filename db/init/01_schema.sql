-- Grzyby Podkarpacia — schemat bazy (Etap 1).
-- Geometrie przechowujemy w EPSG:2180 (PUWG 1992). Do API/mapy transformujemy do EPSG:4326.
-- Znaczniki czasu: timestamptz (zapis w UTC), prezentacja w Europe/Warsaw.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS forest;
CREATE SCHEMA IF NOT EXISTS terrain;
CREATE SCHEMA IF NOT EXISTS protection;
-- Dane demonstracyjne: wyłącznie tutaj, nigdy w schematach z danymi rzeczywistymi.
CREATE SCHEMA IF NOT EXISTS demo;
COMMENT ON SCHEMA demo IS 'Dane demonstracyjne. Interfejs musi je oznaczać. Nie łączyć z danymi rzeczywistymi.';

DO $$ BEGIN EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'UTC'); END $$;

-- Etykieta pochodzenia każdej wartości (zasada danych nr 3).
DO $$ BEGIN
  CREATE TYPE meta.pochodzenie AS ENUM
    ('pomiar', 'opis_taksacyjny', 'model', 'prognoza', 'obserwacja_uzytkownika', 'brak');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Log importów: każde uruchomienie importera zostawia wpis, także nieudane.
CREATE TABLE IF NOT EXISTS meta.import_log (
    id            bigserial PRIMARY KEY,
    source_id     text        NOT NULL,           -- klucz z sources.yaml
    target        text        NOT NULL,           -- tabela/plik docelowy
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    status        text        NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'ok', 'partial', 'failed', 'skipped')),
    records       integer,
    area          text,                           -- np. nazwa obszaru pilotażowego
    params        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    message       text
);
CREATE INDEX IF NOT EXISTS import_log_source_idx ON meta.import_log (source_id, started_at DESC);

-- Obszary pilotażowe. geom_origin mówi, skąd jest zasięg:
--  'bbox_roboczy'  – prostokąt z config/pilot.yaml (tylko do kadrowania rastrów),
--  'bdl'           – granica nadleśnictwa pobrana z BDL (docelowo).
CREATE TABLE IF NOT EXISTS ref.obszar_pilotazowy (
    id           text PRIMARY KEY,
    nazwa        text NOT NULL,
    typ_terenu   text NOT NULL CHECK (typ_terenu IN ('nizinny', 'gorski')),
    geom_origin  text NOT NULL CHECK (geom_origin IN ('bbox_roboczy', 'bdl')),
    geom         geometry(MultiPolygon, 2180) NOT NULL,
    import_id    bigint REFERENCES meta.import_log(id)
);

CREATE TABLE IF NOT EXISTS ref.wojewodztwo (
    id          bigserial PRIMARY KEY,
    source_id   text NOT NULL,
    teryt       text,
    nazwa       text,
    attrs       jsonb NOT NULL,                   -- surowe atrybuty źródła
    geom        geometry(MultiPolygon, 2180) NOT NULL,
    import_id   bigint REFERENCES meta.import_log(id)
);
CREATE INDEX IF NOT EXISTS wojewodztwo_geom_idx ON ref.wojewodztwo USING gist (geom);

-- Wydzielenia leśne. Surowe atrybuty trafiają do attrs (bez zgadywania nazw pól).
-- Kolumny znormalizowane są wypełniane wyłącznie według mapowania z config/bdl_mapping.yaml,
-- które uzupełnia się po odczytaniu rzeczywistego schematu (docs/schemas/).
CREATE TABLE IF NOT EXISTS forest.wydzielenie (
    id                         bigserial PRIMARY KEY,
    source_id                  text NOT NULL,
    external_id                text,
    obszar_id                  text REFERENCES ref.obszar_pilotazowy(id),
    adres_lesny                text,
    gatunek_panujacy           text,
    gatunek_panujacy_pochodzenie meta.pochodzenie NOT NULL DEFAULT 'brak',
    udzial_gatunkow            jsonb,             -- {"SO": 0.7, "BRZ": 0.3} wg opisu
    udzial_gatunkow_pochodzenie meta.pochodzenie NOT NULL DEFAULT 'brak',
    wiek                       integer,
    wiek_pochodzenie           meta.pochodzenie NOT NULL DEFAULT 'brak',
    typ_siedliskowy            text,
    typ_siedliskowy_pochodzenie meta.pochodzenie NOT NULL DEFAULT 'brak',
    gleba                      text,
    gleba_pochodzenie          meta.pochodzenie NOT NULL DEFAULT 'brak',
    attrs                      jsonb NOT NULL,
    geom                       geometry(MultiPolygon, 2180) NOT NULL,
    imported_at                timestamptz NOT NULL DEFAULT now(),
    import_id                  bigint REFERENCES meta.import_log(id),
    UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS wydzielenie_geom_idx ON forest.wydzielenie USING gist (geom);

-- Rzeźba terenu jako statystyki strefowe dla wydzieleń. Wartości z modelu wysokości
-- mają pochodzenie 'model' (DEM jest produktem modelowanym, nie pomiarem w terenie).
CREATE TABLE IF NOT EXISTS terrain.wydzielenie_teren (
    wydzielenie_id      bigint PRIMARY KEY REFERENCES forest.wydzielenie(id) ON DELETE CASCADE,
    dem_source_id       text NOT NULL,
    rozdzielczosc_m     real NOT NULL,
    n_pikseli           integer NOT NULL,
    wys_min             real,
    wys_sr              real,
    wys_max             real,
    nachylenie_sr_deg   real,
    nachylenie_max_deg  real,
    ekspozycja_sr_deg   real,                     -- średnia kołowa; NULL dla terenu płaskiego
    ekspozycja_klasa    text,                     -- N, NE, ..., 'plasko'
    pochodzenie         meta.pochodzenie NOT NULL DEFAULT 'model',
    import_id           bigint REFERENCES meta.import_log(id)
);

-- Rejestr rastrów pochodnych (pliki GeoTIFF w data/derived). Rastry trzymamy poza bazą.
CREATE TABLE IF NOT EXISTS terrain.raster (
    id               text PRIMARY KEY,           -- np. 'copernicus_dem_glo30:baligrod:wysokosc'
    source_id        text NOT NULL,
    obszar_id        text REFERENCES ref.obszar_pilotazowy(id),
    warstwa          text NOT NULL CHECK (warstwa IN ('wysokosc', 'nachylenie', 'ekspozycja')),
    sciezka          text NOT NULL,
    crs              text NOT NULL,
    rozdzielczosc_m  real NOT NULL,
    szerokosc_px     integer NOT NULL,
    wysokosc_px      integer NOT NULL,
    n_nodata         bigint NOT NULL,
    stat_min         real,
    stat_max         real,
    stat_sr          real,
    zasieg           geometry(Polygon, 2180) NOT NULL,
    pochodzenie      meta.pochodzenie NOT NULL DEFAULT 'model',
    import_id        bigint REFERENCES meta.import_log(id)
);

CREATE TABLE IF NOT EXISTS protection.forma_ochrony (
    id           bigserial PRIMARY KEY,
    source_id    text NOT NULL,
    warstwa      text NOT NULL,                   -- nazwa warstwy/typu obiektu w usłudze
    rodzaj       text,                            -- park_narodowy, rezerwat, ... (wg mapowania)
    nazwa        text,
    kod          text,
    attrs        jsonb NOT NULL,
    geom         geometry(MultiPolygon, 2180) NOT NULL,
    import_id    bigint REFERENCES meta.import_log(id)
);
CREATE INDEX IF NOT EXISTS forma_ochrony_geom_idx ON protection.forma_ochrony USING gist (geom);
