"""Actual Andonstar WLAN stream, independent Tiny test stream and lifecycle checks."""
import io
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from gui_integration import SyntheticCamera,pump
from gui_gwen_share import capture
from tiny2.app import Studio
from tiny2.scope_window import Source
from tiny2.network_preview import NetworkPreview


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=True)
    camera=SyntheticCamera()
    with tempfile.TemporaryDirectory() as tmp,patch('tiny2.app.device.connect',return_value=camera):
        app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None));app.register(None);app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            app.preview.start(None,test=True);pump(lambda:app.frames_seen>3)
            app.open_scope();controls=app.scope_controls;pump(lambda:not controls.searching)
            channel=next(c for c in controls.channels.values() if c.source.backend=='andonstar')
            capture(controls,root/'Andonstar-Auswahl.png')
            controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching)
            scope=channel.viewer;assert isinstance(scope.preview,NetworkPreview)
            pump(lambda:scope.picture.get_paintable() is not None,timeout=12)
            texture=scope.picture.get_paintable();assert (texture.get_width(),texture.get_height())==(640,368)
            texture.save_to_png(str(root/'Andonstar-Livebild.png'))
            assert not scope.get_decorated() and scope.get_child()==scope.picture
            pump(lambda:scope.get_width()==450)
            capture(scope,root/'Andonstar-Fenster.png')
            before=app.frames_seen;scope.resize_view(.75);pump(lambda:scope.get_width()==675)
            scope.close();pump(lambda:app.frames_seen>before)
            assert channel.viewer is None and not controls.rows[channel.source.key]['enabled'].get_active()
            controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching)
            scope=channel.viewer;pump(lambda:scope.picture.get_paintable() is not None,timeout=12)
            assert app.preview.pipeline;scope.close()
            # A slow search must not block the main preview; closing cancels its pending result.
            gate=threading.Event()
            def slow():gate.wait(5);return [Source('/dev/video123','Stale result')]
            with patch('tiny2.scope_window.sources',side_effect=slow):
                before=app.frames_seen;controls.refresh()
                pump(lambda:app.frames_seen>before+3)
                controls.close();gate.set()
                pump(lambda:app.frames_seen>before+6)
                assert not any(s.name=='Stale result' for s in controls.cameras)
            app.open_scope();assert controls.refresh_button.get_sensitive()
            # A real HTTP/MJPEG server ending its response simulates link loss without
            # disconnecting the user's microscope or altering its recording state.
            image=Image.new('RGB',(80,48),'blue');jpeg=io.BytesIO();image.save(jpeg,format='JPEG');jpeg=jpeg.getvalue()
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*_):pass
                def do_GET(self):
                    self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace;boundary=test');self.end_headers()
                    self.wfile.write(b'--test\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(jpeg)).encode()+b'\r\n\r\n'+jpeg+b'\r\n--test--\r\n')
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                fake=Source('http://192.168.1.254:8192/','WLAN loss test','andonstar')
                with patch('tiny2.scope_window.sources',return_value=[fake]),patch('tiny2.network_preview.stream_url',return_value=f'http://127.0.0.1:{server.server_port}/'):
                    controls.refresh();pump(lambda:not controls.searching)
                    channel=controls.channels[fake.key]
                    controls.rows[channel.source.key]['enabled'].set_active(True)
                    pump(lambda:not controls.searching and channel.viewer is None,timeout=12)
                    assert 'beendet' in controls.status.get_text(),controls.status.get_text()
                    assert app.preview.pipeline
            finally:server.shutdown();server.server_close();worker.join(2)
            print('PASS: real WLAN 640×368 stream, pure-image 50% window, resize, stop/restart, responsive search, cancellation and HTTP stream loss; independent Tiny preview continued.',flush=True)
        finally:app.close();app.window.destroy()


if __name__=='__main__':main()
