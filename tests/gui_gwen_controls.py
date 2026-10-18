"""Real GTK camera controls in Gwen, including frozen answer alignment."""
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
from gui_integration import SyntheticCamera, pump
from gui_gwen_share import capture
from test_g13 import state, PROFILE
from tiny2.app import Studio


def main():
    root=Path(sys.argv[1]); root.mkdir(parents=True,exist_ok=True)
    camera=SyntheticCamera()
    with tempfile.TemporaryDirectory() as tmp, patch('tiny2.app.device.connect',return_value=camera):
        app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None))
        app.register(None); app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            app.preview.start(None,test=True); pump(lambda:app.frames_seen>3)
            app.open_gwen(); chat=app.gwen_window
            pump(lambda:chat.get_realized() and chat.get_width()>0)
            assert app.detached_window is None
            chat.manual_button.set_active(True); pump(lambda:app.manual_ready)
            chat.drag_controller.emit('drag-begin',100,100)
            chat.drag_controller.emit('drag-update',20,-10)
            pump(lambda:any(w[:2]==('send',0x6484) for w in camera.writes))
            chat.drag_controller.emit('drag-end',20,-10); pump(lambda:not app.busy)
            assert camera.writes[-1][1]==0x6704
            chat.wheel_controller.emit('scroll',0,-1)
            pump(lambda:not app.busy and app.wheel_zoom_timer is None)
            assert camera.state['zoom_percent']==5 and chat.live_button.get_active()
            capture(chat,root/'Gwen-Maussteuerung.png')
            finish=threading.Event()
            with patch('tiny2.gwen_window.GwenClient') as client:
                def reply(*_):
                    assert finish.wait(3)
                    return dict(answer='Testmarkierung am Standbild.',markers=[dict(label='Pin 1',x=250,y=400)],note='Testbild')
                client.return_value.chat.side_effect=reply
                chat.entry.set_text('Testfrage'); chat.send()
                assert not chat.live_button.get_active()
                frame=chat.frame; frozen=chat.frame_texture
                chat.wheel_controller.emit('scroll',0,-1)
                pump(lambda:not app.busy and app.wheel_zoom_timer is None)
                finish.set(); pump(lambda:not chat.busy)
                assert chat.frame==frame and chat.live_button.get_active()
                assert not chat.markers.get_visible() and len(chat.markers.markers)==1
                chat.live_button.set_active(False)
                assert chat.picture.get_paintable()==frozen and chat.markers.get_visible()
            current=[state()]
            with (patch('tiny2.g13_control.request',side_effect=[{'profile':PROFILE},{'ok':True}]),
                  patch('tiny2.g13_control.Subscription') as sub,
                  patch.object(app.g13,'focused',return_value=True)):
                sub.return_value.latest.side_effect=lambda:(current[0],'')
                chat.g13_button.set_active(True); pump(lambda:app.g13.enabled and not app.busy)
                current[0]=state(); app.g13.tick()
                assert not chat.manual_button.get_sensitive() and not app.manual_enabled
                before=list(camera.writes)
                chat.wheel_controller.emit('scroll',0,-1)
                chat.drag_controller.emit('drag-begin',100,100)
                chat.drag_controller.emit('drag-update',20,-10)
                assert camera.writes==before and not app.manual_drag.active
                current[0]=state(keys=['G3']); app.g13.tick()
                current[0]=state(); pump(lambda:not app.busy)
                assert camera.state['zoom_percent']==15
                capture(chat,root/'Gwen-G13-Steuerung.png')
                chat.camera_stop_button.emit('clicked'); pump(lambda:not app.busy)
                assert not app.g13.active and chat.manual_button.get_sensitive()
                assert camera.writes[-1][1]==0x6704
            chat.wheel_controller.emit('scroll',0,-1)
            chat.close(); pump(lambda:app.gwen_window is None and not app.busy)
            assert camera.state['zoom_percent']==15 and len(app.g13.buttons)==1
            print('PASS: Gwen mouse movement, camera wheel zoom, frozen answer during live movement, G13 exclusive control, Stop and close cleanup.')
        finally: app.close(); app.window.destroy()


if __name__=='__main__': main()
