"""Shared camera input from Gwen without a detached preview window."""
from types import SimpleNamespace
from unittest.mock import patch
from test_wheel_zoom import StudioFlowCase, DisplayValue
from test_manual_drag import MotionCamera, MouseGesture, Toggle
from test_g13 import state
from gui_integration import pump


class GwenControlsTests(StudioFlowCase):
    def setUp(self):
        super().setUp(); self.attach(MotionCamera())
        self.app.detached_window = None
        self.chat = SimpleNamespace(closed=False, is_active=lambda: True,
            manual_button=Toggle(), live_button=Toggle(), camera_stop_button=DisplayValue(),
            camera_zoom_state=DisplayValue(), overlay=SimpleNamespace(
                get_width=lambda:600, get_height=lambda:400, set_cursor_from_name=lambda _:None))
        self.app.gwen_window = self.chat
        self.gesture = MouseGesture()

    def tearDown(self):
        self.camera.release.set(); self.app.g13.disable(); super().tearDown()

    def enable_mouse(self):
        self.chat.manual_button.set_active(True)
        self.app.toggle_manual(self.chat.manual_button, surface='gwen')
        pump(lambda:not self.app.busy)
        self.assertTrue(self.app.manual_ready)
        self.camera.writes.clear()  # Tracking-off is expected during activation.

    def test_gwen_mouse_drives_relative_camera_and_wheel_without_detached_window(self):
        self.enable_mouse()
        self.app.manual_drag_begin(self.gesture,100,100,surface='gwen')
        self.app.manual_drag_update(self.gesture,12,-8)
        pump(lambda:bool(self.camera.writes) and not self.app.busy and self.app.manual_timer is None)
        self.assertEqual([w[1] for w in self.camera.writes if w[0]=='send'],[0x6484,0x6484,0x6704])
        self.assertTrue(self.chat.live_button.get_active())
        self.app.scroll_camera_zoom(None,0,-1,surface='gwen'); self.finish()
        self.assertEqual(self.zoom_writes(),[45])
        self.assertIn('45 %',self.chat.camera_zoom_state.text)

    def test_g13_blocks_both_gwen_mouse_inputs(self):
        self.enable_mouse(); self.app.g13.enabled=True; self.app.g13.refresh()
        self.app.manual_drag_begin(self.gesture,100,100,surface='gwen')
        self.app.manual_drag_update(self.gesture,30,30)
        self.app.scroll_camera_zoom(None,0,-1,surface='gwen'); self.finish()
        self.assertEqual(self.camera.writes,[])
        self.assertIn('Maus aus',self.chat.camera_zoom_state.text)

    def test_chat_close_cancels_pending_zoom_and_drag(self):
        self.enable_mouse()
        self.app.manual_drag_begin(self.gesture,0,0,surface='gwen')
        self.app.manual_drag_update(self.gesture,10,10)
        self.app.scroll_camera_zoom(None,0,-1,surface='gwen')
        self.app.gwen_closed(); self.finish()
        self.assertFalse(self.app.manual_enabled)
        self.assertTrue(self.app.manual_drag.cancel.is_set())
        self.assertEqual(self.camera.writes,[])

    def test_chat_focus_loss_discards_queued_zoom_and_motion(self):
        self.enable_mouse()
        self.app.manual_drag_begin(self.gesture,0,0,surface='gwen')
        self.app.manual_drag_update(self.gesture,10,10)
        self.app.scroll_camera_zoom(None,0,-1,surface='gwen')
        self.chat.is_active=lambda:False
        self.app.manual_focus_changed(self.chat,None); self.finish()
        self.assertEqual(self.camera.writes,[])

    def test_g13_works_with_only_chat_focused_and_pauses_on_focus_loss(self):
        self.app.window=SimpleNamespace(is_active=lambda:False)
        self.assertTrue(self.app.g13.focused())
        current=[state()]
        self.app.g13.client=SimpleNamespace(latest=lambda:(current[0],''),close=lambda:None)
        self.app.g13.enabled=True; self.app.g13.tick()
        current[0]=state(keys=['G3']); self.app.g13.tick(); self.finish()
        self.assertEqual(self.zoom_writes(),[45])
        self.assertTrue(self.chat.live_button.get_active())
        self.chat.is_active=lambda:False
        self.app.g13.focus_changed()
        self.assertFalse(self.app.g13.focused())
        self.assertTrue(self.app.g13.input.release.is_set())
        self.app.g13.tick(); self.assertEqual(self.zoom_writes(),[45])

    def test_manual_mode_is_mirrored_between_camera_and_chat(self):
        self.app.manual_button=Toggle()
        self.enable_mouse(); self.assertTrue(self.app.manual_button.get_active())
        self.app.disable_manual()
        self.assertFalse(self.chat.manual_button.get_active())
        self.assertFalse(self.app.manual_button.get_active())
