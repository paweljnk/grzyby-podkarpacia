# Dane siedliskowe i glebowe — weryfikacja źródeł (2026-10-17)

Sprawdzone bezpośrednio, zadaniami w GitHub Actions (skrypty `scripts/recon*.py`, surowe odpowiedzi na gałęzi
`dane/recon`), oraz wyszukiwarką. Wnioski opierają się na rzeczywistych odpowiedziach usług.

## Sprawdzone usługi i eksporty BDL

| Kanał | Adres | Dostęp | Licencja / warunki |
|---|---|---|---|
| OGC API Features | https://ogcapi.bdl.lasy.gov.pl | publiczny, bez klucza | CC BY 4.0 (OpenAPI `info.license`) |
| WFS (GeoServer) | https://wfs.bdl.lasy.gov.pl/geoserver/BDL/ows | publiczny | CC BY 4.0 (dane.gov.pl, zbiór 629) |
| WMS / **ArcGIS REST** (Map, Query, Data; stronicowanie, maks. 2000/str.) | https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services/… | publiczny | CC BY 4.0 (dane.gov.pl, zbiór 629) |
| Paczka ZIP opisu taksacyjnego (SHP + tabele) | formularz https://www.bdl.lasy.gov.pl/portal/wniosek | **wymaga adresu e-mail**, zgody RODO i akceptacji warunków; link przychodzi mailem | warunki BDL: podać źródło i daty; dalej udostępniać w formie pierwotnej; **powiadomić operatora (bdl@bdl.lasy.gov.pl) o przetworzeniu** |

Zawartość paczki ZIP (instrukcja „nowego sposobu pobierania danych z BDL”, gov.pl): `G_SUBAREA` (wydzielenia),
`G_COMPARTMENT`, `f_arodes.txt`, `f_subarea.txt`, `f_arod_storey.txt`, **`f_storey_species.txt`**, `f_part_dic.txt`,
`f_site_type_dic.txt`, `f_tree_species_dic.txt`, `warunki_wykorzystania.txt` i inne słowniki. **W spisie nie ma
słownika gleb ani uwilgotnienia.**

## Wyniki dla poszczególnych atrybutów

| Atrybut | OGC API / WFS | ArcGIS REST / WMS | Paczka ZIP | Stan w aplikacji |
|---|---|---|---|---|
| **Gatunek dominujący** | `species_cd` | `species_cd_d` (wydzielenia LP i poza LP) | tak | ✅ źródło: BDL |
| **Skład gatunkowy z udziałami** | — | warstwa „Drzewostany PGL LP” ma **1 wiersz na wydzielenie** (sprawdzone: 460 wydzieleń, 460 wierszy) — to gatunek panujący piętra, nie pełny skład | `f_storey_species.txt` | ⚠️ tylko **udział gatunku panującego** (`part_cd`); pełny skład — wyłącznie przez zamówienie paczki |
| Udział gatunku panującego | `part_cd` (1–10, kody opisowe np. `PJD`, `MJS`) | `part_cd` | `f_part_dic.txt` | ✅ `part_cd/10`; kody opisowe → brak liczby |
| **Typ siedliskowy lasu** | `site_type` | `site_type_cd`; warstwa „Siedliska leśne” | `f_site_type_dic.txt` | ✅ źródło: BDL |
| **Typ i podtyp gleby** | — | warstwa **„Siedliska leśne”**: `soil_subtype_cd` (np. BRk, BRwy, RDb, Bw), `soil_species` (gatunek gleby / utwór), `geol_depos`, `degradation_cd` | brak słownika w spisie paczki | ✅ źródło: BDL Siedliska (SILP/PUL/OpracGS, `valid_year` 2025); przypisanie do wydzielenia wg największego pokrycia (≥50%) |
| **Uwilgotnienie** | — (pośrednio w kodzie TSL: św/w/b) | `moisture_cd` (wartości 0, 1, 2, 3, „-”) | — | ⚠️ kod zapisany **bez interpretacji** — słownik kodów nie jest opublikowany |
| **pH** | — | — | — | ⚠️ **brak w BDL**. Źródło zastępcze: **SoilGrids 2.0** (model, 250 m, pH(H₂O) 0–5 cm, przedział Q0.05–Q0.95). pH nie jest wyprowadzane z typu gleby |
| Lasy poza LP | — | „Wydzielenia poza PGL LP wg PUL” (254 tys. w prostokącie województwa): typ siedliskowy, gatunek panujący, udział, wiek, **kategoria własności** | — | ✅ źródło: BDL (plany urządzenia lasu, rok planu 1994–2026) |
| Zakazy wstępu do lasu | — | warstwa „Okresowy zakaz wstępu do lasu” (789 w kraju, z datami od–do) | — | ✅ codziennie, przecięcie z województwem |

## Inne sprawdzone źródła

| Źródło | Wynik |
|---|---|
| dane.gov.pl (wyszukiwanie „siedliska leśne”, „bank danych o lasach”) | tylko usługi BDL i monitoring siedlisk przyrodniczych (Natura 2000) — brak map gleb leśnych |
| Geoportal / GUGiK | mapy glebowo-rolnicze obejmują grunty rolne, nie lasy — nieprzydatne |
| GDOŚ (formy ochrony przyrody) | HTTP 403 także z GitHub Actions; parki narodowe rozpoznawane z kategorii własności BDL „SP w zarządzie Parków Narodowych” |
| SoilGrids 2.0 | REST wstrzymany; **WCS działa** (`maps.isric.org`, pokrycia `phh2o_0-5cm_mean/Q0.05/Q0.95`) |
| ESA WorldCover 2021 v200 | warstwa referencyjna lasów (10 m, CC BY 4.0) do oceny pokrycia; „Tree cover” obejmuje też zadrzewienia |

## Jak to wpływa na ocenę (stan 2026-10-23)

Cechy siedliska liczone są **osobno**, każda z własnym źródłem i oznaczeniem (źródłowa / model / brak):

| Cecha | Źródło | Porównanie z wymaganiem gatunku (species/*.yaml) |
|---|---|---|
| Typ siedliskowy lasu | BDL, opis taksacyjny | `typy_siedliskowe` (preferowany / dopuszczalny / inny) |
| Typ i podtyp gleby + gatunek gleby (utwór) | BDL, warstwa „Siedliska leśne” | `gleba.zyznosc` — żyzność z podtypu, a gdy podtyp jej nie daje — z uziarnienia (config/gleby_bdl.yaml, założenie C) |
| Uwilgotnienie | BDL — człon kodu typu siedliskowego (św / w / b / s; Ol, OlJ) | `gleba.uwilgotnienie` |
| pH | **wyłącznie** SoilGrids 2.0 (model 250 m, Q0.05–Q0.95) — BDL nie podaje pH | `gleba.odczyn`; gdy przedział obejmuje odczyn zgodny i niezgodny → przedział warunków |
| Nasłonecznienie stoku | obliczenie z DEM (nachylenie, ekspozycja) i położenia Słońca dla wybranego dnia (Duffie & Beckman, r. 1.6.1) | zmienia parowanie w bilansie wody (B): stok południowy szybciej przesycha (config/model.yaml → `pogoda.naslonecznienie`) |

**pH nie jest wyprowadzane z typu gleby.** Wcześniejsza wersja przypisywała podtypom gleby „klasę odczynu” — usunięte.

Stan danych w województwie (import 2026-10-17):
- podtyp i gatunek gleby z BDL: 81,2% wydzieleń LP, 0,1% lasów poza LP (warstwa siedlisk obejmuje lasy LP);
- pH z SoilGrids: 99,8% / 99,5% wydzieleń, ale średnia szerokość przedziału Q0.05–Q0.95 to 3,3 jednostki pH — przedział
  prawie zawsze obejmuje kilka klas odczynu, więc pH zwykle **poszerza przedział warunków i podnosi pewność tylko o połowę wagi**;
- uwilgotnienie: z kodu typu siedliskowego dla wszystkich wydzieleń z typem w nomenklaturze (św/w/b/s).

Szukano innych źródeł pH gleb leśnych: baza „Gleby leśne” IBL (pomiary pH w H₂O i KCl, punktowe, bez otwartego pobierania),
mapy pH ESDAC/LUCAS (500 m, rejestracja, warunki „do badań”, bez jawnej licencji otwartej), monitoring chemizmu GIOŚ
(tylko gleby orne). Żadne nie daje otwartego pH dla wydzieleń.

Zasady ogólne bez zmian:
- **Warunki** liczone są tylko z dostępnych cech; brak cechy **obniża pewność, nie warunki**.
- Nieznana część składu drzewostanu i niepewne pH dają **przedział warunków**; udziałów nie zgadujemy.
- **Pewność danych** (0–1): źródło BDL = 1, model (SoilGrids, DEM) = 0,5–0,8, brak = 0; obniżana o szerokość przedziału.
- Bramka „siedlisko poniżej progu” działa na **górnej** granicy przedziału.

## Co można jeszcze zrobić (wymaga decyzji użytkownika)

1. **Pełny skład gatunkowy**: zamówić paczki dla nadleśnictw Podkarpacia przez formularz BDL (adres e-mail właściciela
   projektu, akceptacja warunków), pobrać link z poczty i wczytać `f_storey_species.txt`. Importer jest przygotowany na
   pole `udzial_gatunkow` (model użyje pełnego składu bez przedziału).
2. **Powiadomić operatora BDL** (bdl@bdl.lasy.gov.pl) o przetwarzaniu danych w aplikacji — wymóg warunków BDL.
3. Słownik `moisture_cd` — zapytać operatora BDL.
