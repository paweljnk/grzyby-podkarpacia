# Instalacja na iPhonie: komputer w domu i tunel HTTPS

Aplikacja działa na Twoim komputerze. Tunel daje jej adres **HTTPS**, który otworzysz w Safari na iPhonie.
HTTPS jest konieczny: bez niego iPhone nie da dostępu do lokalizacji (GPS) i nie zadziała tryb offline.

> Aplikacja pokazuje na razie **dane demonstracyjne** (fikcyjne lasy i pogoda). Nie planuj na ich podstawie wypraw.

## 1. Zainstaluj Dockera (jednorazowo)

| System | Co zainstalować |
|---|---|
| macOS | [Docker Desktop dla Maca](https://docs.docker.com/desktop/setup/install/mac-install/) (Apple Silicon albo Intel) |
| Windows 10/11 | [Docker Desktop dla Windows](https://docs.docker.com/desktop/setup/install/windows-install/) (z WSL 2 — instalator to zaproponuje) |
| Linux | Docker Engine + wtyczka Compose ([instrukcja](https://docs.docker.com/engine/install/)) |

Po instalacji uruchom Docker Desktop i poczekaj, aż pokaże „Engine running”.

## 2. Pobierz kod (jednorazowo)

Z [GitHuba](https://github.com/paweljnk/grzyby-podkarpacia): przycisk **Code → Download ZIP** i rozpakuj,
albo w terminalu:

```bash
git clone https://github.com/paweljnk/grzyby-podkarpacia
cd grzyby-podkarpacia
```

Terminal: na Macu aplikacja **Terminal**, na Windowsie **PowerShell**. Wszystkie polecenia uruchamiaj w katalogu
`grzyby-podkarpacia`.

## 3. Uruchom aplikację

```bash
docker compose -f docker-compose.home.yml up -d --build
```

Pierwsze uruchomienie trwa kilka minut (pobiera i buduje obrazy). Sprawdź na komputerze: http://localhost:8000.

Opcjonalnie dociągnij rzeźbę terenu (ok. 100 MB, kilka minut) i odśwież dane demo:

```bash
docker compose -f docker-compose.home.yml exec app python -m grzyby.cli import dem
docker compose -f docker-compose.home.yml exec app python -m grzyby.cli demo
```

## 4. Włącz tunel HTTPS

```bash
docker compose -f docker-compose.home.yml --profile tunel up -d
docker compose -f docker-compose.home.yml logs tunel
```

W logach znajdź adres w ramce, np. `https://przykladowe-slowa-1234.trycloudflare.com`.

**Uwaga:**
- Ten adres (Cloudflare „quick tunnel”, bez konta) **zmienia się po każdym restarcie tunelu lub komputera**. Ikona na
  iPhonie przestanie wtedy działać i trzeba ją dodać ponownie.
- Adres jest publiczny: każdy, kto go zna, zobaczy aplikację. Nie podawaj go dalej. Baza danych nie jest wystawiona.

## 5. Dodaj do ekranu początkowego iPhone'a

1. Otwórz adres z kroku 4 w **Safari** (nie w Chrome — na iOS tylko Safari dodaje pełną aplikację).
2. Stuknij **Udostępnij** (kwadrat ze strzałką w górę).
3. Przewiń i wybierz **„Do ekranu początkowego”** → **Dodaj**.
4. Uruchamiaj aplikację ikoną „Grzyby”. Przy pierwszym użyciu „📍 Użyj mojej lokalizacji” zezwól na lokalizację.
5. Jeśli aplikacja pokazuje komunikat o braku danych rzeczywistych, wybierz w nagłówku **„dane demo”**.

## Stały adres (zamiast zmieniającego się)

Jeśli chcesz, żeby ikona działała po restarcie komputera, użyj **Tailscale Funnel** (darmowe konto):

1. Zainstaluj [Tailscale](https://tailscale.com/download) na komputerze i zaloguj się.
2. W panelu Tailscale włącz HTTPS i Funnel dla swojej sieci (panel poprowadzi przy pierwszym uruchomieniu).
3. W terminalu: `tailscale funnel 8000` → dostaniesz stały adres `https://<nazwa-komputera>.<twoja-sieć>.ts.net`.
4. Tunel Cloudflare (krok 4) jest wtedy niepotrzebny.

Druga możliwość: nazwany tunel Cloudflare z własną domeną (wymaga konta Cloudflare i domeny).

## Codzienne użycie

| Co | Polecenie |
|---|---|
| Wyłączyć wszystko | `docker compose -f docker-compose.home.yml --profile tunel down` |
| Włączyć ponownie | `docker compose -f docker-compose.home.yml --profile tunel up -d` (nowy adres tunelu → dodaj ikonę ponownie) |
| Zaktualizować po zmianach w kodzie | `git pull`, potem `docker compose -f docker-compose.home.yml up -d --build` |
| Usunąć dane bazy | `docker compose -f docker-compose.home.yml down -v` |

Komputer musi być włączony i nie może usypiać, gdy korzystasz z aplikacji w telefonie.

## Ograniczenia wersji PWA na iPhonie

- Nie nagrywa śladu GPS przy wygaszonym ekranie (to będzie wymagało aplikacji Capacitor — Etap 5).
- W lesie bez zasięgu działają tylko ostatnio oglądane ekrany (pełny tryb offline obszaru — Etap 5).
- Atlasu grzybów jeszcze nie ma (Etap 4b).
