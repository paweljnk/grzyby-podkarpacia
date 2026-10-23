-- Katalog gatunków do przeglądania (GBIF + Wikidata + Wikipedia PL + Wikimedia Commons).
-- Materiał poglądowy: nie służy do oznaczania okazów; aplikacja nie ocenia jadalności.
CREATE TABLE IF NOT EXISTS atlas.katalog (
  id text PRIMARY KEY,                      -- nazwa naukowa w postaci 'boletus_edulis'
  gbif_key bigint,
  nazwa_naukowa text NOT NULL,
  nazwa_polska text,
  nazwy_polskie text[] NOT NULL DEFAULT '{}',
  rodzaj text, rodzina text, rzad text, klasa text,
  obserwacje_pl integer,                    -- GBIF, wystąpienia w Polsce
  obserwacje_woj integer,                   -- GBIF, wystąpienia w prostokącie obejmującym województwo
  wikidata text, wiki_tytul text, wiki_url text,
  opis_wstep text, opis_budowa text, opis_wystepowanie text, opis_podobne text, opis_ochrona text,
  cechy jsonb NOT NULL DEFAULT '{}',        -- {"hymenium": [...], "kapelusz": [...], ...} etykiety z Wikidata
  siedlisko jsonb NOT NULL DEFAULT '{}',    -- {"gleba": [...], "drzewa": [...]} z opisu występowania (Wikipedia)
  zdjecie_url text, zdjecie_miniatura text, zdjecie_strona text, zdjecie_autor text,
  zdjecie_licencja text, zdjecie_licencja_url text,
  pobrano_utc timestamptz NOT NULL DEFAULT now(),
  import_id bigint
);
CREATE INDEX IF NOT EXISTS katalog_nazwa_idx ON atlas.katalog (lower(coalesce(nazwa_polska, nazwa_naukowa)));
