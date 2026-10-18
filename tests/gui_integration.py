"""Run against a synthetic camera. Never opens a real USB/video device."""
import errno
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import GLib
from tiny2.app import Studio
from tiny2.protocol import MODES


class SyntheticCamera:
    def __init__(self):
        self.candidate=SimpleNamespace(path='/dev/synthetic-camera')
        self.state=dict(awake=True,mode='Aus',speed='Standard',hdr=False,fov='Weit',zoom_percent=0)
        self.writes=[];self.unsettled=False;self.gone=False;self.closed=False
    def close(self):self.closed=True
    def status(self):
        if self.gone:raise OSError(errno.ENODEV,'Synthetic camera disconnected')
        return dict(self.state)
    def control_info(self,key):return dict(min=0,max=100,step=1,default=0,writable=True,flags=0)
    def get_control(self,key):return 0
    def set_control(self,key,value):
        self.writes.append(('control',key,value))
        if key=='zoom':self.state['zoom_percent']=round(value)
        return round(value)
    def raw_write(self,tag,data):
        self.writes.append(('raw',tag,data))
        if tag==0x16 and not self.unsettled:self.state['mode']=next(k for k,v in MODES.items() if v==tuple(data))
    def send(self,command,receiver,payload=b'',**kwargs):
        self.writes.append(('send',command,receiver,payload))


def pump(predicate,timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if predicate():return
        time.sleep(.01)
    raise AssertionError('UI condition timed out')


def main():
    camera=SyntheticCamera()
    with tempfile.TemporaryDirectory() as temp,patch('tiny2.app.device.connect',return_value=camera):
        args=SimpleNamespace(config_dir=temp,smoke_test=False,screenshot=None,device=None)
        app=Studio(args);app.register(None);app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            assert not camera.writes,'Startup changed camera state'
            assert app.move_button.get_sensitive()
            next(w for w in app.actions if w.get_label()=='Nahansicht').emit('clicked')
            pump(lambda:not app.busy)
            assert camera.state['mode']=='Nahansicht'
            assert 'Nahansicht' in app.mode_state.get_text()
            app.pan.set_value(12);app.tilt.set_value(7);app.move_button.emit('clicked')
            pump(lambda:not app.busy)
            assert camera.state['mode']=='Aus'
            assert camera.writes[-1][1]==0x6444
            assert 'nicht bestätigt' in app.notice.get_text()
            app.zoom.set_value(35);app.apply_zoom();pump(lambda:not app.busy)
            assert camera.state['zoom_percent']==35
            app.save_preset(2);app.pan.set_value(0);app.recall(2);pump(lambda:not app.busy)
            assert app.pan.get_value()==12
            assert (Path(temp)/'presets.json').exists()
            camera.unsettled=True
            next(w for w in app.actions if w.get_label()=='Normal').emit('clicked')
            assert app.busy and app.stop_button.get_sensitive()
            app.stop_button.emit('clicked')
            pump(lambda:not app.busy and not app.stop_pending)
            assert [e[1] for e in camera.writes if e[0]=='send'][-2:]==[0x6484,0x6704]
            camera.gone=True;app.poll();pump(lambda:app.controller is None and not app.busy)
            assert not app.move_button.get_sensitive()
            assert app.connection.get_text()=='Verbindung getrennt'
            print('PASS: UI startup is read-only; tracking, move, zoom, local presets, busy-stop and disconnect recovery.')
        finally:
            app.close();app.window.destroy()


if __name__=='__main__':main()
