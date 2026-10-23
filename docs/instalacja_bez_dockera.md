# Instalacja, gdy na komputerze nie można zainstalować Dockera

Typowa sytuacja: firmowy Windows bez uprawnień administratora. Aplikacji nie uruchamiamy wtedy na tym komputerze,
tylko na serwerze, a iPhone łączy się z nim przez **Tailscale** (prywatna sieć, stały adres HTTPS).
Na firmowym komputerze nie trzeba niczego instalować — wystarczy przeglądarka.

## Droga 1 — GitHub Codespaces (za darmo, do testów)

Serwer w chmurze GitHuba z Dockerem, obsługiwany z przeglądarki.

1. Zaloguj się na GitHubie i otwórz https://github.com/paweljnk/grzyby-podkarpacia
2. **Code → zakładka Codespaces → Create codespace on main**. Poczekaj kilka minut — aplikacja zbuduje się i uruchomi
   sama (`.devcontainer/devcontainer.json`).
3. Na dole okna zakładka **Ports** → wiersz `8000 Grzyby Podkarpacia` → kolumna *Forwarded Address* — to adres HTTPS
   (`https://<nazwa>-8000.app.github.dev`).
4. Dostęp z iPhone'a — wybierz jedno:
   - **prywatnie (domyślnie):** otwórz adres w Safari na iPhonie i zaloguj się na to samo konto GitHub;
   - **publicznie:** prawy klik na porcie → *Port Visibility* → *Public*. Każdy, kto zna adres, zobaczy aplikację
     (tylko odczyt).
   - **Jeśli iPhone proponuje „pobranie” pliku 0 KB** — port jest prywatny (GitHub odpowiada pustą odmową 401).
     Ustaw port na **Public** (wyżej) i otwórz adres ponownie. Przy pierwszym wejściu GitHub może pokazać stronę
     ostrzegawczą o porcie codespace'a — stuknij „Continue”.
5. Safari → **Udostępnij → „Do ekranu początkowego”**. Po pierwszym starcie aplikacja sama pobiera dane rzeczywiste
   (ok. 60 MB, 1–2 min) — do tego czasu widać komunikat o braku danych.

Ograniczenia Codespaces:
- serwer usypia po okresie bezczynności (domyślnie 30 min; w ustawieniach GitHuba → Codespaces można wydłużyć do 4 h)
  — wtedy aplikacja w telefonie nie działa, dopóki nie uruchomisz codespace'a ponownie;
- darmowy limit godzin w miesiącu dla kont prywatnych (szczegóły w ustawieniach rozliczeń GitHuba);
- to rozwiązanie do testów, nie do codziennego używania w lesie.

Tailscale nie jest tu potrzebny.

## Droga 2 — mały serwer (VPS) + Tailscale (na stałe)

Działa cały czas, adres się nie zmienia, aplikacja jest widoczna tylko dla Twoich urządzeń.

**Serwer:** dowolny VPS z Ubuntu 24.04, min. 2 GB RAM (np. tani VPS w polskiej lub europejskiej serwerowni; darmowe
maszyny oferuje też Oracle Cloud „Always Free”). Może to być też prywatny komputer lub Raspberry Pi 4/5 w domu.

Na serwerze (przez SSH — z firmowego Windowsa działa wbudowane polecenie `ssh` w PowerShell albo konsola w panelu
dostawcy VPS):

```bash
# 1. Docker
curl -fsSL https://get.docker.com | sudo sh
# 2. kod i uruchomienie
git clone https://github.com/paweljnk/grzyby-podkarpacia
cd grzyby-podkarpacia
sudo docker compose -f docker-compose.home.yml up -d --build
# 3. Tailscale na serwerze
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up            # wyświetli link do zalogowania — otwórz go i zaloguj się
# 4. HTTPS w sieci Tailscale (wcześniej w panelu Tailscale: DNS → włącz MagicDNS i HTTPS Certificates)
sudo tailscale serve --bg 8000
sudo tailscale serve status  # pokaże adres https://<nazwa-serwera>.<twoja-sieć>.ts.net
```

**iPhone:**
1. Zainstaluj aplikację **Tailscale** z App Store i zaloguj się na **to samo konto**. Włącz połączenie (VPN).
2. Otwórz w Safari adres `https://<nazwa-serwera>.<twoja-sieć>.ts.net`.
3. **Udostępnij → „Do ekranu początkowego”**. Dane rzeczywiste aplikacja pobiera sama (co 6 h sprawdza nowe paczki).

Aplikacja działa w telefonie, gdy Tailscale jest włączony. Nikt spoza Twojej sieci Tailscale jej nie zobaczy.
(Jeśli chcesz udostępnić ją komuś bez Tailscale: `sudo tailscale funnel --bg 8000` — wtedy adres jest publiczny.)

Aktualizacja po zmianach w kodzie:

```bash
cd grzyby-podkarpacia && git pull && sudo docker compose -f docker-compose.home.yml up -d --build
```

Zdjęcia do atlasu pobiera się na serwerze tak samo, jak w `docs/instalacja_iphone.md` (z prefiksem `sudo`).

## Uwagi
- Tych dróg nie dało się przetestować w środowisku, w którym powstała aplikacja (brak dostępu do GitHub Codespaces
  i Tailscale). Jeśli któryś krok zwróci błąd — zapisz jego treść.
- Firmowa sieć może blokować Tailscale lub Codespaces — wtedy użyj prywatnego telefonu jako punktu dostępu albo sieci domowej.
