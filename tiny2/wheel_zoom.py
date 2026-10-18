"""Coalesce wheel input into bounded, absolute camera zoom requests."""
import math


class WheelZoom:
    STEP = 5

    def __init__(self):
        self.current = None
        self.pending = None
        self.inflight = None

    def observe(self, percent):
        self.current = (float(percent) if isinstance(percent, (int, float))
                        and not isinstance(percent, bool) and math.isfinite(percent)
                        and 0 <= percent <= 100 else None)

    def scroll(self, dy):
        if not math.isfinite(dy) or not dy:
            return False
        base = next((v for v in (self.pending, self.inflight, self.current)
                     if v is not None), None)
        if base is None:
            return False
        target = min(100, max(0, base - dy * self.STEP))
        if target == base:
            return False
        self.pending = target
        return True

    def take(self):
        if self.inflight is not None:
            return None
        self.inflight, self.pending = self.pending, None
        return self.inflight

    def complete(self, success):
        self.inflight = None
        if not success:
            self.clear(reset=True)

    def clear(self, *, reset=False):
        self.pending = None
        if reset:
            self.current = self.inflight = None
