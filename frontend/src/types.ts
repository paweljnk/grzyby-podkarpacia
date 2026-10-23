export type Dataset = "real" | "demo";

export interface Factor { nazwa: string; wartosc: number | null; waga: number; opis: string }
export interface Component { wynik: number | null; kompletnosc: number; zakres: [number, number] | null; czynniki: Factor[]; uzasadnienie: string[] }
export interface Gate { kod: string; opis: string }
export interface Source { id: string; nazwa: string; licencja: string | null; atrybucja: string | null; ostatni_import: string | null; status: string | null }

export interface Envelope {
  zbior_danych: Dataset;
  parametry: Record<string, unknown>;
  ostrzezenia: string[];
  zastrzezenie: string;
  zrodla: Source[];
  dane: { wydzielen: number; pogoda_od: string | null; pogoda_do: string | null; pogoda_pobrano_utc: string | null; metadane: Record<string, string> };
}

export interface Scored {
  id: number; nazwa: string; lat: number; lon: number; odleglosc_km: number | null; odleglosc_opis: string;
  powierzchnia_ha: number; gatunek_panujacy: string | null; typ_siedliskowy: string | null; wiek: number | null;
  wynik: number | null; podstawa: number | null; A: Component; B: Component; C: number; D: number;
  bramki: Gate[]; rekomendowane: boolean; kompletnosc: number; jakosc: "wysoka" | "srednia" | "niska"; uzasadnienie: string[];
  warunki: number | null; warunki_min: number | null; warunki_max: number | null; pewnosc: number; pewnosc_opis: "wysoka" | "srednia" | "niska";
  zarzad?: string | null; wlasnosc?: string | null; klasa_danych?: string | null; rok_danych?: number | null;
}

export interface Attribute { atrybut: string; wartosc: string | number | null; zrodlo: string | null; data: string | number | null; oznaczenie: "źródłowa" | "model" | "brak" }

export interface RankingResp extends Envelope {
  miejsca: (Scored & { pogoda: { opad_7d_mm: number | null } })[]; liczba_ocenionych: number; wykluczone: number;
  /** wszystkie ocenione wydzielenia: [lon, lat, wskaźnik, rekomendowane 0/1, pewność, id] */
  punkty?: [number, number, number | null, number, number, number][];
}

export interface CalendarInfo {
  data: string; faza: string; faza_opis: string; oswietlenie: number; typ_biodynamiczny: string;
  wschod_utc: string | null; zachod_utc: string | null; uwaga: string; gwiazdozbior_poludnie: string;
}

export interface PlaceCard extends Scored {
  geometria: GeoJSON.Geometry | null;
  drzewostan: { gatunek_panujacy: string | null; udzial_gatunkow: Record<string, number> | null; wiek: number | null; typ_siedliskowy: string | null; gleba: string | null; pochodzenie: Record<string, string>; import_utc: string | null };
  teren: { wys_sr_m: number | null; wys_min_m: number | null; wys_max_m: number | null; nachylenie_sr_deg: number | null; nachylenie_max_deg: number | null; ekspozycja: string | null; uwaga: string };
  pogoda: { opad_mm: Record<string, number | null>; temp_sr_7_c: number | null; bilans_14_mm: number | null; dni_od_ostatniego_opadu: number | null; przymrozki_7: number | null; wilg_gleby_dzien: number | null; sklad_typow: Record<string, number>; pobrano_utc?: string | null; rozdzielczosc_km?: number | null; uwaga: string };
  dostep: { zakaz_zbioru: boolean; zakaz_wstepu: boolean; zakazy_wstepu_sprawdzalne: boolean; uwagi: string[]; las_prywatny_uwaga: string; formy_ochrony: { rodzaj: string; nazwa: string }[] };
  dojazd: { odleglosc_km: number | null; opis: string; nachylenie_sr_deg: number | null };
  kalendarz: CalendarInfo;
  atrybuty: Attribute[];
}

export interface WeekDay { data: string; wynik: number | null; rekomendowane: boolean; jakosc: string; A: number | null; B: number | null; C: number; D: number; bramki: string[]; powody: string[]; typy_danych: Record<string, number>; faza: string; typ_biodynamiczny: string }
export interface WeekResp extends Envelope { dni: WeekDay[]; werdykt: { decyzja: string; dzien?: string; opis: string; uwaga: string } }

export interface MonthDay { data: string; faza: string; faza_opis: string; oswietlenie: number; typ_biodynamiczny: string; wynik: number | null; wynik_z_kalendarzem?: number | null; opad_mm: number | null; temp_sr_c: number | null; typ_danych: string | null }
export interface MonthResp extends Envelope { dni: MonthDay[]; uwaga: string }

export interface SpeciesItem { id: string; nazwa_polska: string; nazwa_naukowa: string; nazwy_zwyczajowe: string[]; weryfikacja: string }
