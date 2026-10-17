-- Zasięg wojewódzki, lasy poza LP, siedliska (gleba, uwilgotnienie), SoilGrids, pokrycie danych.

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['forest.wydzielenie', 'demo.wydzielenie'] LOOP
    EXECUTE format($f$
      ALTER TABLE %s
        ADD COLUMN IF NOT EXISTS zarzad text,                 -- 'LP' | 'poza_LP'
        ADD COLUMN IF NOT EXISTS wlasnosc text,               -- kategoria własności (lasy poza LP)
        ADD COLUMN IF NOT EXISTS nadl_kod text,               -- RR-NN (tylko LP)
        ADD COLUMN IF NOT EXISTS rok_danych integer,          -- a_year rekordu BDL (dla PUL: rok planu)
        ADD COLUMN IF NOT EXISTS w_wojewodztwie_frac real,    -- udział powierzchni w granicach województwa
        ADD COLUMN IF NOT EXISTS udzial_panujacego real,      -- part_cd/10 (udział gatunku panującego)
        ADD COLUMN IF NOT EXISTS udzial_panujacego_pochodzenie meta.pochodzenie NOT NULL DEFAULT 'brak',
        ADD COLUMN IF NOT EXISTS gleba_gatunek text,          -- soil_species z warstwy Siedliska leśne
        ADD COLUMN IF NOT EXISTS uwilgotnienie_kod text,      -- moisture_cd (kod BDL, słownik nieopublikowany)
        ADD COLUMN IF NOT EXISTS siedlisko_zrodlo text,       -- data_source warstwy Siedliska (SILP/PUL/OpracGS)
        ADD COLUMN IF NOT EXISTS siedlisko_rok integer,       -- valid_year warstwy Siedliska
        ADD COLUMN IF NOT EXISTS siedlisko_pokrycie real,     -- jaka część wydzielenia ma przypisane siedlisko
        ADD COLUMN IF NOT EXISTS ph_model real,               -- SoilGrids pH(H2O) 0-5 cm, średnia
        ADD COLUMN IF NOT EXISTS ph_q05 real,
        ADD COLUMN IF NOT EXISTS ph_q95 real,
        ADD COLUMN IF NOT EXISTS ph_pochodzenie meta.pochodzenie NOT NULL DEFAULT 'brak',
        ADD COLUMN IF NOT EXISTS klasa_danych text            -- 'pelniejsze' | 'czesciowe'
    $f$, t);
  END LOOP;
END $$;
CREATE INDEX IF NOT EXISTS wydzielenie_zarzad_idx ON forest.wydzielenie (zarzad);

CREATE TABLE IF NOT EXISTS ref.nadlesnictwo (
    kod                text PRIMARY KEY,          -- RR-NN
    nazwa              text NOT NULL,
    rdlp_kod           text NOT NULL,
    powierzchnia_ha    real,
    w_wojewodztwie_ha  real,
    geom               geometry(MultiPolygon, 2180) NOT NULL
);

-- Siedliska leśne (BDL): geometrie z atrybutami glebowymi; przypisywane do wydzieleń wg największego pokrycia.
CREATE TABLE IF NOT EXISTS forest.siedlisko (
    id               bigint PRIMARY KEY,         -- site_type_id
    site_type_cd     text,
    soil_subtype_cd  text,
    soil_species     text,
    moisture_cd      text,
    degradation_cd   text,
    geol_depos       text,
    data_source      text,
    a_year           integer,
    valid_year       integer,
    geom             geometry(MultiPolygon, 2180) NOT NULL
);
CREATE INDEX IF NOT EXISTS siedlisko_geom_idx ON forest.siedlisko USING gist (geom);

-- Postęp importu (wznawianie): jednostka = nadleśnictwo albo kafel.
CREATE TABLE IF NOT EXISTS meta.import_progress (
    source_id   text NOT NULL,
    unit        text NOT NULL,
    status      text NOT NULL,
    records     integer,
    finished_at timestamptz,
    PRIMARY KEY (source_id, unit)
);

-- Pokrycie danymi w siatce 1 km względem warstwy referencyjnej lasów (ESA WorldCover).
CREATE SCHEMA IF NOT EXISTS coverage;
CREATE TABLE IF NOT EXISTS coverage.siatka (
    ix                 integer NOT NULL,
    iy                 integer NOT NULL,
    las_ref_ha         real NOT NULL,
    bdl_ha             real,
    bdl_pelniejsze_ha  real,
    klasa              text,                      -- pelniejsze | czesciowe | brak_oceny
    geom               geometry(Polygon, 2180) NOT NULL,
    PRIMARY KEY (ix, iy)
);
CREATE INDEX IF NOT EXISTS siatka_geom_idx ON coverage.siatka USING gist (geom);

-- obszar analizy może być województwem (granica PRG), a nie tylko obszarem pilotażowym
ALTER TABLE ref.obszar_pilotazowy DROP CONSTRAINT IF EXISTS obszar_pilotazowy_typ_terenu_check;
ALTER TABLE ref.obszar_pilotazowy DROP CONSTRAINT IF EXISTS obszar_pilotazowy_geom_origin_check;
