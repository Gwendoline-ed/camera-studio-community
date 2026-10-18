"""Real SDK identity lookup and synthetic SDK end-to-end stream in native GTK."""
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from gui_integration import SyntheticCamera,pump
from gui_gwen_share import capture
from tiny2.app import Studio
from tiny2.amcam_preview import AmcamPreview


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=True)
    camera=SyntheticCamera()
    with tempfile.TemporaryDirectory() as tmp,patch('tiny2.app.device.connect',return_value=camera):
        from tiny2.camera_profiles import Registry
        Registry(tmp).enable("amscope",True)
        app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None));app.register(None);app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            app.preview.start(None,test=True);pump(lambda:app.frames_seen>3)
            app.open_scope();controls=app.scope_controls
            pump(lambda:controls.get_realized() and controls.get_width()>0 and not controls.searching)
            if any(s.name=='AmScope MU300' for s in controls.cameras):
                capture(controls,root/'MU300-erkannt.png')
                print('REAL IDENTITY: installed AmScope SDK identified MU300 through USB sysfs; live USB unavailable in test environment.',flush=True)
            with patch.dict(os.environ,{'TINY2_AMCAM_LIBRARY':str(root/'libfake_amcam.so')}):
                controls.refresh();pump(lambda:not controls.searching);assert controls.cameras[0].available
                channel=next(c for c in controls.channels.values() if c.source.backend=='amcam' and c.source.available)
                controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching);scope=channel.viewer
                assert isinstance(scope.preview,AmcamPreview)
                pump(lambda:scope.picture.get_paintable() is not None,timeout=10)
                process=scope.preview.process
                png=bytes(scope.picture.get_paintable().save_to_png_bytes().get_data())
                im=Image.open(io.BytesIO(png))
                assert im.size==(512,384) and im.getpixel((0,0))[:3]==(240,40,30)
                assert im.getpixel((511,383))[:3]==(20,180,230),'RGB order or orientation'
                assert not scope.get_decorated() and scope.get_child()==scope.picture
                capture(scope,root/'MU300-SDK-Testbild.png')
                before=app.frames_seen;scope.close();pump(lambda:process.poll() is not None and app.frames_seen>before)
                assert not controls.rows[channel.source.key]['enabled'].get_active() and channel.viewer is None
                # Rapid start/stop must ignore callbacks from a previous worker.
                controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching);old=channel.viewer.preview.process;channel.viewer.close()
                controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching);current=channel.viewer
                pump(lambda:current.picture.get_paintable() is not None and old.poll() is not None,timeout=10)
                assert channel.viewer is current;current.close()
                for scenario,expected in [('busy','AmLite'),('start-error','fehlgeschlagen'),('disconnect','getrennt')]:
                    with patch.dict(os.environ,{'TINY2_FAKE_AMCAM_SCENARIO':scenario}):
                        controls.rows[channel.source.key]['enabled'].set_active(True)
                        pump(lambda:not controls.searching and channel.viewer is None,timeout=10)
                        assert expected in controls.status.get_text(),controls.status.get_text()
                        assert app.preview.pipeline
                controls.refresh();pump(lambda:not controls.searching)
                controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching);scope=channel.viewer
                pump(lambda:scope.picture.get_paintable() is not None,timeout=10)
                process=scope.preview.process;app.close();pump(lambda:process.poll() is not None)
                assert app.scope_controls is None
            print('PASS: proprietary camera selection, isolated RGB stream/color/orientation, stop/restart, occupied camera, start failure, disconnect, independent Tiny stream and app shutdown.')
        finally:app.close();app.window.destroy()


if __name__=='__main__':main()
