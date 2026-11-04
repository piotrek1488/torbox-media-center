# Lokalne środowisko deweloperskie

Konfiguracja przygotowana dla trybu STRM. Wymagane: Git, Bash i [uv](https://docs.astral.sh/uv/getting-started/installation/). Skrypt wybiera Python 3.12. Obsługiwany przebieg to Linux/macOS; na Windows użyj WSL. Opcjonalny FUSE wymaga dodatkowych bibliotek systemowych i dostępu do urządzenia FUSE.

```bash
git clone https://github.com/piotrek1488/torbox-media-center.git
cd torbox-media-center
bash scripts/setup-dev.sh
.venv/bin/python scripts/smoke-dev.py
```

Skrypt tworzy `.venv` i, jeśli go brakuje, `.env` z przykładu. Zachowuje istniejący `.env`. Zależności pochodzą z `requirements.txt`, które obecnie nie przypina wersji. Domyślnie pomijane są opcjonalne pakiety FUSE, więc tryb STRM nie wymaga `pkg-config` ani nagłówków libfuse. Jeśli potrzebujesz FUSE, na Debianie/Ubuntu zainstaluj `sudo apt-get install pkg-config libfuse-dev build-essential`, a potem wykonaj `INSTALL_FUSE=1 bash scripts/setup-dev.sh`. FUSE wymaga także dostępu do `/dev/fuse`; ten wariant nie był sprawdzany w chmurze.

Wpisz klucz wyłącznie w lokalnym `.env` jako `TORBOX_API_KEY`. Następnie:

```bash
bash scripts/run-dev.sh
```

Domyślne ustawienia nowego `.env`: STRM, metadane wyłączone, katalog `./torbox`. Aplikacja czyści katalog wskazany przez `MOUNT_PATH` podczas startu — przeznacz go wyłącznie na wygenerowane pliki. Obecna aplikacja wypisuje klucz przy starcie; nie udostępniaj surowych logów. Pliki STRM również zawierają klucz w adresach URL. `.env` jest ignorowany przez Git; nie dodawaj go do repozytorium.

Test `smoke-dev.py` działa bez prawdziwego klucza i bez żądań sieciowych. Sprawdza przetwarzanie przykładowego medium, zapis TinyDB, treść STRM i usuwanie nieaktualnych plików, w katalogu tymczasowym. Nie potwierdza synchronizacji z API ani odtwarzania. Po lokalnym uruchomieniu sprawdź pobranie list TorBox i wygenerowane pliki.

W środowisku chmurowym używaj istniejącego checkoutu, bez tworzenia worktree. Jeśli katalog domowy jest tylko do odczytu, ustaw `UV_CACHE_DIR=/workspace/.cache/uv` przed instalacją. Proces aplikacji trzeba uruchomić ponownie w nowej sesji. Do pracy offline klucz nie jest potrzebny; synchronizacja wymaga dostępu HTTPS do `api.torbox.app`, a metadane do wybranych usług: `api.themoviedb.org`, `api4.thetvdb.com`, `kitsu.io` (oraz `kitsu.app` przy przekierowaniu).


## Metadane TMDB

W istniejącym `.env` dopisz (skrypt nie nadpisuje tego pliku):

```dotenv
ENABLE_METADATA=true
TMDB_API_KEY=twoj_lokalny_klucz_tmdb
METADATA_LANGUAGE=pl-PL
RAW_MODE=false
```

Dla TMDB użyj klucza **API Key (v3 auth)** z https://www.themoviedb.org/settings/api, nie tokenu „API Read Access Token”. Klucz TorBox pozostaje w `TORBOX_API_KEY`. Nie publikuj żadnego z kluczy.

Wybrany provider dostarcza tytuł, rok premiery i adresy grafik. Sezon/odcinek pochodzi z nazwy pliku, np. `Dark.S02E03.mkv`. Wyszukiwanie rozróżnia filmy i seriale; dla filmu uwzględnia rok z nazwy, a dla serialu używa roku premiery całej serii. Brak dopasowania, timeout lub błąd API zachowuje metadane z nazwy pliku. Wyniki są przechowywane w ograniczonym cache w pamięci procesu. Dopasowanie po nazwie nie gwarantuje poprawności dla niejednoznacznych tytułów.

Docker Compose odczytuje te same zmienne z `.env`. Uruchom `docker compose up -d --build`, aby zbudować lokalny kod z integracją TMDB. Dotychczasowy publiczny obraz upstream nie zawiera tej zmiany. Pliki STRM pojawią się w `./torbox`. Podgląd logów: `docker compose logs -f` (obecna aplikacja wypisuje klucz TorBox; nie udostępniaj logów).

Testy bez prawdziwych kluczy: `.venv/bin/python -m unittest discover -s tests -v`. Nie potwierdzają autoryzacji prawdziwego konta TMDB.

This product uses the TMDB API but is not endorsed or certified by TMDB.


## Dodatkowi providerzy i anime

Aktualizacja nie dopisuje zmiennych do istniejącego `.env`. Możesz dodać:

```dotenv
METADATA_PROVIDERS=tmdb,tvdb,kitsu
TVDB_API_KEY=
TVDB_PIN=
```

Lista określa kolejność prób. Pierwsze dopasowanie wygrywa; dane różnych serii nie są łączone. Brak klucza pomija TMDB/TVDB, błąd lub brak dopasowania uruchamia następnego providera. Gdy wszystkie próby zawiodą, plik pozostaje dostępny pod oryginalną nazwą. Dla biblioteki anime można ustawić `METADATA_PROVIDERS=kitsu,tmdb,tvdb`; Kitsu nie potrzebuje klucza. Nazwy kanoniczne i aliasy Kitsu pomagają dopasować tytuły japońskie/romaji, ale nie gwarantują trafienia dla każdego wydania ani polskiego tytułu.

TVDB korzysta z API v4 i osobnego `TVDB_API_KEY` (https://thetvdb.com/api-information). `TVDB_PIN` podaj wyłącznie, jeśli wymaga go typ Twojego klucza. Uprawnienia i ewentualna subskrypcja zależą od TVDB. Klucz i PIN są przekazywane przy logowaniu; token jest przechowywany tylko w pamięci. Compose przekazuje te zmienne z `.env`; po aktualizacji wykonaj `docker compose up -d --build`.

Poprawiono błąd PTN zwracający pustą listę odcinków. Dla `[Grupa Mirai] Dragon Ball - 118 [v2] [DVD 720x540 AC3] [4F4E90E0].mkv` rozpoznawany jest tytuł `Dragon Ball` i odcinek absolutny `118`. Nazwa wynikowa zachowuje `E118`; katalog `Season 1` jest organizacyjnym domyślnym katalogiem przy braku sezonu. Nie oznacza to potwierdzenia, że jest to `S01E118` w numeracji TMDB/TVDB. Automatyczne mapowanie numeracji absolutnej na sezony nie jest zaimplementowane. Puste listy sezonów i odcinków nie powodują już `IndexError`.

Integracje TVDB i Kitsu sprawdzono na kontrolowanych odpowiedziach HTTP zgodnych ze schematami API; dostęp do prawdziwego konta TVDB oraz bieżące odpowiedzi Kitsu należy zweryfikować lokalnie. Źródła: https://thetvdb.github.io/v4-api/ oraz https://kitsu.docs.apiary.io/.


Numerowane filmy anime z lokalnym podtytułem, np. `Dragon Ball Z Movie 13 - Eksplozja Smoczej Pięści!! Jeśli nie Goku, to kto`, mają dodatkową próbę wyszukania po `Dragon Ball Z Movie 13`. Dopasowanie może użyć numerowanego aliasu providera (np. w Kitsu). Wymagana jest zgodność nazwy cyklu i numeru filmu; numer 13 nie oznacza trzynastego wyniku wyszukiwania. Oznaczenie `Movie 13` klasyfikuje plik jako film, nawet w folderze z oznaczeniem sezonu. Jeżeli provider nie udostępnia odpowiedniego numerowanego tytułu/aliasu, plik nadal może pozostać bez dopasowania. Nie zastosowano stałego mapowania numerów Dragon Ball na identyfikatory API.
