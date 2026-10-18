"""Desktop integration test with synthetic video, never real camera I/O.

Run from the application directory: PYTHONPATH=. python3 tests/gui_overlays.py
"""
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import cairo
from gui_integration import SyntheticCamera, pump
from tiny2.app import Studio
from tiny2.overlays import OverlayStore


def main():
    camera = SyntheticCamera()
    with tempfile.TemporaryDirectory() as tmp, patch('tiny2.app.device.connect', return_value=camera):
        args = SimpleNamespace(config_dir=tmp, smoke_test=False, screenshot=None, device=None)
        app = Studio(args); app.register(None); app.activate(app)
        try:
            pump(lambda: app.controller is not None and not app.busy)
            app.preview.start(None, test=True)
            pump(lambda: app.frames_seen > 2)
            pipeline, generation = app.preview.pipeline, app.preview.generation
            app.stack.set_visible_child_name('overlays')
            app.text_toggle.set_active(True); app.overlay_text.set_text('Live · Werkbank')
            app.clock_toggle.set_active(True)
            logo = Path(tmp) / 'Logo mit Leerzeichen.png'
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 80, 40)
            cr = cairo.Context(surface); cr.set_source_rgba(0, .8, .4, .7); cr.paint()
            surface.write_to_png(str(logo)); app.set_overlay_image(str(logo))
            app.overlay_spins['size'].set_value(21)
            app.overlay_spins['opacity'].set_value(66)
            assert app.overlay_settings['image']['size'] == 21
            assert app.overlay_settings['image']['opacity'] == 66
            app.save_overlays()
            assert OverlayStore(tmp).load() == app.overlay_settings
            for _ in range(3):
                previous = app.frames_seen
                app.detach_button.emit('clicked')
                pump(lambda: app.detached_window is not None and app.frames_seen > previous + 2)
                window = app.detached_window
                assert window.get_child() is app.overlay
                assert app.overlay_view.settings is app.overlay_settings
                assert app.wheel_controller.get_widget() is app.overlay
                previous_zoom = camera.state['zoom_percent']
                assert app.wheel_controller.emit('scroll', 0, -1)
                pump(lambda: not app.busy and app.wheel_zoom_timer is None)
                assert camera.state['zoom_percent'] == previous_zoom + 5
                assert 'Mausrad' in app.detached_zoom_state.get_text()
                window.set_default_size(420, 740)
                assert app.preview.pipeline is pipeline and app.preview.generation == generation
                app.wheel_controller.emit('scroll', 0, -1)
                window.close()
                pump(lambda: app.detached_window is None)
                assert app.wheel_zoom_timer is None and app.wheel_zoom.pending is None
                assert not app.wheel_controller.emit('scroll', 0, -1)
                assert app.overlay.get_parent() is app.preview_slot
                assert app.preview.pipeline is pipeline and app.preview.generation == generation
            app.clear_overlay_image()
            assert app.overlay_view.image is None and not app.image_toggle.get_active()
            app.toggle_detached()
            assert app.detached_window is not None
            app.window.close()
            pump(lambda: app.closed)
            assert app.detached_window is None and app.preview.pipeline is None
            assert app.overlay_view.timer is None
            assert camera.writes == [('control', 'zoom', value) for value in (5, 10, 15)], camera.writes
            print('PASS: overlays, image loading, persistence, wheel zoom, 3 detach/dock cycles, stream continuity, shutdown.')
        finally:
            app.close(); app.window.destroy()


if __name__ == '__main__': main()
