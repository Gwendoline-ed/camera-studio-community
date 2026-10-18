"""Real GTK and GStreamer; camera enumeration / USB controls are synthetic."""
from fractions import Fraction
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from gui_integration import SyntheticCamera, pump
from gui_gwen_share import capture
from tiny2.app import Studio
from tiny2.camera_profiles import Registry
from tiny2.scope_window import Source
from tiny2.preview import Preview
from tiny2.video_modes import Catalog,VideoMode,SizeRange


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=True)
    camera=SyntheticCamera();camera.candidate.path='/dev/video80'
    mode=VideoMode(853,479,'MJPG',Fraction(30000,1001))
    modes=Catalog([mode,VideoMode(1024,768,'YUYV',Fraction(25))],
                  [SizeRange('YUYV',320,1920,16,240,1080,8)])
    sources=[Source('/dev/video81','USB-Kamera A',modes=modes),Source('/dev/video82','USB-Kamera B',modes=modes)]
    original_start=Preview.start
    def synthetic_start(self,device,resolution='1280x720',test=False,*,mode=None):
        original_start(self,None,resolution,test=True,mode=mode)
    with tempfile.TemporaryDirectory() as tmp,patch('tiny2.app.device.connect',return_value=camera),\
         patch('tiny2.app.video_modes.available',return_value=modes),\
         patch('tiny2.scope_window.sources',return_value=sources),patch.object(Preview,'start',synthetic_start):
        app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None));app.register(None);app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            assert not camera.writes
            assert app.get_application_id()=='io.local.CameraStudioCommunity'
            app.resolution.dropdown.set_selected(1);app.toggle_preview();pump(lambda:app.frames_seen>3)
            assert (app.last_frame[0].get_width(),app.last_frame[0].get_height())==(853,479)
            assert app.preview.negotiated[2]=='29.97'
            app.toggle_preview();app.resolution.dropdown.set_selected(3)
            app.resolution.width.set_value(848);app.resolution.height.set_value(480)
            app.toggle_preview();pump(lambda:app.last_frame[0].get_width()==848)
            app.open_scope();controls=app.scope_controls;pump(lambda:not controls.searching)
            assert 'tiny2' in controls.registry.enabled and not controls.registry.active('amcam')
            first=controls.profile_box.get_first_child();assert first.get_active() and not first.get_sensitive()
            profile=Path(tmp)/'camera.json';profile.write_text(json.dumps({'version':1,'id':'example-cam','name':'Beispiel-Kamera','backend':'v4l2','usb':{'vendor':'1234','product':'abcd'}}))
            controls.registry.install(profile);controls.render_profiles();assert 'example-cam' in Registry(tmp).enabled
            a,b=[controls.channels[s.key] for s in sources]
            controls.rows[a.source.key]['picker'].dropdown.set_selected(1)
            controls.rows[a.source.key]['enabled'].set_active(True);pump(a.ready)
            controls.rows[b.source.key]['picker'].dropdown.set_selected(2)
            controls.rows[b.source.key]['enabled'].set_active(True);pump(b.ready)
            assert a.snapshot().get_width()==853 and b.snapshot().get_width()==1024
            assert a.viewer is not b.viewer and app.preview.pipeline
            controls.refresh();pump(lambda:not controls.searching)
            assert a.ready() and b.ready() and a.mode==mode
            controls.registry.enable('usb-video',False)
            assert a.ready() and b.ready(),'Profile changes must not stop live sessions'
            a.viewer.close();pump(lambda:a.viewer is None);assert b.ready() and app.preview.pipeline
            controls.registry.enable('usb-video',True)
            controls.render_profiles();controls.profiles_expander.set_expanded(True)
            capture(app.window,root/'Community-Fenstertest.png')
            capture(controls,root/'Community-Profile-Fenstertest.png')
            assert not camera.writes,'Other cameras must not receive or trigger Tiny-2 motion'
            app.open_integrations()
            window=next(w for w in app.get_windows() if w.get_title()=='KI & Zusatzdienste · Community')
            capture(window,root/'Community-Zusatzdienste-Fenstertest.png');window.close()
            # Dialog is transient, the app still has its independent configuration.
            print('PASS: separate app identity; enumerated formats; 853×479 at 30000/1001; custom 848×480; two concurrent independent cameras; fixed Tiny 2; imported profile persisted; no device writes.')
        finally:
            app.close();app.window.destroy()


if __name__=='__main__':main()
