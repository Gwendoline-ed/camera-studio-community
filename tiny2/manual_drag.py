"""Bounded relative mouse input; no absolute position is inferred."""
import math
import threading
import time

PULSE_SECONDS = .08
MAX_SPEED = 25
MAX_INPUT_AGE = .25


class ManualDrag:
    def __init__(self):
        self.active = False
        self.cancel = threading.Event()
        self.cancel.set()
        self.pending = None

    def begin(self, width, height):
        self.end()
        if not all(math.isfinite(v) and v > 0 for v in (width, height)):
            return False
        self.width, self.height = width, height
        self.previous = (0, 0)
        self.active = True
        self.cancel = threading.Event()
        return True

    def update(self, x, y, *, now=None):
        if not self.active or not all(math.isfinite(v) for v in (x, y)):
            return False
        now = time.monotonic() if now is None else now
        dx, dy = x - self.previous[0], y - self.previous[1]
        self.previous = (x, y)
        if dx == 0 and dy == 0:
            return False
        if self.pending and now - self.pending[2] <= MAX_INPUT_AGE:
            dx += self.pending[0]; dy += self.pending[1]
        self.pending = dx, dy, now
        return True

    def take(self, *, now=None):
        pending, self.pending = self.pending, None
        now = time.monotonic() if now is None else now
        if not self.active or pending is None or now - pending[2] > MAX_INPUT_AGE:
            return None
        dx, dy, _ = pending
        clamp = lambda value: min(MAX_SPEED, max(-MAX_SPEED, value))
        # Rightward mouse motion looks right; the protocol's positive yaw is left.
        pan = clamp(-dx * 60 / self.width / PULSE_SECONDS)
        tilt = clamp(-dy * 40 / self.height / PULSE_SECONDS)
        if abs(pan) < .1 and abs(tilt) < .1:
            return None
        return pan, tilt, self.cancel

    def end(self):
        self.cancel.set()
        self.active = False
        self.pending = None
