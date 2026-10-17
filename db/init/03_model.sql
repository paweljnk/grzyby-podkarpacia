-- Obserwacje użytkowników (Etap 5 wypełni je z dziennika) i zakazy wstępu.
CREATE SCHEMA IF NOT EXISTS obs;
CREATE TABLE IF NOT EXISTS obs.obserwacja (
    id                 bigserial PRIMARY KEY,
    user_id            bigint,
    species_id         text NOT NULL,
    czas_utc           timestamptz NOT NULL,
    znaleziono         boolean NOT NULL,          -- false = "szukałem — nic nie znalazłem"
    liczba_okazow      integer,
    czas_szukania_min  integer,
    jakosc             text NOT NULL DEFAULT 'srednia' CHECK (jakosc IN ('wysoka', 'srednia', 'niska')),
    udostepniona       boolean NOT NULL DEFAULT false,
    pochodzenie        meta.pochodzenie NOT NULL DEFAULT 'obserwacja_uzytkownika',
    geom               geometry(Point, 2180) NOT NULL
);
CREATE INDEX IF NOT EXISTS obserwacja_geom_idx ON obs.obserwacja USING gist (geom);

CREATE SCHEMA IF NOT EXISTS access;
-- Czasowe zakazy wstępu (pożarowe, prace leśne, ASF, polowania). Źródło: BDL/LP — po weryfikacji.
CREATE TABLE IF NOT EXISTS access.zakaz (
    id          bigserial PRIMARY KEY,
    source_id   text NOT NULL,
    rodzaj      text NOT NULL,
    od          date,
    do_dnia     date,
    opis        text,
    attrs       jsonb NOT NULL DEFAULT '{}'::jsonb,
    geom        geometry(MultiPolygon, 2180) NOT NULL,
    import_id   bigint REFERENCES meta.import_log(id)
);
CREATE INDEX IF NOT EXISTS zakaz_geom_idx ON access.zakaz USING gist (geom);

-- Lustrzane tabele danych DEMONSTRACYJNYCH (bez kluczy obcych do danych rzeczywistych).
CREATE TABLE IF NOT EXISTS demo.wydzielenie        (LIKE forest.wydzielenie INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.wydzielenie_teren  (LIKE terrain.wydzielenie_teren INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.komorka            (LIKE weather.komorka INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.dzien              (LIKE weather.dzien INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.wydzielenie_komorka (LIKE forest.wydzielenie_komorka INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.forma_ochrony      (LIKE protection.forma_ochrony INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.obserwacja         (LIKE obs.obserwacja INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.zakaz              (LIKE access.zakaz INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS demo.metadane (klucz text PRIMARY KEY, wartosc text);
