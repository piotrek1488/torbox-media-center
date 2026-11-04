# Lokalne środowisko deweloperskie

Konfiguracja przygotowana dla trybu STRM. Wymagane: Git, Bash i [uv](https://docs.astral.sh/uv/getting-started/installation/). Skrypt wybiera Python 3.12. Obsługiwany przebieg to Linux/macOS; na Windows użyj WSL. Opcjonalny FUSE wymaga dodatkowych bibliotek systemowych i dostępu do urządzenia FUSE.

```bash
git clone https://github.com/piotrek1488/torbox-media-center.git
cd torbox-media-center
bash scripts/setup-dev.sh
.venv/bin/python scripts/smoke-dev.py
```

Skrypt tworzy `.venv` i, jeśli go brakuje, `.env` z przykładu. Zachowuje istniejący `.env`. Zależności pochodzą z `requirements.txt`, które obecnie nie przypina wersji.

Wpisz klucz wyłącznie w lokalnym `.env` jako `TORBOX_API_KEY`. Następnie:

```bash
bash scripts/run-dev.sh
```

Domyślne ustawienia nowego `.env`: STRM, metadane wyłączone, katalog `./torbox`. Aplikacja czyści katalog wskazany przez `MOUNT_PATH` podczas startu — przeznacz go wyłącznie na wygenerowane pliki. Obecna aplikacja wypisuje klucz przy starcie; nie udostępniaj surowych logów. Pliki STRM również zawierają klucz w adresach URL. `.env` jest ignorowany przez Git; nie dodawaj go do repozytorium.

Test `smoke-dev.py` działa bez prawdziwego klucza i bez żądań sieciowych. Sprawdza przetwarzanie przykładowego medium, zapis TinyDB, treść STRM i usuwanie nieaktualnych plików, w katalogu tymczasowym. Nie potwierdza synchronizacji z API ani odtwarzania. Po lokalnym uruchomieniu sprawdź pobranie list TorBox i wygenerowane pliki.

W środowisku chmurowym używaj istniejącego checkoutu, bez tworzenia worktree. Jeśli katalog domowy jest tylko do odczytu, ustaw `UV_CACHE_DIR=/workspace/.cache/uv` przed instalacją. Proces aplikacji trzeba uruchomić ponownie w nowej sesji. Do pracy offline klucz nie jest potrzebny; synchronizacja wymaga dostępu HTTPS do `api.torbox.app`, a opcjonalne metadane do `search-api.torbox.app`.
