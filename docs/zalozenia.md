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
