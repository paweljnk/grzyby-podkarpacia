# Założenia projektowe (Etap 1)

Wszystkie poniższe wartości są **założeniami projektowymi**, a nie ustalonymi zależnościami
biologicznymi ani standardem. Leżą w plikach konfiguracyjnych i można je zmieniać bez zmiany kodu.

| Parametr | Wartość | Plik | Uzasadnienie |
|---|---|---|---|
| Rozdzielczość analiz rzeźby | 25 m | `config/pilot.yaml` | kompromis między rozmiarem danych a skalą wydzielenia (zwykle 0,5–10 ha) |
| Resampling DEM | bilinear | `config/pilot.yaml` | dane ciągłe; najbliższy sąsiad dawałby schodkowe nachylenie |
| Próg terenu płaskiego | 2° | `config/pilot.yaml` | poniżej tego średniego nachylenia ekspozycja nie ma sensu i ma klasę `plasko` |
| Prostokąty robocze obszarów | zob. plik | `config/pilot.yaml` | tylko do kadrowania; zastąpić granicą nadleśnictwa z BDL |

Metody:
- nachylenie i ekspozycja: metoda Horna (1981), okno 3×3; brzeg i sąsiedztwo NoData = brak wartości;
- ekspozycja wydzielenia: średnia kołowa azymutów pikseli o nachyleniu ≥ progu; brak, gdy kierunki się znoszą;
- wydzielenie mniejsze niż piksel: brane są piksele, których dotyka (`all_touched`).

## Model rekomendacji (Etap 3c)

Parametry: `config/model.yaml`, reguły gatunkowe: `species/*.yaml`, kalendarz: `config/kalendarz.yaml`.

- **A (siedlisko)** = [średnia ważona: typ siedliskowy, wiek, gleba, teren] × **drzewa partnerskie** (mnożnik).
  Drzewa są czynnikiem ograniczającym dla gatunków mikoryzowych: pierwsza wersja (średnia ważona wszystkich
  czynników) dawała ols bez drzew partnerskich A ≈ 29 i wskaźnik ≈ 59 przy idealnej pogodzie — test to wykrył.
- **B (pogoda)** = sezon (mnożnik, z poprawką wysokościową) × **dostępność wody** (mnożnik: opad z okna gatunku,
  kary za ujemny bilans opad − ET₀ i długi brak opadu) × [średnia ważona: opóźnienie po opadzie, temperatura,
  wilgotność gleby z modelu] − kara za przymrozki. Pierwsza wersja bez mnożnika wody dawała przy suszy ≈ 60.
- **podstawa** = A^0,5 · B^0,5 (ważona średnia geometryczna); **wynik** = clamp(podstawa + C + D, 0, 100).
- **C (obserwacje)**: ±15 pkt; waga = jakość × 0,5^(dni/7) × e^(−km/2); „nic nie znalazłem” z wagą 0,6 × (czas szukania / 120 min).
- **D (kalendarz)**: jeden modyfikator z fazy Księżyca i typu dnia biodynamicznego, domyślnie ±3, maks. ±5, eksperymentalny.
- **Bramki**: A < 30, silna susza (bilans 14 d poniżej progu gatunku albo ≥ 21 dni bez opadu w 30 dniach), park narodowy.
- **Kompletność**: udział wag czynników A i B, dla których są dane; obniżana o dni prognozy w oknie. Progi: wysoka ≥ 0,8, średnia ≥ 0,55.
