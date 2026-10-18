# Third-party notices and provenance

## Application

The application code and documentation are released under the MIT license in `LICENSE`. The Community edition is an independent continuation of the original Tiny 2 Studio implementation. Brand names identify compatible devices/services; this project is not affiliated with or endorsed by those companies.

## Bundled OCR data — Apache License 2.0

The only bundled third-party runtime data are:

- `tiny2/data/ocr/deu.traineddata.gz`
- `tiny2/data/ocr/eng.traineddata.gz`

These are Tesseract language data distributed under Apache-2.0. The unmodified license is included as `tiny2/data/ocr/LICENSE-Apache-2.0.txt`. This component keeps its own license; the application MIT license does not relicense it.

Sources and original SHA-256 values:

| File | Source | SHA-256 |
| --- | --- | --- |
| German | https://tessdata.projectnaptha.com/4.0.0/deu.traineddata.gz | f5618a8b8d07f6c7a633ce243bf075bb90f4145bb15c9264734c7cc63aa33205 |
| English | https://tessdata.projectnaptha.com/4.0.0/eng.traineddata.gz | ed350f3752f81ee8f38769edc14d92d997dababe23b565c59879372cc46a2468 |

Upstream: https://github.com/tesseract-ocr/tessdata

## External dependencies

GTK, GStreamer, PyGObject, Cairo, Pillow and Tesseract libraries are installed from the operating system, not vendored here. Their upstream licenses apply independently. AmLite/libamcam, Ollama models, faster-whisper models, the compatible G13 service and the optional cover tool must be obtained and configured separately. Their code, models and installers are not included in this repository or release packages.

## Protocol research

Tiny 2 commands were independently implemented in Python after static analysis of user-supplied OBSBOT Center/Firmware binaries and comparison with public protocol documentation. No manufacturer binaries, firmware, extracted decompiler output or SDK libraries are distributed. `SOURCES.txt` preserves hashes, addresses, observations and links; source facts are distinct from verified hardware behavior.

Public protocol references include https://github.com/lxman/obsbot-mcp and https://github.com/mitchelloharawild/obsbot-tiny-2-control. The latter supplied packet reference values used as test vectors. AmScope adapter layout was checked against published SDK headers and the existing local library. Andonstar references include https://github.com/rgov/novatek-api and https://github.com/nutsey/novatek-web-api-commands. These are provenance references, not bundled dependencies.

License text source: https://opensource.org/license/mit
