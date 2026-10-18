"""GStreamer preview. Does not record or write camera images to disk."""
from .i18n import tr as _t
import threading
import re
import gi
gi.require_version("Gst", "1.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gst, GLib, Gdk

Gst.init(None)


class Preview:
    def __init__(self, on_frame, on_error):
        self.on_frame, self.on_error = on_frame, on_error
        self.pipeline = None
        self.generation = 0
        self.latest = None
        self.lock = threading.Lock()
        self.timer = None
        self.negotiated = None

    def start(self, device, resolution="1280x720", test=False, *, mode=None):
        """Use driver negotiation by default; explicit caps come from enumeration."""
        self.stop()
        from .video_modes import VideoMode, valid_size
        if mode is not None and not isinstance(mode,VideoMode):
            raise ValueError(_t('Ungültiger Kameramodus.'))
        if test:
            width,height=(mode.width,mode.height) if mode else map(int,resolution.split('x'))
            if not valid_size(width,height):raise ValueError(_t('Ungültige Testbildgröße.'))
            source=f'videotestsrc is-live=true pattern=ball ! video/x-raw,width={width},height={height}'
            if mode and mode.fps:source+=f',framerate={mode.fps.numerator}/{mode.fps.denominator}'
            source+=' ! '
        else:
            if not re.fullmatch(r'/dev/video[0-9]+',str(device)):
                raise ValueError(_t('Bitte ein gültiges Kameragerät auswählen.'))
            source=f'v4l2src device="{device}" ! '
            if mode:source+=mode.caps+' ! '
            source+='decodebin ! '
        self._play(source+'videoconvert ! video/x-raw,format=RGB ! '
                   'appsink name=frames emit-signals=true max-buffers=1 drop=true sync=false')

    def start_auto(self, device, test=False, *, mode=None):
        self.start(device, resolution="640x480", test=test, mode=mode)

    def _play(self, description):
        pipeline = Gst.parse_launch(description)
        self.pipeline = pipeline
        generation = self.generation
        sink = pipeline.get_by_name("frames")
        sink.connect("new-sample", self._sample, generation)
        bus = pipeline.get_bus(); bus.add_signal_watch()
        bus.connect("message::error", self._error, generation)
        bus.connect("message::eos", self._eos, generation)
        self.timer = GLib.timeout_add(67, self._display, generation)
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.stop(); raise RuntimeError(_t('Vorschau konnte nicht gestartet werden'))

    def _sample(self, sink, generation):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        caps = sample.get_caps().get_structure(0)
        width, height = caps.get_value("width"), caps.get_value("height")
        has_rate, numerator, denominator = caps.get_fraction("framerate")
        rate = f"{numerator / denominator:g}" if has_rate and denominator else ""
        buffer = sample.get_buffer()
        ok, mapping = buffer.map(Gst.MapFlags.READ)
        if ok:
            try:
                # GStreamer RGB rows are aligned to a 4-byte boundary.
                stride = ((width * 3 + 3) // 4) * 4
                data = bytes(mapping.data)
                if len(data) >= stride * height:
                    with self.lock:
                        if generation == self.generation:
                            self.negotiated = (width,height,rate)
                            self.latest = (width, height, stride, data)
            finally:
                buffer.unmap(mapping)
        return Gst.FlowReturn.OK

    def _display(self, generation):
        if generation != self.generation:
            return False
        with self.lock:
            sample, self.latest = self.latest, None
        if sample:
            width, height, stride, data = sample
            texture = Gdk.MemoryTexture.new(width, height, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(data), stride)
            self.on_frame(texture)
        return True

    def _error(self, bus, message, generation):
        if generation != self.generation: return
        error, _ = message.parse_error()
        self.stop(); self.on_error(str(error))

    def _eos(self, bus, message, generation):
        if generation != self.generation: return
        self.stop(); self.on_error(_t('Die Vorschau wurde beendet'))

    def stop(self):
        self.generation += 1
        if self.timer:
            GLib.source_remove(self.timer); self.timer = None
        self.negotiated = None
        if self.pipeline:
            self.pipeline.get_bus().remove_signal_watch()
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        with self.lock:
            self.latest = None
