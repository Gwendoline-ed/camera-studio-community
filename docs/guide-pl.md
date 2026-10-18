# Camera Studio Community 0.9 — Instrukcja

[English](guide-en.md) · [Deutsch](guide-de.md) · [Dansk](guide-da.md) · [Español](guide-es.md) · [Polski](guide-pl.md) · [Français](guide-fr.md)

## Instalacja, uruchamianie i usuwanie

Ta niezależna aplikacja dla Ubuntu ma własny skrót i ustawienia. Nie zastępuje Tiny 2 Studio. Wymaga Pythona 3.10+, GTK 4.8+, GStreamera i Tesseract 5. Testy GitHub są przygotowane dla Ubuntu 24.04; starsze wersje GTK nie są obsługiwane.

Pobierz DEB, otwórz terminal w jego folderze i wykonaj:

```sh
sudo apt install ./camera-studio-community_0.9.0_all.deb
camera-studio-community
```

Możesz też rozpakować ZIP ze źródłami, zainstalować zależności wymienione w `build.py` i uruchomić `./Starten.sh`. Opcjonalne modele i SDK kamer nie są dołączane ani automatycznie pobierane. H.264/H.265 mogą wymagać pakietów `gstreamer1.0-plugins-bad` i `gstreamer1.0-libav`.

Usuwanie działa również wtedy, gdy aplikacji nie ma w App Center:

```sh
sudo apt remove camera-studio-community
```

Ustawienia osobiste, projekty książek i pierwotne Tiny 2 Studio pozostają zachowane. Kopię uruchamianą wyłącznie z rozpakowanego folderu usuwa się przez skasowanie tego folderu po zapisaniu pracy.

## Język i pomoc

Na dole okna głównego wybierz English, Deutsch, Dansk, Español, Polski lub Français. Wybór jest zapisywany; zamknij i ponownie uruchom aplikację, aby go zastosować. Działające kamery nie są przerywane. Przy pierwszym uruchomieniu używany jest język systemowy, a w razie braku obsługi angielski. Instrukcja otwiera lokalną pomoc w aktywnym języku bez internetu. `--language pl` wybiera język na jedno uruchomienie, zachowując zapisaną preferencję.

## Sterowanie Tiny 2 i dokładność

Połącz kamerę i uruchom podgląd. Łączenie tylko odczytuje ustawienia. Ruch oferuje kąty docelowe, kroki względne, środek, stop, zoom oraz wybudzenie/uśpienie. Ręczne ruchy wyłączają śledzenie. Pozycje zapisują lokalnie kąty docelowe i zoom; nie są to zmierzone pozycje fizyczne. Surowe kąty SDK służą do diagnostyki; przypisanie osi i dokładność nie zostały potwierdzone.

Śledzenie i jego szybkość realizuje kamera. Tryb jest potwierdzany dopiero po zgodnym odczycie. Rozpoznawanie gestów zależy od ustawień kamery; aplikacja nie może go włączyć ani odczytać, czy jest włączone. Regulatory obrazu zależą od sterownika. Efekty upiększania i zmiana tła nie są dostępne.

Odłącz obraz, aby otworzyć ruchome okno. Sterowanie ręczne działa przez przeciąganie lewym przyciskiem; kółko zmienia zoom. F11 przełącza pełny ekran. Escape opuszcza pełny ekran i wyłącza sterowanie ręczne/G13. Nakładki tekstowe, zegar i PNG/JPEG są widoczne w tej aplikacji; nie są przekazywane innym programom jako kamera wirtualna.

## Dodatkowe kamery i rozmiary obrazu

Otwórz Kamery i profile, włącz adaptery i wybierz Szukaj ponownie. Tiny 2 jest zawsze wbudowana. Kamery Linux/UVC używają ogólnego profilu USB. Dodatkowe profile JSON dopasowują identyfikatory producenta i produktu USB; wzór: `profiles/usb-camera.example.json`. Profile zawierają dane, a nie wykonywalne sterowniki. Nie mogą nadpisać Tiny 2. Kamery z własnym protokołem wymagają opracowania adaptera.

Każda kamera może mieć osobne okno i rozmowę AI. Prawy przycisk na obrazie otwiera narzędzia i rozmiary okna. Rozdzielczość i liczbę klatek wybiera się z trybów zgłoszonych przez urządzenie. Własne rozmiary są dostępne tylko w zgłoszonych zakresach. Po zmianie trybu uruchom podgląd ponownie. Zmiana rozmiaru okna nie zmienia rozdzielczości przechwytywania. Źródło obrazu pokazuje rzeczywiste wymiary otrzymanego obrazu.

AmScope/MU300 wymaga istniejącej instalacji AmLite dla Linuksa. Najpierw zamknij jej podgląd. Aplikacja szuka w `~/.local/opt/AmLite`, `/opt/AmLite`, `/usr/local/lib` i `/usr/lib`; `TINY2_AMCAM_LIBRARY` pozwala wskazać inną bibliotekę. Andonstar używa LiveView-MJPEG na porcie 8192: połącz Ubuntu z Wi-Fi kamery, włącz profil i wyszukaj ponownie. Aplikacja nie przełącza sieci Wi-Fi. Te adaptery uzgadniają rozmiar przechwytywania; rozdzielczości matrycy nie wybiera się tutaj. Andonstar oferuje cyfrowy zoom obrazu, a nie regulację ostrości mikroskopu.

## Udostępnianie, rysowanie i skanowanie książek

Udostępnij obraz oferuje schowek i eksport PNG. Rysuj na nieruchomym obrazie myszą lub tabletem: pisak, zakreślacz, gumka całych kresek, nacisk, cofanie i ponawianie. Jawnie przekaż wynik do AI albo zapisz PNG.

Skanowanie książki przechwytuje jedną pełną stronę na ujęcie. Zapewnij stabilny obraz i równomierne oświetlenie. Automat czeka na zmianę strony i stabilizację obrazu, po czym zatrzymuje się do sprawdzenia. Zaznacz cztery narożniki zgodnie z ruchem wskazówek zegara od lewego górnego lub użyj wybranej AI. Sprawdź wyprostowaną stronę przed zatwierdzeniem; oryginał zostaje zachowany. Lokalne OCR dostarcza edytowalny tekst. Sprawdź wyniki przed eksportem PDF/EPUB. Projekty `.tinybook` przechowują obrazy i poprawki. Limit: 500 stron na projekt i 20 megapikseli na stronę.

Dołączone dane OCR obejmują tylko niemiecki i angielski. Język interfejsu nie tłumaczy książek ani nie dodaje języków OCR. Korekta strony przez AI jest osobna: pomniejszony obraz trafia do wybranego dostawcy, a oryginał jest prostowany lokalnie. Automatyczna korekta AI jest początkowo wyłączona i wyłącza się przy zmianie dostawcy.

## Dostawcy AI i dane

W oknie AI lub skanowaniu wybierz Lokalnie, ChatGPT, Grok lub Gemini. W Ustawieniach AI podaj identyfikator modelu obsługującego obrazy i ustrukturyzowane odpowiedzi JSON. Lokalnie używa już zainstalowanego modelu Ollama pod `127.0.0.1`; port można zmienić. Dostawcy chmurowi wymagają własnego konta API, dostępu do modelu i klucza. To nie jest logowanie do ich stron czatu; użycie API może być płatne.

Zmiana dostawcy niczego nie wysyła. Wyślij przekazuje wybrany obraz, pytanie i do ośmiu wiadomości tekstowych z rozmowy tego dostawcy. Starsze zdjęcia nie są ponownie wysyłane. Każdy dostawca ma osobną historię w pamięci, usuwaną przy zamknięciu okna. Cel i model są widoczne. Anulowanie odrzuca późniejsze odpowiedzi, ale nie cofa już wysłanych danych. Nie ma automatycznego przełączania dostawcy po błędzie. Odpowiedzi i oznaczenia mogą być błędne; AI otrzymuje polecenie odpowiadania w języku interfejsu.

Nowe klucze API domyślnie działają tylko w sesji. Opcjonalny zapis tworzy nieszyfrowany `api-keys.json`, czytelny tylko dla właściciela dzięki uprawnieniom 0600. Alternatywnie: `OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY` lub `GOOGLE_API_KEY`. Kolejność: sesja, środowisko, zapisany klucz. Usunięcie kasuje zapisany klucz i blokuje go w sesji; zmienne środowiskowe usuwa się poza aplikacją. OpenAI/xAI używają `store=false`; nie gwarantuje to braku wszelkiego rejestrowania danych przez dostawcę.

## Dyktowanie, komiksy i G13

Dyktowanie wymaga istniejącego Pythona z faster-whisper i lokalnego folderu modelu z `model.bin` i `config.json`. Skonfiguruj je w AI i usługi. Opcjonalny zgodny folder z `guard_common.py` może ograniczać równoczesne zużycie pamięci. Dźwięk jest przetwarzany lokalnie; tekst trafia do pola w celu sprawdzenia przed wysłaniem. Modele nie są pobierane.

Odczytaj komiks · lokalne OCR otwiera oddzielnie skonfigurowane zgodne narzędzie okładek InvenTree. Tesseract dwukrotnie odczytuje ramkę numeru, by ustalić serię, numer i datę; wyszukiwanie Panini pomaga sprawdzić wydanie. Funkcja jest niezależna od dostawcy AI, nie identyfikuje niezawodnie całej okładki i nie księguje zapasu automatycznie. Bez narzędzia nadal można kopiować i eksportować PNG. Interfejs zewnętrznego narzędzia nie jest tłumaczony przez tę aplikację.

G13 wymaga istniejącej zgodnej usługi g13d i pustego profilu M2 o nazwie `Tiny 2 Studio`. Aplikacja nie instaluje profili klawiatury. Karta G13 opisuje przyciski. Włącz G13 jawnie; blokuje wtedy mysz i zoom kółkiem. Po zmianie aktywnego okna/profilu puść drążek. G1/G22/naciśnięcie drążka zatrzymuje ruch i wyłącza G13; G15 daje precyzyjny ruch. G16 przechwytuje stronę, G17 zatwierdza sprawdzoną stronę. Bez G13 działają zwykłe elementy sterujące.

## Pliki, problemy i ograniczenia

Ustawienia: `${XDG_CONFIG_HOME:-~/.config}/camera-studio-community/`. Książki: `${XDG_DATA_HOME:-~/.local/share}/camera-studio-community/books/`. `--config-dir ŚCIEŻKA` wybiera osobny folder ustawień. Przed usunięciem danych osobistych zrób kopię projektów; odinstalowanie ich nie usuwa.

Przy braku obrazu sprawdź uprawnienia USB, zamknij inne aplikacje kamery, wybierz Automatycznie lub niższą rozdzielczość i uruchom podgląd ponownie. Przy błędach AI sprawdź możliwości modelu, dostęp API i wyświetlany cel. Nie dołączaj kluczy, prywatnych zdjęć ani plików konfiguracji do zgłoszeń.

Obsługa sprzętu i dokładność mechaniczna nie są potwierdzone dla każdej kamery. Testy automatyczne korzystają z kamer syntetycznych i symulowanych odpowiedzi chmury. Nie zweryfikowano rzeczywistych kont chmurowych ani wszystkich trybów sprzętu. Wyniki i źródła: `TESTERGEBNIS.txt` oraz `SOURCES.txt`.
