"""Explicit microphone recording, bounded RAM buffer and offline transcription."""
from .i18n import tr as _t
import json
import os
from pathlib import Path
import subprocess
import threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

MAX_PCM = 60 * 16000 * 2
from . import integrations


def whisper_paths(home=None):
    settings=integrations.load()
    if not settings['whisper_python'] or not settings['whisper_model']:
        raise RuntimeError(_t('Bitte Python und lokalen Whisper-Modellordner unter KI & Dienste eintragen.'))
    python=Path(settings['whisper_python']).expanduser();model=Path(settings['whisper_model']).expanduser()
    if not python.is_absolute() or not model.is_absolute() or not python.is_file() or not os.access(python,os.X_OK) or not all((model/name).is_file() for name in ('model.bin','config.json')):
        raise RuntimeError(_t('Python oder lokales Whisper-Modell nicht gefunden. Bitte KI & Dienste prüfen.'))
    return python,model


class Transcriber:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()

    def transcribe(self, pcm):
        if not pcm or len(pcm) > MAX_PCM or len(pcm) % 2:
            raise ValueError(_t('Keine gültige Tonaufnahme vorhanden.'))
        if self.cancelled.is_set(): raise InterruptedError(_t('Diktieren abgebrochen'))
        python, model = whisper_paths()
        guard=integrations.load()['memory_guard']
        if guard and not (Path(guard).expanduser()/'guard_common.py').is_file():
            raise RuntimeError(_t('Der eingestellte Speicherschutz wurde nicht gefunden.'))
        env = os.environ.copy(); env.update(HF_HUB_OFFLINE='1', OMP_NUM_THREADS='2', PYTHONDONTWRITEBYTECODE='1')
        with self.lock:
            if self.cancelled.is_set(): raise InterruptedError(_t('Diktieren abgebrochen'))
            process = subprocess.Popen([str(python), str(Path(__file__).with_name('speech_worker.py')),
                                        str(model), str(Path(guard).expanduser()) if guard else ''], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            self.process = process
        try:
            try: out, _err = process.communicate(pcm, timeout=120)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate()
                raise RuntimeError(_t('Die Spracherkennung hat zu lange gebraucht.'))
            if self.cancelled.is_set(): raise InterruptedError(_t('Diktieren abgebrochen'))
            if len(out) > 64000: raise ValueError(_t('Spracherkennung lieferte zu viel Text.'))
            try: result = json.loads(out)
            except ValueError: raise RuntimeError(_t('Die lokale Spracherkennung konnte nicht gestartet werden.'))
            if process.returncode or result.get('error'):
                raise RuntimeError(str(result.get('error', _t('Spracherkennung fehlgeschlagen')))[:800])
            if not isinstance(result.get('text'), str): raise ValueError(_t('Kein Diktattext erhalten.'))
            return result['text'][:4000]
        finally:
            with self.lock: self.process = None


class Recorder:
    def __init__(self, done, error):
        self.done, self.error = done, error
        self.pipeline = None
        self.lock = threading.Lock()
        self.data = bytearray()
        self.generation = 0
        self.limit_queued = False
        self.timer = None

    def start(self):
        self.stop(); self.data = bytearray(); self.limit_queued = False
        pipeline = Gst.parse_launch('autoaudiosrc ! audioconvert ! audioresample ! '
            'audio/x-raw,format=S16LE,rate=16000,channels=1 ! '
            'appsink name=audio emit-signals=true max-buffers=8 drop=false sync=false')
        self.pipeline = pipeline; generation = self.generation
        pipeline.get_by_name('audio').connect('new-sample', self.sample, generation)
        bus = pipeline.get_bus(); bus.add_signal_watch()
        bus.connect('message::error', self.failed, generation)
        bus.connect('message::eos', lambda *_: self.finish(generation))
        self.timer = GLib.timeout_add_seconds(60, self.finish, generation)
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.stop(); raise RuntimeError(_t('Das Mikrofon konnte nicht gestartet werden.'))

    def sample(self, sink, generation):
        sample = sink.emit('pull-sample')
        if sample is None: return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer(); ok, mapping = buffer.map(Gst.MapFlags.READ)
        if ok:
            try:
                with self.lock:
                    if generation != self.generation: return Gst.FlowReturn.OK
                    room = MAX_PCM - len(self.data)
                    self.data.extend(mapping.data[:room])
                    if len(self.data) == MAX_PCM and not self.limit_queued:
                        self.limit_queued = True; GLib.idle_add(self.finish, generation)
            finally: buffer.unmap(mapping)
        return Gst.FlowReturn.OK

    def failed(self, _bus, message, generation):
        if generation != self.generation: return
        error, _ = message.parse_error(); self.stop(); self.error(_t('Mikrofon: ') + str(error))

    def finish(self, generation=None):
        if self.pipeline is None or (generation is not None and generation != self.generation): return False
        data = self.stop(); self.done(data); return False

    def stop(self):
        with self.lock:
            self.generation += 1
            data = bytes(self.data); self.data.clear()
        if self.timer is not None:
            GLib.source_remove(self.timer); self.timer = None
        if self.pipeline is not None:
            pipeline, self.pipeline = self.pipeline, None
            pipeline.get_bus().remove_signal_watch(); pipeline.set_state(Gst.State.NULL)
        return data
