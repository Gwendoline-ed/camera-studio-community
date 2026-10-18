"""Isolated AmScope SDK process. Framed RGB output, no GUI or image files."""
from .i18n import tr as _t
import json
import signal
import sys
import threading
import time
from .amcam import SDK,Capture


def main():
    stopped=threading.Event();camera=None
    signal.signal(signal.SIGTERM,lambda *_:stopped.set())
    try:
        sdk=SDK()
        if sys.argv[1:]==['--list']:
            print(json.dumps({'cameras':sdk.discover(),'version':sdk.Version().decode()}));return 0
        if len(sys.argv)!=2:raise ValueError(_t('AmScope-Kamera fehlt.'))
        camera=Capture(sdk,sys.argv[1]);last=time.monotonic()
        while not stopped.is_set():
            frame=camera.next_frame()
            if frame:
                width,height,stride,data=frame
                header={'type':'frame','width':width,'height':height,'stride':stride,'size':len(data)}
                sys.stdout.buffer.write(json.dumps(header).encode()+b'\n');sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
                last=time.monotonic()
            elif time.monotonic()-last>20:raise TimeoutError(_t('AmScope liefert seit 20 Sekunden kein Bild. Bitte AmLite-Vorschau schließen und Kamera prüfen.'))
        return 0
    except (BrokenPipeError,KeyboardInterrupt):return 0
    except Exception as error:
        print(json.dumps({'type':'error','error':str(error)}),flush=True);return 1
    finally:
        if camera:camera.close()


if __name__=='__main__':raise SystemExit(main())
