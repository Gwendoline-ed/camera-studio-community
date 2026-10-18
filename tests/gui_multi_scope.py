"""Two concurrent microscope streams, source-bound actions and Andonstar input.
The AmScope SDK is synthetic; Andonstar uses the connected real WLAN camera.
No image or prompt is actually sent to Gwen in this test.
"""
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from gui_integration import SyntheticCamera,pump
from gui_gwen_share import capture
from test_g13 import state
from tiny2.app import Studio


def png(texture):return bytes(texture.save_to_png_bytes().get_data())


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=True)
    camera=SyntheticCamera()
    with tempfile.TemporaryDirectory() as tmp,patch('tiny2.app.device.connect',return_value=camera),patch.dict(os.environ,{'TINY2_AMCAM_LIBRARY':str(root/'libfake_amcam.so')}):
        app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None));app.register(None);app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            app.preview.start(None,test=True);pump(lambda:app.frames_seen>3)
            app.open_scope();controls=app.scope_controls;pump(lambda:not controls.searching)
            am=next(c for c in controls.channels.values() if c.source.backend=='amcam' and c.source.available)
            wifi=next(c for c in controls.channels.values() if c.source.backend=='andonstar')
            def start(channel):
                controls.rows[channel.source.key]['enabled'].set_active(True)
                pump(lambda:not controls.searching and channel.ready(),timeout=15)
                return channel.viewer
            mu=start(am);ad=start(wifi)
            before=(mu.frames_seen,ad.frames_seen,app.frames_seen)
            pump(lambda:mu.frames_seen>before[0]+3 and ad.frames_seen>before[1]+3 and app.frames_seen>before[2]+3)
            assert mu is not ad and mu.preview is not ad.preview
            assert png(am.snapshot())!=png(wifi.snapshot())
            controls.present();capture(controls,root/'Scopes-parallel.png')
            controls.refresh();pump(lambda:not controls.searching)
            assert am.viewer is mu and wifi.viewer is ad
            controls.start_selected(am,controls.cameras,'');assert am.viewer is mu
            controls.close();assert mu.get_visible() and ad.get_visible()
            for channel in (am,wifi):
                controls.rows[channel.source.key]['gwen'].emit('clicked');chat=channel.chat
                pump(lambda:chat.get_realized())
                assert chat.scope is channel and channel.source.name in chat.get_title()
                assert chat.capture_image() and chat.frame[0]==png(channel.snapshot())
                chat.fresh_image.set_active(False)
                with patch('tiny2.gwen_window.GwenClient') as client:
                    client.return_value.chat.return_value={'answer':channel.source.name,'markers':[],'note':''}
                    chat.entry.set_text('Prüfe die Quelle');chat.send();pump(lambda:not chat.busy)
                    assert client.return_value.chat.call_args.args[1]==chat.frame[0]
                controls.rows[channel.source.key]['share'].emit('clicked');share=app.share_windows[-1]
                assert share.png==png(channel.snapshot()) and share.source_name==channel.source.name
                frozen=share.png
                controls.rows[channel.source.key]['draw'].emit('clicked');drawing=app.drawing_windows[-1]
                assert drawing.original==png(channel.snapshot())
                drawing.ink.begin(10,10,(1,0,0,1),10);drawing.ink.add(150,100);drawing.ink.end()
                expected=png(drawing.result());drawing.apply()
                assert channel.chat.frame[0]==expected and not channel.chat.fresh_image.get_active()
                assert share.png==frozen;share.close()
            assert am.chat is not wifi.chat and am.chat.frame[0]!=wifi.chat.frame[0]
            assert app.gwen_window is None
            capture(wifi.chat,root/'Andonstar-Gwen.png')
            # Wheel acts on just the Andonstar crop; sending and sharing use that crop.
            ad.present();pump(lambda:ad.is_active());camera.writes.clear()
            width=wifi.snapshot().get_width();ad.wheel_controller.emit('scroll',0,-1)
            assert wifi.zoom>1 and wifi.snapshot().get_width()<width and am.zoom==1
            ad.wheel_controller.emit('scroll',0,1);assert abs(wifi.zoom-1)<1e-8
            wifi.chat.present();pump(lambda:wifi.chat.is_active())
            wifi.chat.wheel_controller.emit('scroll',0,-2)
            assert wifi.chat.live_button.get_active() and wifi.chat.picture.get_paintable()==ad.picture.get_paintable()
            wifi.chat.capture_image();assert wifi.chat.frame[0]==png(wifi.snapshot())
            before=wifi.zoom
            current=[state()];app.g13.client=SimpleNamespace(latest=lambda:(current[0],''),close=lambda:None)
            app.g13.enabled=True;app.g13.tick()
            current[0]=state(keys=['G3']);app.g13.tick()
            assert wifi.zoom>before and wifi.chat.live_button.get_active()
            blocked=wifi.zoom;ad.wheel_controller.emit('scroll',0,-1);wifi.chat.wheel_controller.emit('scroll',0,-1)
            assert wifi.zoom==blocked
            current[0]=state();app.g13.tick();current[0]=state(keys=['G4']);app.g13.tick();assert wifi.zoom==1
            assert camera.writes==[],camera.writes
            app.g13.disable()
            for _ in range(60):wifi.zoom_by(1)
            assert wifi.zoom==6
            wifi.reset_zoom();assert wifi.zoom==1
            # Old frames cannot silently be reused as a fresh capture.
            ad.frame_time=time.monotonic()-3
            try:wifi.snapshot();raise AssertionError('stale snapshot accepted')
            except ValueError:pass
            pump(wifi.ready)
            before=ad.frames_seen;process=mu.preview.process
            mu.failed('USB-Test getrennt');pump(lambda:process.poll() is not None and ad.frames_seen>before)
            assert am.viewer is None and wifi.viewer is ad and app.preview.pipeline
            assert not am.chat.capture_image()
            replacement=start(am);assert replacement is not mu
            assert am.chat.capture_image() and am.chat.frame[0]==png(am.snapshot())
            process=replacement.preview.process;old_chats=(am.chat,wifi.chat)
            app.close();pump(lambda:process.poll() is not None)
            assert all(c.closed for c in old_chats) and ad.preview.pipeline is None and app.scope_controls is None
            print('PASS: simultaneous synthetic MU300 SDK + real Andonstar WLAN + Tiny test preview; per-source chats/share/drawing, wheel/G13 crop zoom, focus isolation, refresh, stale capture, disconnect/restart and cleanup.',flush=True)
        finally:app.close();app.window.destroy()

if __name__=='__main__':main()
