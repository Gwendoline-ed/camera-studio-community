"""Operations with explicit postconditions; no motion on connect/startup."""
from .i18n import tr as _t
from dataclasses import dataclass
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import time
from . import protocol as P
from .manual_drag import MAX_SPEED, PULSE_SECONDS


@dataclass
class Result:
    message: str
    confirmed: bool = False
    snapshot: dict | None = None


class Controller:
    def __init__(self, camera):
        self.camera = camera
        self.cancel = threading.Event()

    def verify(self, predicate, timeout=2.5):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            if self.cancel.is_set():
                raise InterruptedError(_t('Vorgang für Stop abgebrochen'))
            last = self.camera.status()
            if predicate(last):
                return last
            time.sleep(0.1)
        raise TimeoutError(_t('Befehl übertragen, Änderung von der Kamera noch nicht bestätigt'))

    def power(self, awake):
        self.camera.send(0xA0C2, 2, struct.pack("<I", 0 if awake else 1))
        state = self.verify(lambda s: s["awake"] == awake, timeout=4)
        return Result(_t('Kamera wach') if awake else _t('Kamera im Ruhemodus'), True, state)

    def ensure_awake(self):
        if not self.camera.status()["awake"]:
            self.power(True)

    def mode(self, name):
        if name not in P.MODES:
            raise ValueError(_t('Unbekannter Tracking-Modus'))
        self.ensure_awake()
        self.camera.raw_write(0x16, bytes(P.MODES[name]))
        state = self.verify(lambda s: s["awake"] and s["mode"] == name)
        return Result(_t('Tracking: {v0} – bestätigt', v0=_t(name)), True, state)

    def speed(self, name):
        value = {"Standard": 0, "Sport": 2}[name]
        self.ensure_awake()
        # Tiny2 uses aiSetTrackingModeR (0x0cc4), not generic speed-type 0x0944.
        self.camera.send(0x0CC4, 4, bytes([value]))
        state = self.verify(lambda s: s["awake"] and s["speed"] == name)
        return Result(_t('Verfolgungstempo: {v0} – bestätigt', v0=_t(name)), True, state)

    def move(self, pan, tilt):
        payload = P.angle_payload(pan, tilt)  # Validate before any device write.
        self.ensure_awake()
        self.mode("Aus")
        if self.cancel.is_set():
            raise InterruptedError(_t('Bewegung für Stop abgebrochen'))
        self.camera.send(0x6444, 4, payload)
        return Result(_t('Ziel gesendet: {v0:.1f}° / {v1:.1f}°. Ankunft noch nicht bestätigt.', v0=pan, v1=tilt))

    def stop(self):
        self.cancel.clear()
        # No wake operation on Stop. Clear AI ownership, then zero velocity and stop.
        errors = []
        for operation in [lambda: self.camera.raw_write(0x16, b"\0\0"),
                          lambda: self.camera.send(0x6484, 4, bytes(12)),
                          lambda: self.camera.send(0x6704, 4)]:
            try:
                operation()
            except OSError as error:
                errors.append(str(error))
        if errors:
            raise OSError(_t('Stop konnte nicht vollständig übertragen werden: ') + "; ".join(errors))
        return Result(_t('Stop gesendet. Stillstand bitte im Bild prüfen.'))

    def zoom(self, percent):
        percent = P.finite_range(percent, 0, 100, _t('Zoom'))
        self.ensure_awake()
        info = self.camera.control_info("zoom")
        value = info["min"] + (info["max"] - info["min"]) * percent / 100
        self.camera.set_control("zoom", value)
        # XU status is device readback, unlike V4L2's cached G_CTRL.
        state = self.verify(lambda s: s["awake"] and s["zoom_percent"] is not None
                            and abs(s["zoom_percent"] - percent) <= 2, timeout=5)
        return Result(_t('Zoom von der Kamera bestätigt'), True, state)

    def manual_step(self, pan_speed, tilt_speed, released):
        """Short velocity pulse, always followed by zero velocity and Stop.

        Each step starts at the physical pose, avoiding stale absolute targets.
        All I/O, including the final stop, stays on the serial camera worker.
        """
        pan_speed = P.finite_range(pan_speed, -MAX_SPEED, MAX_SPEED, _t('Schwenktempo'))
        tilt_speed = P.finite_range(tilt_speed, -MAX_SPEED, MAX_SPEED, _t('Neigetempo'))
        cancelled = lambda: released.is_set() or self.cancel.is_set()
        if cancelled():
            return Result(_t('Mausbewegung beendet'))
        state = self.camera.status()
        if not state['awake'] or state['mode'] != 'Aus':
            raise RuntimeError(_t('Maussteuerung beendet: Kamera schläft oder Tracking ist wieder aktiv.'))
        if cancelled():
            return Result(_t('Mausbewegung beendet'))
        try:
            self.camera.send(0x6484, 4, struct.pack('<fff', 0, -tilt_speed, pan_speed))
            # Mouse release wakes the worker immediately, independently of GTK timers.
            released.wait(PULSE_SECONDS)
        finally:
            errors = []
            for operation in (lambda: self.camera.send(0x6484, 4, bytes(12)),
                              lambda: self.camera.send(0x6704, 4)):
                try: operation()
                except Exception as error: errors.append(str(error))
            if errors:
                raise OSError(_t('Mausbewegung: Stop konnte nicht vollständig gesendet werden: ') + '; '.join(errors))
        return Result(_t('Mausbewegung und Stop gesendet; Position nicht gemessen.'), snapshot=state)

    def fov(self, name):
        value = {"Weit": 0, "Mittel": 1, "Eng": 2}[name]
        self.ensure_awake(); self.camera.raw_write(4, bytes([value]))
        state = self.verify(lambda s: s["awake"] and s["fov"] == name)
        return Result(_t('Bildausschnitt: {v0} – bestätigt', v0=_t(name)), True, state)

    def hdr(self, enabled):
        self.ensure_awake(); self.camera.raw_write(1, bytes([int(enabled)]))
        state = self.verify(lambda s: s["awake"] and s["hdr"] == enabled)
        return Result(_t('HDR-Einstellung bestätigt'), True, state)

    def image_control(self, key, value):
        self.ensure_awake()
        actual = self.camera.set_control(key, value)
        return Result(_t('Bildwert an den Treiber übergeben: {v0}', v0=actual))

    def diagnostic_angles(self):
        data = self.camera.send(0x0043, 3, read=True)
        if len(data) != 32:
            raise P.ProtocolError(_t('Gimbal-Antwort: unerwartete Länge {v0}', v0=len(data)))
        # Corresponds exactly to libdev's v3 attitude decoder; axis calibration unverified.
        values = tuple(v / 100 for v in struct.unpack_from("<hhh", data, 6))
        return {"sdk_angles": values, "axis_mapping_verified": False, "payload_hex": data.hex()}


class Presets:
    """User-selected targets stored locally, never claimed as measured positions."""
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(os.environ.get(
            "XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "camera-studio-community"
        self.path = self.directory / "presets.json"

    def load(self):
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise ValueError(_t('Ungültige Datei mit gespeicherten Positionen'))
        return data

    def save(self, slot, pan, tilt, zoom):
        if slot not in (1, 2, 3):
            raise ValueError(_t('Ungültiger Speicherplatz'))
        P.angle_payload(pan, tilt); P.finite_range(zoom, 0, 100, _t('Zoom'))
        data = self.load()
        data[str(slot)] = dict(pan=pan, tilt=tilt, zoom=zoom)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".presets-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def get(self, slot):
        data = self.load().get(str(slot))
        if data is None:
            raise ValueError(_t('Dieser Speicherplatz ist noch leer'))
        P.angle_payload(data["pan"], data["tilt"])
        P.finite_range(data["zoom"], 0, 100, _t('Zoom'))
        return data
