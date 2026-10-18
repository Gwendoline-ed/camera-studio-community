"""Real GTK controls with synthetic camera and G13 input; no device movement."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from gui_integration import SyntheticCamera, pump
from gui_gwen_share import capture
from tiny2.app import Studio
from tiny2.g13_input import State, PROFILE_ID, PROFILE_NAME


def main():
    root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
    camera = SyntheticCamera()
    profile = dict(id=PROFILE_ID, name=PROFILE_NAME, slot=2, bindings={}, macros={}, stick_mode='keys')
    with tempfile.TemporaryDirectory() as tmp, patch('tiny2.app.device.connect', return_value=camera):
        app = Studio(SimpleNamespace(config_dir=tmp, smoke_test=False, screenshot=None, device=None, tab='g13'))
        app.register(None); app.activate(app)
        try:
            pump(lambda: app.controller is not None and not app.busy)
            assert app.stack.get_visible_child_name() == 'g13'
            app.preview.start(None, test=True); pump(lambda: app.frames_seen > 3)
            app.toggle_detached(); app.manual_button.set_active(True)
            pump(lambda: app.manual_ready)
            with (patch('tiny2.g13_control.request', side_effect=[{'profile':profile}, {'ok':True}]),
                  patch('tiny2.g13_control.Subscription') as subscription):
                subscription.return_value.latest.side_effect = lambda: (State.parse(dict(kind='state',
                    profile_id=PROFILE_ID, profile=PROFILE_NAME, stick=[147,127], keys=[], mr_state='idle')), '')
                app.detached_g13_button.set_active(True)
                pump(lambda: app.g13.enabled and not app.busy)
                assert not app.manual_enabled and not app.manual_button.get_sensitive()
                assert all(button.get_active() for button, _ in app.g13.buttons)
                assert 'Maus aus' in app.detached_zoom_state.get_text()
                before = list(camera.writes)
                app.wheel_controller.emit('scroll', 0, -1)
                app.manual_drag_begin(app.drag_controller, 100, 100)
                app.manual_drag_update(None, 40, 0)
                assert camera.writes == before and app.wheel_zoom_timer is None
                assert not app.manual_drag.active
                capture(app.window, root / 'G13-Steuerung.png')
                capture(app.detached_window, root / 'G13-Maus-aus.png')
                app.detached_g13_button.set_active(False)
                assert app.manual_button.get_sensitive()
                app.wheel_controller.emit('scroll', 0, -1)
                pump(lambda: not app.busy and app.wheel_zoom_timer is None)
                assert camera.state['zoom_percent'] == 5
                assert all(not button.get_active() for button, _ in app.g13.buttons)
                app.dock_preview()
                assert len(app.g13.buttons) == 1
            print('PASS: G13 tab, synchronized buttons, manual cancellation, mouse/wheel lock, wheel restoration, dock cleanup.')
        finally: app.close(); app.window.destroy()


if __name__ == '__main__': main()
