"""Read the existing g13d subscription, without opening any keyboard device."""
from .i18n import tr as _t
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import socket
import threading
import time

PROFILE_ID = 'profile-2'
PROFILE_NAME = 'Tiny 2 Studio'
MAX_AGE = .3
DEAD_ZONE = 28
STOP_KEYS = {'G1', 'G22', 'TOP'}
ACTION_KEYS = {
    'G4': 'center', 'G5': 'position1', 'G6': 'position2', 'G7': 'position3',
    'G8': 'tracking_off', 'G9': 'tracking_hand', 'G10': 'tracking_normal',
    'G11': 'detach', 'G12': 'gwen', 'G13': 'share', 'G14': 'fullscreen',
    'G16': 'book_capture', 'G17': 'book_accept',
}


def socket_path():
    return Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'g13d.sock'


def request(message, path=None):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2); client.connect(str(path or socket_path()))
        client.sendall((json.dumps(message) + '\n').encode())
        with client.makefile('rb') as stream: raw = stream.readline(65537)
    if not raw.endswith(b'\n') or len(raw) > 65536: raise ValueError(_t('Ungültige G13-Antwort.'))
    result = json.loads(raw)
    if not isinstance(result, dict): raise ValueError(_t('Ungültige G13-Antwort.'))
    if result.get('error'): raise RuntimeError('G13: ' + str(result['error'])[:300])
    return result


def verify_profile(profile):
    if (not isinstance(profile, dict) or profile.get('id') != PROFILE_ID
            or profile.get('name') != PROFILE_NAME or profile.get('slot') != 2
            or profile.get('bindings') != {} or profile.get('macros') != {}
            or profile.get('shortcuts', {}) != {} or profile.get('stick_mode') != 'keys'):
        raise ValueError(_t('Bitte das eingerichtete M2-Profil „Tiny 2 Studio“ ohne Tastaturbelegungen verwenden.'))


@dataclass(frozen=True)
class State:
    profile_id: str
    profile: str
    stick: tuple
    keys: frozenset
    mr_state: str
    received: float

    @classmethod
    def parse(cls, data, now=None):
        stick, keys = data.get('stick'), data.get('keys')
        if (data.get('kind') != 'state' or not isinstance(stick, list) or len(stick) != 2
                or not all(type(v) is int and 0 <= v <= 255 for v in stick)
                or not isinstance(keys, list) or len(keys) > 64
                or not all(isinstance(v, str) and len(v) <= 32 for v in keys)
                or not all(isinstance(data.get(k), str) for k in ('profile_id', 'profile', 'mr_state'))):
            raise ValueError(_t('Ungültiger G13-Eingabestatus.'))
        return cls(data['profile_id'], data['profile'], tuple(stick), frozenset(keys),
                   data['mr_state'], time.monotonic() if now is None else now)


class Subscription:
    def __init__(self, path=None):
        self.path = path or socket_path()
        self.lock = threading.Lock()
        self.state = None
        self.error = _t('Verbindung zum G13-Treiber wird hergestellt …')
        self.closed = threading.Event()
        self.connection = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, name='tiny2-g13', daemon=True)
        self.thread.start()

    def latest(self):
        with self.lock: return self.state, self.error

    def run(self):
        while not self.closed.is_set():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                    with self.lock: self.connection = connection
                    connection.settimeout(.5); connection.connect(str(self.path))
                    if self.closed.is_set(): break
                    connection.sendall(b'{"cmd":"subscribe"}\n')
                    pending = bytearray()
                    while not self.closed.is_set():
                        data = connection.recv(4096)
                        if not data: raise ConnectionError(_t('G13 getrennt'))
                        pending.extend(data)
                        if len(pending) > 65536: raise ValueError(_t('G13-Antwort zu groß'))
                        while b'\n' in pending:
                            line, _, rest = pending.partition(b'\n'); pending = bytearray(rest)
                            value = json.loads(line)
                            if not isinstance(value, dict): raise ValueError(_t('G13-Antwort ungültig'))
                            state = State.parse(value)
                            with self.lock: self.state, self.error = state, ''
            except (OSError, ValueError, TypeError):
                with self.lock:
                    self.state = None
                    self.error = _t('G13-Verbindung unterbrochen. Auf den Treiber warten …')
            finally:
                with self.lock: self.connection = None
            self.closed.wait(1)

    def close(self):
        self.closed.set()
        with self.lock:
            connection = self.connection
            self.state = None
        if connection is not None:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            connection.close()


class Input:
    """Centre-before-arming gate, edge-triggered actions and bounded stick speed."""
    def __init__(self):
        self.center = (128, 128)
        self.speed = 15
        self.armed = False
        self.previous = frozenset()
        self.release = threading.Event(); self.release.set()

    def suspend(self):
        self.release.set(); self.armed = False

    def stop_motion(self): self.release.set()

    def evaluate(self, state, focused, now=None):
        now = time.monotonic() if now is None else now
        empty = dict(motion=None, actions=[], zoom=0, note='')
        reason = ''
        if state is None or now - state.received > MAX_AGE: reason = _t('G13 wartet auf aktuelle Eingaben.')
        elif state.profile_id != PROFILE_ID or state.profile != PROFILE_NAME: reason = _t('An der G13 M2 wählen.')
        elif state.mr_state != 'idle': reason = _t('Makroaufnahme beenden: MR drücken.')
        elif not focused: reason = _t('Zum Steuern Haupt- oder Kamerafenster aktivieren.')
        if reason:
            self.suspend(); self.previous = state.keys if state else frozenset()
            return {**empty, 'note': reason}
        keys = state.keys
        controls = keys & (set(ACTION_KEYS) | STOP_KEYS | {'G2', 'G3', 'G15'})
        pressed = keys - self.previous; self.previous = keys
        if keys & STOP_KEYS:
            self.suspend()
            return {**empty, 'actions': ['stop'] if pressed & STOP_KEYS else [], 'note': _t('Stop')}
        if not self.armed:
            # Recalibrate only inside a generous neutral region, never at full deflection.
            if not controls and all(abs(v - 128) <= DEAD_ZONE for v in state.stick):
                self.center = state.stick; self.armed = True
            return {**empty, 'note': _t('Bereit · Stick steuert die Kamera.') if self.armed
                    else _t('Stick loslassen und Tasten freigeben.')}
        actions = [name for key, name in ACTION_KEYS.items() if key in pressed]
        zoom = int('G3' in keys) - int('G2' in keys)
        if actions or keys & {'G2', 'G3'}:
            self.stop_motion()
            return {**empty, 'actions': actions, 'zoom': zoom, 'note': _t('G13 aktiv')}
        axes = []
        for value, center in zip(state.stick, self.center):
            delta = value - center
            extent = 255 - center if delta >= 0 else center
            amount = max(0, abs(delta) - DEAD_ZONE) / max(1, extent - DEAD_ZONE)
            axes.append(math.copysign(min(1, amount), delta))
        length = max(1, math.hypot(*axes))
        speed = min(25, max(2, self.speed)) * (.3 if 'G15' in keys else 1)
        pan, tilt = (-v * speed / length for v in axes)
        if abs(pan) < .1 and abs(tilt) < .1:
            self.stop_motion(); return {**empty, 'note': _t('Bereit · G15 halten für feine Bewegungen.')}
        if self.release.is_set(): self.release = threading.Event()
        return {**empty, 'motion': (pan, tilt, self.release), 'note': _t('Kamera wird mit der G13 bewegt.')}
