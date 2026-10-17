CREATE SCHEMA IF NOT EXISTS weather;

-- Komórki siatki pogodowej. Wartości pogodowe dotyczą komórki, nie konkretnego lasu.
CREATE TABLE IF NOT EXISTS weather.komorka (
    id        text PRIMARY KEY,                 -- np. 'g0.1:49.30:22.30'
    lat       double precision NOT NULL,
    lon       double precision NOT NULL,
    krok_st   double precision NOT NULL,
    geom      geometry(Polygon, 2180) NOT NULL
);
CREATE INDEX IF NOT EXISTS komorka_geom_idx ON weather.komorka USING gist (geom);

-- Dobowe wartości dla komórki i doby lokalnej (Europe/Warsaw).
CREATE TABLE IF NOT EXISTS weather.dzien (
    komorka_id         text NOT NULL REFERENCES weather.komorka(id),
    data_lokalna       date NOT NULL,
    typ                text NOT NULL CHECK (typ IN ('stacja', 'reanaliza', 'prognoza')),
    model              text,
    rozdzielczosc_km   real,
    godzin             smallint NOT NULL,       -- 23/24/25 przy zmianie czasu
    opad_mm            real,
    temp_min_c         real,
    temp_sr_c          real,
    temp_max_c         real,
    wilg_powietrza_pct real,
    wilg_gleby_m3m3    real,
    temp_gleby_c       real,
    et0_mm             real,
    pochodzenie        meta.pochodzenie NOT NULL,
    zrodlo_lat         double precision,        -- współrzędne punktu siatki modelu zwrócone przez API
    zrodlo_lon         double precision,
    pobrano_utc        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (komorka_id, data_lokalna, typ)
);

CREATE TABLE IF NOT EXISTS forest.wydzielenie_komorka (
    wydzielenie_id bigint PRIMARY KEY REFERENCES forest.wydzielenie(id) ON DELETE CASCADE,
    komorka_id     text NOT NULL REFERENCES weather.komorka(id)
);
