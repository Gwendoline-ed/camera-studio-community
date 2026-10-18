from .i18n import tr as _t
import argparse
from dataclasses import asdict
import json
import sys


def main():
    from . import i18n
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument('--config-dir')
    bootstrap.add_argument('--language', choices=i18n.LANGUAGES)
    initial, _ = bootstrap.parse_known_args()
    i18n.configure(initial.config_dir, initial.language)
    parser=argparse.ArgumentParser(description=_t('Camera Studio Community für Ubuntu'))
    parser.add_argument("--diagnose",action="store_true",help=_t('Nur Identität, Verbindung und Status lesen'))
    parser.add_argument("--device",help=_t('Bestimmten Tiny-2-Videoknoten auswählen, z.B. /dev/video1'))
    parser.add_argument("--config-dir",help=_t('Alternativer Ordner für Positionen und Overlays'))
    parser.add_argument("--tab",choices=("motion", "tracking", "image", "overlays", "g13"),help=_t('Gewünschte Steuerungsseite beim Start öffnen'))
    parser.add_argument("--smoke-test",action="store_true",help=_t('Oberfläche mit Testbild prüfen; kein Kamerazugriff'))
    parser.add_argument("--screenshot",help=_t('Im Oberflächentest ein Bild der eigenen Anwendung speichern'))
    parser.add_argument('--language', choices=i18n.LANGUAGES, help=_t('Sprache für diesen Start auswählen'))
    args=parser.parse_args()
    from .camera_profiles import config_root
    args.config_dir = str(config_root(args.config_dir))
    if args.diagnose:
        from .device import discover,connect
        report={"devices":[asdict(item) for item in discover()],"connected":False,"writes":False}
        camera=None
        try:
            camera=connect(args.device,writable=False);report.update(connected=True,status=camera.status())
        except Exception as error:report['error']=str(error)
        finally:
            if camera:camera.close()
        print(json.dumps(report,indent=2,ensure_ascii=False))
        return 0 if report['connected'] else 2
    try:
        from .app import run
        return run(args)
    except (ImportError,ValueError,RuntimeError) as error:
        print(_t('Start fehlgeschlagen:'),error,file=sys.stderr)
        print(_t('Benötigt: python3-gi, python3-gi-cairo, python3-cairo, gir1.2-gtk-4.0, gir1.2-gdkpixbuf-2.0, gir1.2-pango-1.0, gir1.2-gstreamer-1.0, gstreamer1.0-plugins-good'),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
