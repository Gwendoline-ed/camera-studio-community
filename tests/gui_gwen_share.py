"""Real GTK windows + synthetic camera/audio; no microphone or live camera access."""
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gst, Gio
from gui_integration import SyntheticCamera, pump
from tiny2.app import Studio


def capture(window, path):
    widget = window
    paintable = Gtk.WidgetPaintable.new(widget)
    nodes = []
    def rendered():
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, widget.get_width(), widget.get_height())
        node = snapshot.to_node()
        if node is not None: nodes.append(node)
        return bool(nodes)
    pump(rendered)
    texture = window.get_renderer().render_texture(nodes[-1], None)
    assert texture.save_to_png(str(path))


def main():
    root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
    camera = SyntheticCamera()
    with tempfile.TemporaryDirectory() as tmp, patch('tiny2.app.device.connect', return_value=camera):
        app = Studio(SimpleNamespace(config_dir=tmp, smoke_test=False, screenshot=None, device=None))
        app.register(None); app.activate(app)
        try:
            pump(lambda: app.controller is not None and not app.busy)
            app.preview.start(None, test=True); pump(lambda: app.frames_seen > 3)
            capture(app.window, root / 'Studio-Fenstertest.png')
            app.toggle_detached(); app.manual_button.set_active(True)
            pump(lambda: app.manual_ready)
            capture(app.detached_window, root / 'Manuell-Fenstertest.png')
            app.manual_drag_begin(app.drag_controller, 100, 100)
            app.manual_drag_update(None, 15, -10)
            pump(lambda: any(w[:2] == ('send', 0x6484) for w in camera.writes))
            app.end_manual_drag(); pump(lambda: not app.busy)
            assert camera.writes[-1][1] == 0x6704
            app.wheel_controller.emit('scroll', 0, -1); pump(lambda: not app.busy and app.wheel_zoom_timer is None)
            assert camera.state['zoom_percent'] == 5 and app.manual_enabled
            app.open_gwen(); chat = app.gwen_window
            pump(lambda: chat.get_realized() and chat.get_width() > 0)
            assert chat.frame is not None and chat.recorder.pipeline is None
            frame = chat.frame
            with patch('tiny2.gwen_window.GwenClient') as client:
                client.return_value.chat.return_value = {'answer': 'Testantwort: zwei vorgegebene Punkte.',
                    'markers': [{'label': 'Testpunkt 1', 'x': 250, 'y': 400}, {'label': 'Testpunkt 2', 'x': 750, 'y': 600}],
                    'note': 'Darstellungstest mit vorgegebenen Punkten.'}
                chat.entry.set_text('Markiere die Testpunkte.'); chat.send_button.emit('clicked')
                pump(lambda: not chat.busy)
                assert len(chat.markers.markers) == 2 and len(chat.history) == 2
                assert chat.frame[1] != frame[1]
                assert client.return_value.chat.call_args.args[1] == chat.frame[0]
            # Capture native render tree, not another application's desktop.
            pump(lambda: app.frames_seen > 8)
            capture(chat, root / 'Gwen-Fenstertest.png')
            chat.capture_image(); assert chat.markers.markers == []
            # Substitute a tone source only for this test, never opening autoaudiosrc.
            real_parse = Gst.parse_launch
            with (patch('tiny2.dictation.Gst.parse_launch', side_effect=lambda _: real_parse(
                    'audiotestsrc num-buffers=6 ! audioconvert ! audioresample ! '
                    'audio/x-raw,format=S16LE,rate=16000,channels=1 ! '
                    'appsink name=audio emit-signals=true max-buffers=8 drop=false sync=false')),
                 patch('tiny2.gwen_window.whisper_paths', return_value=('unused', 'unused')),
                 patch('tiny2.gwen_window.Transcriber') as transcriber):
                transcriber.return_value.transcribe.return_value = 'Dies ist ein Testdiktat.'
                chat.mic_button.emit('clicked')
                pump(lambda: chat.entry.get_text() == 'Dies ist ein Testdiktat.')
                assert chat.recorder.pipeline is None and len(chat.history) == 2
                assert len(transcriber.return_value.transcribe.call_args.args[0]) > 0
            chat.share_button.emit('clicked'); share = app.share_windows[-1]
            pump(lambda: share.get_realized() and share.get_width() > 0)
            assert share.png == chat.frame[0]
            share.copy(); assert 'kopiert' in share.status.get_text()
            capture(share, root / 'Bild-teilen-Fenstertest.png')
            with patch('tiny2.share_window.Gio.AppInfo.launch_default_for_uri') as launch:
                share.comic(); url = launch.call_args.args[0]
                assert url.startswith('http://127.0.0.1:')
            # Save uses the chosen native file path and exact frozen image.
            chosen = Path(tmp) / 'snapshot.png'
            chooser = SimpleNamespace(get_file=lambda: Gio.File.new_for_path(str(chosen)), destroy=lambda: None)
            share.saved(chooser, Gtk.ResponseType.ACCEPT)
            assert chosen.read_bytes() == share.png
            share.close(); assert not app.share_windows
            chat.close(); assert app.gwen_window is None
            app.open_gwen(); assert not app.gwen_window.history
            app.close(); assert not app.share_windows and app.cover_share is None
            print('PASS: real GTK manual mode, stop, wheel zoom, snapshot chat, markers, dictation insertion, clipboard, file save, cover handoff and cleanup.')
        finally: app.close(); app.window.destroy()


if __name__ == '__main__': main()
