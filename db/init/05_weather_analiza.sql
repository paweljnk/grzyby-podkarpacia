-- Typ 'analiza': analiza operacyjna modelu dla dni minionych (API prognozy, past_days), gdy reanaliza
-- ERA5-Land jeszcze nie obejmuje ostatnich dni. Nie jest to ani pomiar, ani prognoza.
ALTER TABLE weather.dzien DROP CONSTRAINT IF EXISTS dzien_typ_check;
ALTER TABLE weather.dzien ADD CONSTRAINT dzien_typ_check CHECK (typ IN ('stacja', 'reanaliza', 'analiza', 'prognoza'));
ALTER TABLE demo.dzien DROP CONSTRAINT IF EXISTS dzien_typ_check;

-- Paczki danych (snapshot) wczytane z publikacji GitHub Actions.
CREATE TABLE IF NOT EXISTS meta.snapshot (
    id             bigserial PRIMARY KEY,
    wygenerowano   timestamptz NOT NULL,
    wczytano       timestamptz NOT NULL DEFAULT now(),
    zrodlo_url     text,
    manifest       jsonb NOT NULL
);
