# Camera Studio Community 0.9 — User guide

[English](guide-en.md) · [Deutsch](guide-de.md) · [Dansk](guide-da.md) · [Español](guide-es.md) · [Polski](guide-pl.md) · [Français](guide-fr.md)

## Install, launch and remove

This independent Ubuntu application has its own launcher and settings. It does not replace Tiny 2 Studio. It requires Python 3.10+, GTK 4.8+, GStreamer and Tesseract 5. Ubuntu 24.04 is the CI target; older GTK versions are not supported.

Download the DEB, open a terminal in its folder and run:

```sh
sudo apt install ./camera-studio-community_0.9.0_all.deb
camera-studio-community
```

To use the source ZIP instead, extract it, install the dependencies listed in `build.py`, and run `./Starten.sh`. Optional models and camera SDKs are not included or downloaded automatically. H.264/H.265 may require the additional GStreamer packages `gstreamer1.0-plugins-bad` and `gstreamer1.0-libav`.

Removal also works when App Center does not list the application:

```sh
sudo apt remove camera-studio-community
```

This leaves personal settings, book projects and the original Tiny 2 Studio intact. A source-only copy is removed by deleting its extracted folder after saving your work.

## Language and help

At the bottom of the main window, select English, Deutsch, Dansk, Español, Polski or Français. The selection is saved; close and restart the application to apply it. This avoids interrupting camera operation. On first launch the system language is used, with English as fallback. The Guide button opens the local guide for the active language. No internet connection is needed. `--language en` overrides the language for one launch; saved preferences are retained.

## Tiny 2 controls and precision

Connect the camera and start the preview. Connecting only reads settings. Movement provides target angles, relative steps, center, stop, zoom and wake/sleep. Manual movements disable tracking. Positions save target angles and zoom locally; they are not measured physical positions. Raw SDK angles are diagnostic values with unverified axis mapping and accuracy.

Tracking modes and tracking speed run in the camera. A mode is shown as confirmed only after matching feedback. Gesture recognition depends on camera settings; this application cannot enable it or read whether it is enabled. Image controls depend on what the camera driver exposes. Beauty effects and background replacement are not included.

Detach the image for a movable window. Manual control uses left-button dragging; the wheel changes zoom. Full screen uses F11; Escape leaves full screen and disables manual/G13 control. Text, clock and PNG/JPEG overlays appear in this application's preview, not as a virtual camera for other programs.

## Additional cameras and image sizes

Open Cameras & profiles, enable the desired adapters and select Scan again. Tiny 2 is always built in. Linux/UVC cameras use the generic USB profile. Additional JSON profiles match USB vendor/product IDs; `profiles/usb-camera.example.json` is a template. Profiles contain data, not executable drivers. They cannot override Tiny 2. Proprietary cameras need an implemented adapter.

Each camera can have its own window and AI conversation. Right-click its image for tools and window sizes. Capture resolution and frame rate are selected from modes reported by the device; custom sizes appear only for camera-declared ranges. Restart the preview after changing the mode. Resizing a window does not change capture resolution. The image-source label shows the delivered dimensions.

AmScope/MU300 requires an existing Linux AmLite installation. Close its camera preview first. The application searches `~/.local/opt/AmLite`, `/opt/AmLite`, `/usr/local/lib` and `/usr/lib`; `TINY2_AMCAM_LIBRARY` can specify another library. Andonstar uses its LiveView MJPEG service on port 8192: connect Ubuntu to the camera's Wi-Fi first, enable the profile and scan again. The application does not switch Wi-Fi networks. These adapters negotiate capture size; their sensor resolution is not selectable here. Andonstar supports digital image zoom, not microscope focus adjustment.

## Share, draw and scan books

Share image offers clipboard copy and PNG export. Draw on a frozen image with mouse or tablet: pen, highlighter, whole-stroke eraser, pressure, undo and redo. Send the result to AI explicitly or save it as PNG.

Book scan captures one complete page at a time. Choose a steady, evenly lit image. Automatic capture waits for a page change and a stable image, and pauses for review. Set four corners clockwise from top left or use the selected AI to find them. Review the corrected page before accepting it. The original is retained. Local OCR supplies editable text; review recognition results before exporting PDF or EPUB. Save/open `.tinybook` projects to keep images and corrections. Up to 500 pages per project and 20 megapixels per page are supported.

Only German and English OCR data are bundled. Changing interface language does not translate books or add OCR languages. AI page correction is separate: it sends a reduced image to the selected provider, then rectifies the original locally. Automatic AI correction is off initially and turns off when changing provider.

## AI providers and privacy

Choose Local, ChatGPT, Grok or Gemini in the AI window or book scan. In AI settings, enter a vision-capable model ID supporting structured JSON responses. Local uses an already installed Ollama model on `127.0.0.1`; its port is configurable. Cloud providers require your own API account, model access and key. This is not a login to their chat websites; API usage may cost money.

Changing provider sends nothing. Send transmits the selected still image, question and up to eight text messages from that provider's conversation. Previous photos are not resent. Each provider has its own in-memory history, discarded when the window closes. The destination and model are displayed. Cancellation discards later results but cannot retrieve data already sent. There is no automatic provider fallback. AI answers and markers may be wrong; the AI is asked to answer in the interface language.

New API keys are session-only by default. Optional persistence stores plaintext `api-keys.json` with owner-only permissions 0600. Alternatively use `OPENAI_API_KEY`, `XAI_API_KEY` or `GEMINI_API_KEY` (`GOOGLE_API_KEY` also accepted). Priority: session, environment, stored key. Removing a key deletes the stored value and blocks it for that session; remove environment keys outside the application. OpenAI/xAI requests use `store=false`, which is not a guarantee about all provider logging.

## Dictation, comics and G13

Dictation requires an existing Python installation with faster-whisper and a local model folder containing `model.bin` and `config.json`. Configure them in AI & services. An optional compatible `guard_common.py` folder can limit competing memory use. Audio is processed locally; dictation inserts text for review before sending. No model is downloaded.

Read comic · local OCR opens a separately configured compatible InvenTree cover tool. Tesseract reads the issue box in two passes to identify series, issue and date; the offered Panini search helps check the edition. This is independent of the selected AI, does not identify a whole cover reliably and does not book stock automatically. Without that tool, copy and PNG export still work. The external tool's own interface is not translated by this application.

G13 requires an existing compatible g13d service and an empty M2 profile named `Tiny 2 Studio`. The application installs no keyboard profiles. The G13 tab lists bindings. Enable it explicitly; it disables mouse movement and wheel zoom. Release the stick after a focus/profile change. G1/G22/stick press stops and disables G13; G15 gives fine movement. G16 captures a page and G17 accepts a reviewed page. Without G13, ordinary controls remain available.

## Files, troubleshooting and limits

Settings: `${XDG_CONFIG_HOME:-~/.config}/camera-studio-community/`. Books: `${XDG_DATA_HOME:-~/.local/share}/camera-studio-community/books/`. `--config-dir PATH` selects a separate configuration directory. Back up book projects before deleting personal data; uninstalling does not delete it.

For a missing image, check USB permissions, close competing camera applications, select Automatic or a lower resolution, and restart the preview. For AI errors, check model capabilities, API access and the displayed destination. Avoid uploading keys, personal images or configuration files to bug reports.

Hardware support and mechanical accuracy are not certified for every camera. Automated tests use synthetic cameras and simulated cloud responses; real cloud account access and every hardware mode are not verified. See `TESTERGEBNIS.txt` and `SOURCES.txt` for evidence and provenance.
