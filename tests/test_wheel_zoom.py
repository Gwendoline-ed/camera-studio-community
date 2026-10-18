"""Real zoom controller/worker flow with a fake camera and no desktop window."""
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

from tiny2.app import Studio
from tiny2.controller import Controller
from tiny2.wheel_zoom import WheelZoom
from gui_integration import SyntheticCamera, pump


class DisplayValue:
    def __init__(self): self.text = ''; self.value = 0
    def set_value(self, value): self.value = value
    def get_value(self): return self.value
    def set_text(self, text): self.text = text
    def set_label(self, text): self.text = text
    def set_sensitive(self, value): pass
    def set_visible(self, value): pass
    def remove_css_class(self, value): pass
    def add_css_class(self, value): pass


class DelayedCamera(SyntheticCamera):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.fail = False

    def set_control(self, key, value):
        self.entered.set()
        if not self.release.wait(3):
            raise TimeoutError('Synthetic test did not release camera')
        if self.fail:
            raise TimeoutError('Synthetic zoom confirmation failed')
        return super().set_control(key, value)


class WheelZoomTests(unittest.TestCase):
    def test_range_direction_and_invalid_values(self):
        zoom = WheelZoom()
        self.assertFalse(zoom.scroll(-1))
        for value in (None, True, -1, 101, float('nan'), float('inf')):
            zoom.observe(value)
            self.assertFalse(zoom.scroll(-1))
        zoom.observe(95)
        self.assertTrue(zoom.scroll(-20))
        self.assertEqual(zoom.pending, 100)
        self.assertFalse(zoom.scroll(-1))
        self.assertTrue(zoom.scroll(30))
        self.assertEqual(zoom.pending, 0)
        self.assertFalse(zoom.scroll(float('nan')))


class StudioFlowCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Studio(SimpleNamespace(config_dir=self.temp.name, smoke_test=False, device=None))
        for name in ('zoom', 'zoom_state', 'mode_state', 'detail_state', 'notice',
                     'connect_button', 'stop_button', 'connection', 'preview_button',
                     'empty', 'detached_zoom_state', 'resolution'):
            setattr(self.app, name, DisplayValue())
        self.app.resolution.observed_label = DisplayValue()
        self.app.detached_window = object()
        # No GStreamer pipeline is opened; only the running-preview guard is exercised.
        self.app.preview = SimpleNamespace(pipeline=object(), stop=lambda: None)
        self.camera = SyntheticCamera()
        self.attach(self.camera)

    def attach(self, camera):
        self.camera = camera
        self.camera.state['zoom_percent'] = 40
        self.app.camera = camera
        self.app.controller = Controller(camera)
        self.app.update_state(camera.status())

    def tearDown(self):
        if isinstance(self.camera, DelayedCamera): self.camera.release.set()
        self.app.disable_manual()
        self.app.cancel_wheel_zoom(reset=True)
        self.app.closed = True
        self.app.executor.shutdown(wait=True, cancel_futures=True)
        pump(lambda: True)
        self.temp.cleanup()

    def wheel(self, dy):
        return self.app.scroll_camera_zoom(None, 0, dy)

    def finish(self):
        pump(lambda: not self.app.busy and self.app.wheel_zoom_timer is None)

    def zoom_writes(self):
        return [w[2] for w in self.camera.writes if w[:2] == ('control', 'zoom')]


class WheelFlowTests(StudioFlowCase):
    def test_burst_uses_camera_state_not_unsent_slider_and_coalesces(self):
        self.app.zoom.set_value(90)
        for _ in range(4): self.assertTrue(self.wheel(-1))
        self.assertEqual(self.camera.writes, [])
        self.assertEqual(self.app.zoom.value, 60)
        self.finish()
        self.assertEqual(self.zoom_writes(), [60])
        self.assertIn('60 %', self.app.detached_zoom_state.text)
        self.assertNotIn('→', self.app.detached_zoom_state.text)
        self.wheel(3); self.finish()
        self.assertEqual(self.zoom_writes(), [60, 45])

    def test_new_input_during_pending_usb_keeps_latest_target(self):
        camera = DelayedCamera(); self.attach(camera)
        self.wheel(-1)
        pump(camera.entered.is_set)
        self.wheel(-1); self.wheel(-1)
        self.assertEqual(self.app.wheel_zoom.pending, 55)
        camera.release.set(); self.finish()
        self.assertEqual(self.zoom_writes(), [45, 55])
        self.assertEqual(camera.state['zoom_percent'], 55)

    def test_waits_for_other_camera_work(self):
        self.app.busy = True
        self.wheel(-2)
        deadline = time.monotonic() + .18
        pump(lambda: time.monotonic() >= deadline)
        self.assertEqual(self.camera.writes, [])
        self.app.busy = False; self.finish()
        self.assertEqual(self.zoom_writes(), [50])

    def test_error_discards_later_zoom_and_requires_fresh_readback(self):
        camera = DelayedCamera(); camera.fail = True; self.attach(camera)
        self.wheel(-1); pump(camera.entered.is_set)
        self.wheel(-3)
        camera.release.set(); self.finish()
        self.assertIsNone(self.app.wheel_zoom.pending)
        self.assertIsNone(self.app.wheel_zoom.current)
        self.assertIn('failed', self.app.notice.text)
        self.wheel(-1)
        self.assertIsNone(self.app.wheel_zoom_timer)

    def test_stop_cancels_unsent_zoom(self):
        self.wheel(-3)
        self.app.stop(); self.finish()
        self.assertEqual(self.zoom_writes(), [])
        self.assertEqual([w[1] for w in self.camera.writes if w[0] == 'send'], [0x6484, 0x6704])

    def test_stop_during_usb_cancels_followup_and_runs_stop_next(self):
        camera = DelayedCamera(); self.attach(camera)
        self.wheel(-1); pump(camera.entered.is_set)
        self.wheel(-3)
        self.app.stop()
        self.assertTrue(self.app.stop_pending)
        self.assertIsNone(self.app.wheel_zoom.pending)
        camera.release.set(); self.finish()
        self.assertFalse(self.app.stop_pending)
        self.assertEqual(self.zoom_writes(), [45])
        self.assertEqual([w[1] for w in camera.writes if w[0] == 'send'], [0x6484, 0x6704])

    def test_cancel_dock_pause_and_missing_camera_never_write(self):
        self.wheel(-2); self.app.cancel_wheel_zoom(); self.finish()
        self.app.detached_window = None
        self.assertFalse(self.wheel(-1))
        self.app.resolution.observed_label = DisplayValue()
        self.app.detached_window = object()
        self.app.preview.pipeline = None
        self.wheel(-1)
        self.app.preview.pipeline = object(); self.app.controller = None
        self.wheel(-1)
        self.assertEqual(self.camera.writes, [])
        self.assertIsNone(self.app.wheel_zoom_timer)

    def test_sleep_or_unknown_zoom_does_not_guess(self):
        self.camera.state['awake'] = False
        self.app.update_state(self.camera.status())
        self.wheel(-1)
        self.assertEqual(self.camera.writes, [])
        self.assertIsNone(self.app.wheel_zoom_timer)


if __name__ == '__main__': unittest.main()
