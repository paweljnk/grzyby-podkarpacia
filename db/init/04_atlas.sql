-- Atlas: zdjęcia z licencją i ręcznym zatwierdzaniem (Etap 4b).
CREATE SCHEMA IF NOT EXISTS atlas;
CREATE TABLE IF NOT EXISTS atlas.zdjecie (
    id               bigserial PRIMARY KEY,
    gatunek_id       text NOT NULL,
    ujecie           text CHECK (ujecie IN ('mlody', 'dojrzaly', 'spod', 'trzon', 'przekroj', 'inne')),
    autor            text NOT NULL,
    licencja         text NOT NULL,
    licencja_url     text,
    zrodlo_url       text NOT NULL,                -- strona pliku (np. Commons File:...)
    plik_url         text,                         -- adres pobranej miniatury
    plik             text,                         -- ścieżka lokalna w data/atlas
    sha1             text,
    szerokosc        integer,
    wysokosc         integer,
    opis_zrodla      text,
    pobrano_utc      timestamptz NOT NULL DEFAULT now(),
    status           text NOT NULL DEFAULT 'do_weryfikacji'
                     CHECK (status IN ('do_weryfikacji', 'zatwierdzone', 'odrzucone')),
    zatwierdzil      text,
    zatwierdzono_utc timestamptz,
    adnotacje        jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{x:0..1, y:0..1, tekst}] — cechy zaznaczone przez weryfikatora
    przerobka        boolean NOT NULL DEFAULT false,       -- kadr/przeróbka: przy CC BY-SA na tej samej licencji
    uwagi            text,
    UNIQUE (zrodlo_url),
    CHECK (status <> 'zatwierdzone' OR (zatwierdzil IS NOT NULL AND ujecie IS NOT NULL AND plik IS NOT NULL))
);
