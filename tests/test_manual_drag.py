"""Mouse motion, zoom arbitration and final Stop using the real serial worker."""
import struct
import threading
import time
from types import SimpleNamespace
import unittest
from tiny2.manual_drag import ManualDrag, MAX_SPEED
from tiny2.controller import Controller
from tiny2.app import Gtk
from gui_integration import SyntheticCamera, pump
from test_wheel_zoom import StudioFlowCase, DisplayValue


class Toggle(DisplayValue):
    def __init__(self): super().__init__(); self.active = False
    def get_active(self): return self.active
    def set_active(self, value): self.active = value


class MouseGesture:
    def set_state(self, state): self.state = state


class MotionCamera(SyntheticCamera):
    def __init__(self):
        super().__init__()
        self.moving = threading.Event()
        self.release = threading.Event(); self.release.set()
        self.fail_motion = self.fail_zero = False

    def send(self, command, receiver, payload=b'', **kwargs):
        super().send(command, receiver, payload, **kwargs)
        if command == 0x6484 and payload != bytes(12):
            self.moving.set()
            if not self.release.wait(3): raise TimeoutError('Test did not release send')
            if self.fail_motion: raise OSError('Synthetic motion failure')
        if command == 0x6484 and payload == bytes(12) and self.fail_zero:
            raise OSError('Synthetic zero-velocity failure')

    def close(self):
        self.writes.append(('close',))
        super().close()


class ManualInputTests(unittest.TestCase):
    def test_relative_direction_accumulation_and_speed_cap(self):
        drag = ManualDrag(); self.assertTrue(drag.begin(600, 400))
        drag.update(5, -4, now=1); drag.update(10, -8, now=1.01)
        pan, tilt, _ = drag.take(now=1.02)
        self.assertAlmostEqual(pan, -12.5)
        self.assertAlmostEqual(tilt, 10)
        drag.update(1000, -1000, now=1.03)
        pan, tilt, _ = drag.take(now=1.04)
        self.assertEqual((pan, tilt), (-MAX_SPEED, MAX_SPEED))

    def test_stale_input_and_old_gesture_cannot_restart_motion(self):
        drag = ManualDrag(); drag.begin(600, 400)
        drag.update(20, 20, now=1)
        self.assertIsNone(drag.take(now=2))
        old_release = drag.cancel
        drag.end(); self.assertTrue(old_release.is_set())
        self.assertFalse(drag.update(30, 30))
        drag.begin(600, 400)
        self.assertTrue(old_release.is_set())
        self.assertFalse(drag.cancel.is_set())
        self.assertIsNone(drag.take())
        self.assertFalse(drag.update(float('nan'), 10))

    def test_invalid_speed_never_writes_and_released_step_is_noop(self):
        camera = MotionCamera(); camera.state['mode'] = 'Aus'
        controller = Controller(camera); released = threading.Event()
        for pan, tilt in ((26, 0), (0, -26), (float('nan'), 0)):
            with self.assertRaises(ValueError): controller.manual_step(pan, tilt, released)
        released.set(); controller.manual_step(10, 10, released)
        self.assertEqual(camera.writes, [])

    def test_stop_command_still_sent_if_zero_velocity_fails(self):
        camera = MotionCamera(); camera.state['mode'] = 'Aus'; camera.fail_zero = True
        with self.assertRaises(OSError): Controller(camera).manual_step(1, 1, threading.Event())
        self.assertEqual(camera.writes[-1][1], 0x6704)


class ManualFlowTests(StudioFlowCase):
    def setUp(self):
        super().setUp()
        self.attach(MotionCamera())
        self.app.manual_button = Toggle()
        self.app.manual_hint = DisplayValue()
        self.app.overlay = SimpleNamespace(get_width=lambda: 600, get_height=lambda: 400,
                                            set_cursor_from_name=lambda _: None)
        self.gesture = MouseGesture()

    def tearDown(self):
        self.camera.release.set()
        super().tearDown()

    def enable(self):
        self.app.manual_button.set_active(True)
        self.app.toggle_manual(self.app.manual_button)
        pump(lambda: not self.app.busy)
        self.assertTrue(self.app.manual_ready)

    def drag(self, x=10, y=-8):
        self.app.manual_drag_begin(self.gesture, 100, 100)
        self.assertEqual(self.gesture.state, Gtk.EventSequenceState.CLAIMED)
        self.app.manual_drag_update(self.gesture, x, y)

    def finish_motion(self):
        pump(lambda: not self.app.busy and self.app.manual_timer is None and self.app.wheel_zoom_timer is None)

    def motion_writes(self):
        return [w for w in self.camera.writes if w[0] == 'send']

    def test_mode_off_has_no_motion_and_activation_only_disables_tracking(self):
        self.app.manual_drag_begin(self.gesture, 10, 10)
        self.assertEqual(self.gesture.state, Gtk.EventSequenceState.DENIED)
        self.assertEqual(self.camera.writes, [])
        self.camera.state['mode'] = 'Hand'
        self.enable()
        self.assertEqual(self.camera.writes, [('raw', 0x16, b'\0\0')])

    def test_motion_is_relative_then_stops_without_absolute_jump(self):
        self.enable(); self.drag(); self.finish_motion()
        events = self.motion_writes()
        self.assertEqual([w[1] for w in events], [0x6484, 0x6484, 0x6704])
        self.assertEqual(struct.unpack('<fff', events[0][3]), (0, -10, -12.5))
        self.assertEqual(events[1][3], bytes(12))
        self.assertTrue(self.app.manual_ready)

    def test_release_cancels_unsent_input(self):
        self.enable(); self.drag(); self.app.end_manual_drag(); self.finish_motion()
        self.assertEqual(self.motion_writes(), [])
        self.assertTrue(self.app.manual_drag.cancel.is_set())

    def test_focus_loss_ends_gesture_and_discards_input(self):
        self.enable(); self.drag()
        self.app.manual_focus_changed(SimpleNamespace(is_active=lambda: False), None)
        self.finish_motion()
        self.assertFalse(self.app.manual_drag.active)
        self.assertEqual(self.motion_writes(), [])

    def test_wheel_zoom_works_while_manual_mode_stays_enabled(self):
        self.enable(); self.drag(); self.wheel(-1); self.finish_motion()
        self.assertEqual(self.zoom_writes(), [45])
        self.assertTrue(self.app.manual_ready)
        zoom_index = next(i for i, w in enumerate(self.camera.writes) if w[0] == 'control')
        motion_index = next(i for i, w in enumerate(self.camera.writes) if w[0] == 'send')
        self.assertLess(zoom_index, motion_index)
        self.assertEqual(self.camera.writes[-1][1], 0x6704)

    def test_old_mouse_input_not_replayed_after_busy_camera(self):
        self.enable()
        self.app.manual_drag.begin(600, 400)
        self.app.manual_drag.update(30, 30, now=time.monotonic() - 1)
        self.app.flush_manual_drag(); self.finish_motion()
        self.assertEqual(self.motion_writes(), [])

    def test_external_tracking_switch_leaves_manual_mode(self):
        self.enable(); self.drag()
        self.camera.state['mode'] = 'Normal'
        self.app.update_state(self.camera.status()); self.finish_motion()
        self.assertFalse(self.app.manual_enabled)
        self.assertEqual(self.motion_writes(), [])

    def test_motion_error_still_sends_stop_and_exits_manual_mode(self):
        self.enable(); self.camera.fail_motion = True
        self.drag(); self.finish_motion()
        self.assertEqual([w[1] for w in self.motion_writes()], [0x6484, 0x6484, 0x6704])
        self.assertFalse(self.app.manual_enabled)
        self.assertIn('Synthetic motion failure', self.app.notice.text)

    def test_window_close_finishes_stop_before_camera_descriptor_closes(self):
        self.enable(); self.camera.release.clear(); self.drag()
        pump(self.camera.moving.is_set)
        self.app.overlay_view = SimpleNamespace(stop=lambda: None)
        self.app.detached_window = SimpleNamespace(destroy=lambda: None)
        self.app.close()
        self.assertTrue(self.app.manual_drag.cancel.is_set())
        self.assertFalse(self.camera.closed)
        self.camera.release.set()
        self.app.executor.shutdown(wait=True)
        self.assertEqual(self.camera.writes[-3:], [('send', 0x6484, 4, bytes(12)),
                                                ('send', 0x6704, 4, b''), ('close',)])
        self.assertTrue(self.camera.closed)


if __name__ == '__main__': unittest.main()
