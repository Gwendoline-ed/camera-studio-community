"""Persistent preview overlays; no camera I/O or changes to source frames."""
from .i18n import tr as _t
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import tempfile

DEFAULTS = {
    "text": {"enabled": False, "text": "Camera Studio Community", "x": 4, "y": 90, "size": 4, "opacity": 100},
    "clock": {"enabled": False, "seconds": True, "x": 96, "y": 4, "size": 3, "opacity": 100},
    "image": {"enabled": False, "path": "", "x": 4, "y": 4, "size": 18, "opacity": 100},
}


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError(_t('Ungültige Overlay-Einstellungen.'))
    result = deepcopy(DEFAULTS)
    for kind, defaults in DEFAULTS.items():
        layer = value[kind]
        if not isinstance(layer, dict) or set(layer) != set(defaults):
            raise ValueError(_t('Unvollständige Overlay-Einstellungen.'))
        for key, default in defaults.items():
            item = layer[key]
            if isinstance(default, bool):
                if not isinstance(item, bool): raise ValueError(_t('Ungültiger Overlay-Schalter.'))
            elif isinstance(default, str):
                if not isinstance(item, str) or "\0" in item or len(item) > (200 if key == "text" else 4096):
                    raise ValueError(_t('Ungültiger Overlay-Text oder Bildpfad.'))
            else:
                minimum, maximum = (1, 50) if key == "size" else (0, 100)
                if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or not minimum <= item <= maximum:
                    raise ValueError(_t('Ungültige Overlay-Größe, Position oder Deckkraft.'))
            result[kind][key] = item
    return result


def fitted_rect(width, height, source_width, source_height):
    if min(width, height, source_width, source_height) <= 0:
        return 0, 0, 0, 0
    scale = min(width / source_width, height / source_height)
    w, h = source_width * scale, source_height * scale
    return (width - w) / 2, (height - h) / 2, w, h


def positioned(rect, item_width, item_height, x, y):
    """Percent position along the available travel; 100 keeps the item inside."""
    left, top, width, height = rect
    return left + max(0, width - item_width) * x / 100, top + max(0, height - item_height) * y / 100


class OverlayStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "camera-studio-community"
        self.path = self.directory / "overlays.json"

    def load(self):
        if not self.path.exists(): return deepcopy(DEFAULTS)
        try:
            if self.path.stat().st_size > 16384: raise ValueError(_t('Datei ist zu groß.'))
            return validate(json.loads(self.path.read_text()))
        except (OSError, ValueError) as exc:
            raise ValueError(_t('Gespeicherte Overlays konnten nicht geladen werden. Die Datei bleibt erhalten.')) from exc

    def save(self, value):
        data = validate(value)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=".overlays-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)
