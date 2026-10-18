# Camera Studio Community 0.9.0

Six interface languages and offline guides are now available: English, German, Danish, Spanish, Polish and French. Select the language at the bottom of the main window and restart. Camera control, AI, book scanning, drawing, settings and status messages use the selected language. German/English OCR language support remains separate.

This release also prepares the project for community contributions under MIT, with attribution for the Apache-2.0 OCR data, tests and a build workflow. It remains a separate application from Tiny 2 Studio.

## Downloads

- `camera-studio-community_0.9.0_all.deb`: installable Ubuntu package.
- `camera-studio-community-0.9.0.zip`: complete source and offline guides.
- `SHA256SUMS-community.txt`: checksums for these two artifacts.

Install with `sudo apt install ./camera-studio-community_0.9.0_all.deb`. Remove with `sudo apt remove camera-studio-community`; personal settings and book projects remain.

## Validation and limits

Catalog and protocol checks, synthetic GTK tests for all six languages, simulated AI provider tests and package integrity checks are included. See `TESTERGEBNIS.txt` for the exact locally completed checks. GitHub-hosted CI runs only after the repository is pushed. Real cloud requests, all camera models and mechanical precision are not certified. Translation wording can be improved through community review.
