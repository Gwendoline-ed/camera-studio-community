"""Andonstar MJPEG live preview using the existing GStreamer display path."""
from .i18n import tr as _t
import time
from .andonstar import stream_url
from .preview import Preview


class NetworkPreview(Preview):
    def start_auto(self,address):
        self.stop()
        address=stream_url(address)
        self.last_frame=time.monotonic()
        self._play(f'souphttpsrc location="{address}" is-live=true timeout=5 automatic-redirect=false ! '
                   'multipartdemux single-stream=true ! jpegdec ! videoconvert ! '
                   'video/x-raw,format=RGB ! appsink name=frames emit-signals=true '
                   'max-buffers=1 drop=true sync=false')

    def _display(self,generation):
        if generation!=self.generation:return False
        with self.lock:
            if self.latest is not None:self.last_frame=time.monotonic()
        if time.monotonic()-self.last_frame>8:
            self.stop();self.on_error(_t('Kein WLAN-Livebild mehr. Verbindung zum Andonstar prüfen.'))
            return False
        return super()._display(generation)
