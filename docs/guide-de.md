# Camera Studio Community 0.9 — Anleitung

[English](guide-en.md) · [Deutsch](guide-de.md) · [Dansk](guide-da.md) · [Español](guide-es.md) · [Polski](guide-pl.md) · [Français](guide-fr.md)

## Installieren, starten und entfernen

Diese unabhängige Ubuntu-Anwendung hat einen eigenen Starter und eigene Einstellungen. Sie ersetzt Tiny 2 Studio nicht. Benötigt werden Python ab 3.10, GTK ab 4.8, GStreamer und Tesseract 5. Ubuntu 24.04 ist das Ziel der automatischen GitHub-Tests; ältere GTK-Versionen werden nicht unterstützt.

DEB herunterladen, im betreffenden Ordner ein Terminal öffnen und ausführen:

```sh
sudo apt install ./camera-studio-community_0.9.0_all.deb
camera-studio-community
```

Alternativ das Quell-ZIP entpacken, die Abhängigkeiten aus `build.py` installieren und `./Starten.sh` ausführen. Optionale Modelle und Kamera-SDKs werden weder mitgeliefert noch automatisch geladen. Für H.264/H.265 können `gstreamer1.0-plugins-bad` und `gstreamer1.0-libav` nötig sein.

Deinstallieren geht auch, wenn die Anwendung im App Center fehlt:

```sh
sudo apt remove camera-studio-community
```

Persönliche Einstellungen, Buchprojekte und das ursprüngliche Tiny 2 Studio bleiben erhalten. Eine nur entpackte Kopie entfernt man durch Löschen ihres Ordners, nachdem eigene Arbeiten gesichert wurden.

## Sprache und Hilfe

Unten im Hauptfenster English, Deutsch, Dansk, Español, Polski oder Français wählen. Die Auswahl wird gespeichert; zum Anwenden die Anwendung schließen und neu starten. Laufende Kameras werden dadurch nicht unterbrochen. Beim ersten Start gilt die Systemsprache, ersatzweise Englisch. Anleitung öffnet die lokale Hilfe in der aktiven Sprache, ohne Internet. `--language de` überschreibt die Sprache für einen Start und lässt die gespeicherte Auswahl erhalten.

## Tiny 2 steuern und Präzision verstehen

Kamera verbinden und Vorschau starten. Beim Verbinden werden nur Einstellungen gelesen. Bewegung bietet Zielwinkel, relative Schritte, Mitte, Stop, Zoom und Aufwecken/Ruhemodus. Manuelle Bewegungen schalten Tracking aus. Positionen speichern Zielwinkel und Zoom lokal; das sind keine gemessenen Istpositionen. SDK-Rohwinkel dienen der Diagnose; Achszuordnung und Genauigkeit sind nicht bestätigt.

Tracking und Verfolgungstempo werden in der Kamera umgesetzt. Ein Modus gilt erst nach passender Rückmeldung als bestätigt. Gesten hängen von den Kameraeinstellungen ab; die App kann die Erkennung weder einschalten noch ihren Aktivierungszustand lesen. Bildregler hängen vom Treiber ab. Beauty-Effekte und Hintergrundersatz sind nicht enthalten.

Bild auslagern öffnet ein verschiebbares Fenster. Manuell steuert man durch Ziehen mit linker Maustaste; das Mausrad zoomt. F11 schaltet Vollbild, Escape verlässt Vollbild und deaktiviert Manuell/G13. Text-, Uhr- und PNG/JPEG-Overlays erscheinen in dieser Vorschau; sie werden nicht als virtuelle Kamera an andere Programme ausgegeben.

## Weitere Kameras und Bildgrößen

Kameras & Profile öffnen, gewünschte Adapter aktivieren und Neu suchen wählen. Tiny 2 bleibt fest integriert. Linux/UVC-Kameras verwenden das allgemeine USB-Profil. Weitere JSON-Profile ordnen USB-Hersteller- und Produktkennungen zu; Vorlage: `profiles/usb-camera.example.json`. Profile enthalten Daten, keine ausführbaren Treiber. Tiny 2 kann damit nicht überschrieben werden. Proprietäre Kameras benötigen einen entwickelten Adapter.

Jede Kamera kann ein eigenes Fenster und einen eigenen KI-Chat haben. Rechtsklick im Bild zeigt Werkzeuge und Fenstergrößen. Aufnahmeauflösung und Bildrate stammen aus den gemeldeten Gerätemodi; eigene Größen sind nur innerhalb gemeldeter Größenbereiche verfügbar. Nach Änderungen die Vorschau neu starten. Eine andere Fenstergröße ändert nicht die Aufnahmeauflösung. Die Bildquellenanzeige nennt die tatsächlich gelieferten Abmessungen.

AmScope/MU300 benötigt eine vorhandene Linux-AmLite-Installation. Deren Vorschau vorher schließen. Gesucht wird unter `~/.local/opt/AmLite`, `/opt/AmLite`, `/usr/local/lib` und `/usr/lib`; `TINY2_AMCAM_LIBRARY` erlaubt einen anderen Bibliothekspfad. Andonstar verwendet LiveView-MJPEG auf Port 8192: Ubuntu zuerst mit dem Kamera-WLAN verbinden, Profil aktivieren und neu suchen. Die App wechselt kein WLAN. Diese Adapter handeln die Aufnahmegröße aus; die Sensorauflösung ist hier nicht frei wählbar. Andonstar bietet digitalen Bildzoom, keine Fokussteuerung des Mikroskops.

## Teilen, zeichnen und Bücher scannen

Bild teilen bietet Zwischenablage und PNG-Export. Auf einem Standbild mit Maus oder Tablet zeichnen: Stift, Textmarker, Radierer für ganze Striche, Druck, Rückgängig und Wiederholen. Das Ergebnis ausdrücklich an KI übergeben oder als PNG speichern.

Buchscan erfasst eine vollständige Seite pro Aufnahme. Ein ruhiges, gleichmäßig beleuchtetes Bild verwenden. Die Automatik wartet auf Seitenwechsel und ein stabiles Bild und pausiert zur Prüfung. Vier Ecken im Uhrzeigersinn ab oben links setzen oder die gewählte KI suchen lassen. Die entzerrte Seite prüfen und erst dann übernehmen; das Original bleibt erhalten. Lokale OCR liefert bearbeitbaren Text. Ergebnisse vor PDF-/EPUB-Export prüfen. `.tinybook`-Projekte speichern Bilder und Korrekturen. Grenze: 500 Seiten pro Projekt und 20 Megapixel pro Seite.

Nur deutsche und englische OCR-Daten liegen bei. Die Oberflächensprache übersetzt keine Bücher und ergänzt keine OCR-Sprachen. KI-Seitenkorrektur ist separat: ein verkleinertes Bild geht an den gewählten Anbieter; das Original wird lokal entzerrt. Automatische KI-Korrektur ist zunächst aus und wird bei Anbieterwechsel wieder ausgeschaltet.

## KI-Anbieter und Datenübertragung

Im KI-Fenster oder Buchscan Lokal, ChatGPT, Grok oder Gemini wählen. Unter KI-Einstellungen eine bildfähige Modell-ID mit strukturierten JSON-Antworten eintragen. Lokal verwendet ein bereits installiertes Ollama-Modell auf `127.0.0.1`; der Port ist einstellbar. Cloud-Anbieter benötigen ein eigenes API-Konto, Modellzugriff und einen Schlüssel. Das ist keine Anmeldung an deren Chat-Webseiten; API-Nutzung kann kostenpflichtig sein.

Ein Anbieterwechsel sendet nichts. Senden überträgt das gewählte Standbild, die Frage und bis zu acht Textnachrichten dieses Anbieterverlaufs. Alte Fotos werden nicht erneut versendet. Jeder Anbieter hat seinen eigenen Verlauf im Arbeitsspeicher, der beim Schließen des Fensters verworfen wird. Ziel und Modell werden angezeigt. Abbrechen verwirft spätere Antworten, kann bereits übertragene Daten aber nicht zurückholen. Kein automatischer Anbieterwechsel bei Fehlern. Antworten und Markierungen können falsch sein; die KI wird um Antworten in der Oberflächensprache gebeten.

Neue API-Schlüssel gelten zunächst nur für die Sitzung. Optionales Speichern schreibt sie unverschlüsselt in `api-keys.json`, nur für das Benutzerkonto lesbar mit Rechten 0600. Alternativ: `OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY` oder `GOOGLE_API_KEY`. Vorrang: Sitzung, Umgebung, gespeicherter Schlüssel. Entfernen löscht den gespeicherten Wert und sperrt ihn für die Sitzung; Umgebungsvariablen außerhalb der App entfernen. OpenAI/xAI-Anfragen verwenden `store=false`; das garantiert nicht den Ausschluss sämtlicher Anbieterprotokollierung.

## Diktat, Comics und G13

Diktat benötigt eine vorhandene Python-Installation mit faster-whisper und einen lokalen Modellordner mit `model.bin` und `config.json`. Unter KI & Dienste eintragen. Optional kann ein kompatibler Ordner mit `guard_common.py` konkurrierende Speichernutzung begrenzen. Audio wird lokal verarbeitet; der Text wird vor dem Senden zur Prüfung eingefügt. Keine Modelldownloads.

Comic lesen · lokale OCR öffnet ein separat eingerichtetes kompatibles InvenTree-Cover-Tool. Tesseract liest das Heftkästchen in zwei Durchgängen für Reihe, Heftnummer und Datum; die angebotene Panini-Suche hilft beim Abgleich. Unabhängig vom KI-Anbieter, keine zuverlässige Erkennung des ganzen Covers und keine automatische Bestandsbuchung. Ohne das Werkzeug bleiben Kopieren und PNG-Export verfügbar. Die Oberfläche des externen Werkzeugs wird durch diese App nicht übersetzt.

G13 benötigt einen vorhandenen kompatiblen g13d-Dienst und ein leeres M2-Profil namens `Tiny 2 Studio`. Die App installiert keine Tastaturprofile. Der G13-Reiter erklärt die Tasten. Explizit einschalten; dabei werden Maussteuerung und Mausrad-Zoom gesperrt. Nach Fokus-/Profilwechsel den Stick loslassen. G1/G22/Stickdruck stoppt und schaltet G13 aus; G15 bewegt fein. G16 nimmt eine Seite auf, G17 übernimmt eine geprüfte Seite. Ohne G13 funktionieren die normalen Bedienelemente.

## Dateien, Probleme und Grenzen

Einstellungen: `${XDG_CONFIG_HOME:-~/.config}/camera-studio-community/`. Bücher: `${XDG_DATA_HOME:-~/.local/share}/camera-studio-community/books/`. `--config-dir PFAD` wählt einen eigenen Einstellungsordner. Vor dem Löschen persönlicher Daten Buchprojekte sichern; Deinstallation löscht sie nicht.

Bei fehlendem Bild USB-Berechtigungen prüfen, andere Kamera-Apps schließen, Automatisch oder eine kleinere Auflösung wählen und die Vorschau neu starten. Bei KI-Fehlern Modellfähigkeiten, API-Zugang und angezeigtes Ziel prüfen. Keine Schlüssel, persönlichen Bilder oder Konfigurationsdateien in Fehlerberichte hochladen.

Hardwareunterstützung und mechanische Präzision sind nicht für jede Kamera bestätigt. Automatische Tests verwenden künstliche Kameras und simulierte Cloud-Antworten. Echte Cloud-Konten und sämtliche Hardwaremodi wurden nicht verifiziert. Prüfstand und Herkunft: `TESTERGEBNIS.txt` und `SOURCES.txt`.
