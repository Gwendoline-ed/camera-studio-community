# Contributing

Keep Community independent of Tiny 2 Studio: separate application ID, package, launcher, configuration and data directories. Never migrate or overwrite the original app automatically.

## Setup and tests

Install the runtime dependencies from README. For headless GUI tests install `xvfb`, `xauth`, `dbus-x11`, and `gcc` for the fake SDK. Use `/usr/bin/python3`, not a Python environment missing distro GTK bindings.

```sh
/usr/bin/python3 -B tools/render_docs.py
/usr/bin/python3 -B -m unittest discover -s tests -p 'test_*.py'
xvfb-run -a env PYTHONPATH=. GSK_RENDERER=cairo /usr/bin/python3 -B tests/gui_languages.py fr /tmp/camera-studio-fr
xvfb-run -a env PYTHONPATH=. GSK_RENDERER=cairo /usr/bin/python3 -B tests/gui_ai.py /tmp/camera-studio-ai
/usr/bin/python3 -B build.py
```

`gui_languages.py` uses synthetic video and a simulated camera. Run it for `en de da es pl fr`. `gui_ai.py` simulates cloud replies and never needs real credentials. Some historical GUI scripts require optional fixture installations; they are not part of the CI contract. Do not perform a hardware test without explicitly selecting the intended device.

## Translations and guides

`tiny2/i18n.py` provides `tr` (imported as `_t`). Catalog keys are the German source strings to preserve compatibility with existing messages; values live in `tiny2/locales/{en,de,da,es,pl,fr}.json`. Translate whole sentences where possible, retaining all named placeholders and format specifications. Call translation before formatting. Never translate protocol identifiers, database keys, model IDs, filenames chosen by users, or user-authored content. Translate stable camera enum values only at presentation boundaries.

Add a message to every catalog. The test suite checks key parity, literal call coverage and placeholder integrity. Language preference is saved separately in `language.json` and applied at next startup; changing it must not move cameras or interrupt capture. Providers are requested to answer in the interface language. OCR language support is independent.

Edit all six `docs/guide-*.md` manuals together. Run `tools/render_docs.py` to regenerate the offline HTML. The renderer supports headings, paragraphs, inline code, fenced code blocks and relative guide links. It has no network or JavaScript dependency. Native speakers are welcome to improve wording; do not claim the translations have received professional linguistic review.

## Camera profiles

Use `profiles/usb-camera.example.json` for USB matching. JSON profiles are declarative and cannot override Tiny 2 or load executable code. Keep proprietary SDK support in explicit adapters and do not commit SDK binaries. Include observed device IDs, negotiated modes, firmware versions and reproducible results in compatibility reports. Distinguish tested hardware behavior from simulation.

## Changes and releases

Explain the user-visible problem, the resulting behavior and meaningful validation. Keep API keys and personal configuration out of logs, fixtures and commits. License contributions under MIT; preserve third-party notices. Update `tiny2/__init__.py`, the changelog and versioned installation examples together.

Build from a clean checkout. Review the generated ZIP and DEB, manifests and checksums before uploading. The CI workflow tests and builds artifacts; it does not create a release or publish packages automatically. Use the release draft in `docs/RELEASE-0.9.0.md` for a GitHub release once the repository is published. GitHub workflow versions follow the official action documentation: https://github.com/actions/checkout and https://github.com/actions/upload-artifact.
