"""Focus isolation: scope input must never issue Tiny PTZ commands."""
from types import SimpleNamespace
from unittest.mock import Mock,patch
from test_wheel_zoom import StudioFlowCase
from test_manual_drag import MotionCamera
from test_g13 import state,PROFILE
from gui_integration import pump


class ScopeInputTests(StudioFlowCase):
    def setUp(self):
        super().setUp();self.attach(MotionCamera())
        self.scope=SimpleNamespace(ready=lambda:True,zoom_by=Mock(),zoom_label=lambda:'Bildzoom 1.2×',
            source=SimpleNamespace(backend='andonstar',name='Andonstar'),open_gwen=Mock(),share=Mock(),
            reset_zoom=Mock(),toggle_fullscreen=Mock(),show=Mock(),chat=None)
        self.target=self.scope
        self.app.scope_controls=SimpleNamespace(focused_channel=lambda:self.target,
            channels={'scope':self.scope},is_active=lambda:True)
        self.current=state()
        self.app.g13.client=SimpleNamespace(latest=lambda:(self.current,''),close=lambda:None)
        self.app.g13.enabled=True;self.app.g13.tick();self.camera.writes.clear()

    def tearDown(self):
        self.camera.release.set();self.app.g13.disable();super().tearDown()

    def press(self,keys):self.current=state(keys=keys);self.app.g13.tick();self.finish()

    def test_zoom_and_actions_route_to_scope(self):
        self.press(['G3']);self.scope.zoom_by.assert_called_once_with(1)
        self.press([]);self.press(['G12']);self.scope.open_gwen.assert_called_once()
        self.press([]);self.press(['G13']);self.scope.share.assert_called_once()
        self.press([]);self.press(['G4']);self.scope.reset_zoom.assert_called_once()
        self.assertEqual(self.camera.writes,[])

    def test_stick_presets_tracking_book_and_stop_do_not_touch_tiny(self):
        self.current=state(stick=(255,0));self.app.g13.tick();self.finish()
        for key in ['G5','G8','G9','G16','G17','G1']:
            self.press([]);self.press([key])
        self.assertFalse(self.app.g13.active);self.assertEqual(self.camera.writes,[])

    def test_focus_switch_while_zoom_held_requires_release(self):
        second=SimpleNamespace(**vars(self.scope));second.zoom_by=Mock()
        self.press(['G3']);self.target=second;self.app.g13.last_zoom=0
        self.press(['G3']);second.zoom_by.assert_not_called()
        self.press([]);self.press(['G3']);second.zoom_by.assert_called_once_with(1)
        self.assertEqual(self.camera.writes,[])

    def test_scope_input_does_not_depend_on_tiny_camera(self):
        self.app.controller=None;self.app.preview.pipeline=None
        self.press(['G3']);self.scope.zoom_by.assert_called_once_with(1)

    def test_stale_scope_disables_actions(self):
        self.scope.ready=lambda:False
        self.press(['G3']);self.press([]);self.press(['G13'])
        self.scope.zoom_by.assert_not_called();self.scope.share.assert_not_called()
        self.assertEqual(self.camera.writes,[])

    def test_chat_share_uses_edited_standstill(self):
        self.scope.chat=SimpleNamespace(is_active=lambda:True,share_image=Mock())
        self.press(['G13']);self.scope.chat.share_image.assert_called_once()
        self.scope.share.assert_not_called();self.assertEqual(self.camera.writes,[])

    def test_enable_from_scope_needs_no_tiny_and_does_not_switch_tiny_tracking(self):
        self.app.g13.disable();self.app.controller=None;self.app.preview.pipeline=None
        with patch('tiny2.g13_control.request',return_value={'profile':PROFILE}),patch('tiny2.g13_control.Subscription') as sub:
            self.app.g13.enable();pump(lambda:not self.app.busy)
            self.assertTrue(self.app.g13.enabled);sub.return_value.start.assert_called_once()
            self.assertEqual(self.camera.writes,[])
