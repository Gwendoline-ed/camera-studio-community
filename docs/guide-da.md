# Camera Studio Community 0.9 — Brugervejledning

[English](guide-en.md) · [Deutsch](guide-de.md) · [Dansk](guide-da.md) · [Español](guide-es.md) · [Polski](guide-pl.md) · [Français](guide-fr.md)

## Installation, start og afinstallation

Dette selvstændige Ubuntu-program har sin egen starter og egne indstillinger. Det erstatter ikke Tiny 2 Studio. Krav: Python 3.10+, GTK 4.8+, GStreamer og Tesseract 5. Ubuntu 24.04 er mål for GitHub-testene; ældre GTK-versioner understøttes ikke.

Hent DEB-filen, åbn en terminal i dens mappe, og kør:

```sh
sudo apt install ./camera-studio-community_0.9.0_all.deb
camera-studio-community
```

Du kan også pakke kilde-ZIP-filen ud, installere afhængighederne fra `build.py` og køre `./Starten.sh`. Valgfrie modeller og kamera-SDK'er medfølger ikke og hentes ikke automatisk. H.264/H.265 kan kræve `gstreamer1.0-plugins-bad` og `gstreamer1.0-libav`.

Afinstallation virker også, selv om programmet ikke vises i App Center:

```sh
sudo apt remove camera-studio-community
```

Personlige indstillinger, bogprojekter og det oprindelige Tiny 2 Studio bevares. En kopi, der kun er pakket ud, fjernes ved at slette dens mappe, efter at dit arbejde er gemt.

## Sprog og hjælp

Vælg English, Deutsch, Dansk, Español, Polski eller Français nederst i hovedvinduet. Valget gemmes; luk og genstart programmet for at anvende det. Aktive kameraer afbrydes ikke. Første start bruger systemsproget, ellers engelsk. Vejledning åbner den lokale hjælp på det aktive sprog uden internet. `--language da` vælger sprog for én start uden at ændre det gemte valg.

## Tiny 2 og nøjagtighed

Tilslut kameraet, og start forhåndsvisningen. Tilslutning læser kun indstillinger. Bevægelse tilbyder målvinkler, relative trin, centrering, stop, zoom og vågen/dvale. Manuelle bevægelser slår sporing fra. Positioner gemmer målvinkler og zoom lokalt; de er ikke målte fysiske positioner. Rå SDK-vinkler er diagnoseværdier med ubekræftet aksetilknytning og nøjagtighed.

Kameraet udfører sporing og vælger sporingshastighed. En tilstand bekræftes først efter passende tilbagemelding. Gestusregistrering afhænger af kameraets indstillinger; appen kan hverken aktivere den eller læse dens aktiveringstilstand. Billedindstillinger afhænger af driveren. Skønhedseffekter og baggrundserstatning er ikke inkluderet.

Frigør billedet til et flytbart vindue. Manuel styring bruger venstre museknap og træk; musehjulet zoomer. F11 skifter fuld skærm. Escape forlader fuld skærm og slår manuel/G13-styring fra. Tekst-, ur- og PNG/JPEG-overlejringer vises i denne app, men leveres ikke som virtuelt kamera til andre programmer.

## Flere kameraer og billedstørrelser

Åbn Kameraer og profiler, aktivér de ønskede adaptere, og vælg Søg igen. Tiny 2 er altid indbygget. Linux/UVC-kameraer bruger den generelle USB-profil. Yderligere JSON-profiler matcher USB-producent- og produkt-ID'er; skabelon: `profiles/usb-camera.example.json`. Profiler indeholder data, ikke kørbare drivere. De kan ikke erstatte Tiny 2. Proprietære kameraer kræver en udviklet adapter.

Hvert kamera kan have eget vindue og egen AI-samtale. Højreklik i billedet for værktøjer og vinduesstørrelser. Optageopløsning og billedhastighed vælges blandt enhedens rapporterede tilstande. Egne størrelser er kun mulige inden for rapporterede intervaller. Genstart forhåndsvisningen efter ændringer. Vinduesstørrelsen ændrer ikke optageopløsningen. Billedkilde viser de faktisk leverede dimensioner.

AmScope/MU300 kræver en eksisterende Linux-AmLite-installation. Luk dens kameravisning først. Programmet søger i `~/.local/opt/AmLite`, `/opt/AmLite`, `/usr/local/lib` og `/usr/lib`; `TINY2_AMCAM_LIBRARY` kan angive et andet bibliotek. Andonstar bruger LiveView-MJPEG på port 8192: forbind først Ubuntu til kameraets Wi-Fi, aktivér profilen, og søg igen. Appen skifter ikke Wi-Fi-net. Disse adaptere forhandler optagestørrelse; sensoropløsningen kan ikke vælges her. Andonstar har digital billedzoom, ikke mikroskopets fokusstyring.

## Deling, tegning og bogscanning

Del billede tilbyder udklipsholder og PNG-eksport. Tegn på et stillbillede med mus eller tablet: pen, overstregning, viskelæder til hele streger, tryk, fortryd og gentag. Send resultatet udtrykkeligt til AI, eller gem som PNG.

Bogscanning optager én hel side ad gangen. Brug et roligt, jævnt belyst billede. Automatik venter på sideskift og et stabilt billede og holder pause til kontrol. Angiv fire hjørner med uret fra øverst til venstre, eller lad den valgte AI finde dem. Kontrollér den oprettede side før godkendelse; originalen bevares. Lokal OCR giver redigerbar tekst. Kontrollér resultatet før PDF-/EPUB-eksport. `.tinybook`-projekter gemmer billeder og rettelser. Grænse: 500 sider pr. projekt og 20 megapixel pr. side.

Kun tyske og engelske OCR-data medfølger. Grænsefladesproget oversætter ikke bøger og tilføjer ikke OCR-sprog. AI-sidekorrektion er separat: et mindre billede sendes til udbyderen; originalen rettes lokalt. Automatisk AI-korrektion er slået fra i starten og slås fra igen ved udbyderskift.

## AI-udbydere og data

Vælg Lokal, ChatGPT, Grok eller Gemini i AI-vinduet eller bogscanningen. Angiv under AI-indstillinger et model-ID med billedforståelse og strukturerede JSON-svar. Lokal bruger en allerede installeret Ollama-model på `127.0.0.1`; porten kan ændres. Cloududbydere kræver egen API-konto, modeladgang og nøgle. Dette er ikke login på deres chatwebsteder; API-brug kan koste penge.

Udbyderskift sender intet. Send overfører det valgte stillbillede, spørgsmålet og højst otte tekstbeskeder fra denne udbyders samtale. Gamle billeder sendes ikke igen. Hver udbyder har egen historik i hukommelsen, som kasseres, når vinduet lukkes. Destination og model vises. Annullering forkaster senere svar, men kan ikke hente allerede sendte data tilbage. Der skiftes ikke automatisk udbyder ved fejl. AI-svar og markeringer kan være forkerte; AI'en bedes svare på grænsefladens sprog.

Nye API-nøgler gælder kun for sessionen som standard. Valgfri lagring skriver ukrypteret `api-keys.json` med rettigheder 0600, kun læsbar for brugerkontoen. Alternativer: `OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY` eller `GOOGLE_API_KEY`. Prioritet: session, miljøvariabel, gemt nøgle. Fjern sletter den gemte nøgle og spærrer den i sessionen; miljøvariabler fjernes uden for appen. OpenAI/xAI bruger `store=false`; det garanterer ikke fravær af al udbyderlogning.

## Diktering, tegneserier og G13

Diktering kræver en eksisterende Python-installation med faster-whisper og en lokal modelmappe med `model.bin` og `config.json`. Angiv dem under AI og tjenester. En valgfri kompatibel mappe med `guard_common.py` kan begrænse konkurrerende hukommelsesbrug. Lyd behandles lokalt; teksten indsættes til kontrol før afsendelse. Ingen modeller hentes.

Læs tegneserie · lokal OCR åbner et separat opsat, kompatibelt InvenTree-omslagsværktøj. Tesseract læser nummerfeltet to gange for serie, hæftenummer og dato; den tilbudte Panini-søgning hjælper med at kontrollere udgaven. Funktionen er uafhængig af AI-udbyderen, genkender ikke pålideligt hele omslaget og bogfører ikke lager automatisk. Uden værktøjet virker kopiering og PNG-eksport stadig. Det eksterne værktøjs grænseflade oversættes ikke af denne app.

G13 kræver en eksisterende kompatibel g13d-tjeneste og en tom M2-profil ved navn `Tiny 2 Studio`. Appen installerer ingen tastaturprofiler. G13-fanen viser tasterne. Aktivér udtrykkeligt; musestyring og musehjulszoom spærres imens. Slip sticken efter fokus-/profilskift. G1/G22/sticktryk stopper og deaktiverer G13; G15 giver fin bevægelse. G16 optager en side, G17 godkender en kontrolleret side. Uden G13 virker almindelige kontroller.

## Filer, problemer og begrænsninger

Indstillinger: `${XDG_CONFIG_HOME:-~/.config}/camera-studio-community/`. Bøger: `${XDG_DATA_HOME:-~/.local/share}/camera-studio-community/books/`. `--config-dir STI` vælger en anden indstillingsmappe. Sikkerhedskopiér bogprojekter før sletning af personlige data; afinstallation sletter dem ikke.

Ved manglende billede: kontrollér USB-rettigheder, luk andre kameraapps, vælg Automatisk eller lavere opløsning, og genstart forhåndsvisningen. Ved AI-fejl: kontrollér modelmuligheder, API-adgang og destination. Medtag ikke nøgler, personlige billeder eller konfigurationsfiler i fejlrapporter.

Hardwareunderstøttelse og mekanisk nøjagtighed er ikke bekræftet for alle kameraer. Automatiske tests bruger syntetiske kameraer og simulerede cloudsvar. Rigtige cloudkonti og alle hardwaretilstande er ikke verificeret. Dokumentation for tests og kilder: `TESTERGEBNIS.txt` og `SOURCES.txt`.
