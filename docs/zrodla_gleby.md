# Źródła danych o glebie i pH — weryfikacja (2026-10-23)

Sprawdzone przez GitHub Actions (`scripts/recon6.py`, `scripts/recon7.py`, gałąź `dane/recon`) i wyszukiwarką.

| Źródło | Co zawiera | Lasy? | pH? | Dostęp / licencja | Wniosek |
|---|---|---|---|---|---|
| **IBL — baza „Gleby leśne”, podbaza „Siedliska lasowe”** (ibles.pl) | ok. 59 188 rekordów; adres leśny (RDLP, nadleśnictwo, leśnictwo, oddział, adres), warstwa 0–5 / 5–15 cm, poziom OFH/AB/AE, **pH KCl i pH H₂O**, C, N, C/N, P₂O₅, kationy, kwasowość hydrolityczna | tak (siedliska lasowe; osobno „siedliska górskie”) | **tak, pomiar** | „dane laboratoryjne, **baza zamknięta**”; kontakt: dr Grażyna Olszowska, Zakład Ekologii Lasu IBL | najlepsze źródło pH dla lasów; adres leśny pozwala połączyć z wydzieleniami BDL — **wymaga prośby o udostępnienie** |
| **ESDAC — LUCAS 2018 Topsoil** | 18 984 próbek w UE: pH (H₂O, CaCl₂), C org., CaCO₃, N, P, K, przewodność; CSV + punkty SHP | częściowo (punkty losowe, głównie grunty rolne) | tak, pomiar punktowy | formularz rejestracji (adres e-mail); własność UE, nieodpłatnie, obowiązek cytowania; JRC: „nie są reprezentatywne dla warunków lokalnych” | na Podkarpaciu pojedyncze punkty — przydatne tylko do **sprawdzenia SoilGrids** w regionie, nie do oceny wydzieleń |
| **OSChR Rzeszów** (Okręgowa Stacja Chemiczno-Rolnicza) | laboratorium: oznacza pH, makro- i mikroelementy, skład granulometryczny; baza zasobności gleb w N i P (rolnictwo) | na zlecenie (próbki dostarczone przez zleceniodawcę) | tak, **pomiar na zlecenie (płatny, cennik Dz.U. 1866/2025)** | usługa, nie zbiór danych | możliwość zmierzenia pH w wybranych miejscach przez użytkownika |
| **GUGiK — mapa glebowo-rolnicza 1:5000** (podkarpackie, uzupełniona 2026-02-04) | warstwa `KONTURY_GLEBOWE`: kompleks przydatności, typ/podtyp gleby, gatunek gleby w 5 warstwach, szkieletowość, rodzaj gleby organicznej; stan kartowania 1966–1980 | **lasy LP: tylko „Ls” bez opisu gleby (8/8 sprawdzonych wydzieleń)**; **lasy poza LP: typ i gatunek gleby w 6/8** | **nie** | WMS/WMTS publiczne (przeglądanie); dane GML z PZGiK na wniosek (odpłatnie albo nieodpłatnie m.in. dla celów edukacyjnych i badań) | uzupełnia **typ i gatunek gleby dla lasów poza LP** (tam BDL ma 0,1% pokrycia); masowe odpytywanie WMS dla 145 tys. wydzieleń byłoby nadużyciem usługi — właściwa droga to GML z PZGiK |

Stan w aplikacji bez zmian: pH tylko z SoilGrids (model, przedział), typ i gatunek gleby z BDL (81% wydzieleń LP).

Decyzje do podjęcia (wymagają działania właściciela projektu):
1. Wniosek do IBL o udostępnienie podbazy „Siedliska lasowe” (pH dla wydzieleń wg adresu leśnego).
2. Wniosek do PZGiK (GUGiK / WODGiK Rzeszów) o GML mapy glebowo-rolniczej dla woj. podkarpackiego — typ i gatunek gleby dla lasów poza LP.
3. Rejestracja w ESDAC (LUCAS 2018) — sprawdzenie, jak SoilGrids odpowiada pomiarom w regionie.
4. Własne pomiary pH (np. OSChR Rzeszów) — aplikacja może przyjmować je jako „pomiar użytkownika” dla wybranego miejsca.
