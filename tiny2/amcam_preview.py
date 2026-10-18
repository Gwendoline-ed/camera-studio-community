"""GTK adapter for the isolated AmScope stream; keeps only the latest RGB frame."""
from .i18n import tr as _t
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import gi
gi.require_version('Gdk','4.0')
from gi.repository import Gdk,GLib
from .amcam import MAX_PIXELS


def worker_args(*args):return [sys.executable,'-m','tiny2.amcam_worker',*args]

def worker_environment():return {**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}

def discover():
    result=subprocess.run(worker_args('--list'),capture_output=True,timeout=5,env=worker_environment(),
                          cwd=Path(__file__).resolve().parent.parent)
    try:data=json.loads(result.stdout)
    except (ValueError,UnicodeError):raise RuntimeError(_t('AmScope-Treiber konnte nicht gelesen werden.'))
    if result.returncode:raise RuntimeError(data.get('error',_t('AmScope-Zugriff fehlgeschlagen.')))
    return data['cameras']


def read_frame(stream):
    header=stream.readline(4097)
    if not header:raise EOFError(_t('AmScope-Verbindung beendet.'))
    if len(header)>4096:raise ValueError(_t('Ungültige AmScope-Bildnachricht.'))
    info=json.loads(header)
    if info.get('type')=='error':raise RuntimeError(info.get('error',_t('AmScope-Fehler.')))
    if info.get('type')!='frame':raise ValueError(_t('Unbekannte AmScope-Bildnachricht.'))
    width,height,stride,size=(info.get(k) for k in ('width','height','stride','size'))
    if (any(type(x)!=int for x in (width,height,stride,size)) or min(width,height)<1 or
        width*height>MAX_PIXELS or stride!=width*3 or size!=stride*height):
        raise ValueError(_t('Ungültige AmScope-Bildgröße.'))
    chunks=[];remaining=size
    while remaining:
        part=stream.read(remaining)
        if not part:raise EOFError(_t('AmScope-Bildübertragung unterbrochen.'))
        chunks.append(part);remaining-=len(part)
    return width,height,stride,b''.join(chunks)


class AmcamPreview:
    def __init__(self,on_frame,on_error):
        self.on_frame=on_frame;self.on_error=on_error
        self.process=None;self.generation=0;self.latest=None;self.lock=threading.Lock();self.timer=None

    def start_auto(self,identifier):
        self.stop();generation=self.generation
        process=subprocess.Popen(worker_args(identifier),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    env=worker_environment(),cwd=Path(__file__).resolve().parent.parent)
        self.process=process;self.timer=GLib.timeout_add(67,self.display,generation)
        def reader():
            try:
                while True:
                    frame=read_frame(process.stdout)
                    with self.lock:
                        if generation!=self.generation:break
                        self.latest=frame
            except Exception as error:GLib.idle_add(self.failed,generation,str(error))
            finally:
                process.stdout.close()
                # Also handles a malformed stream while the worker is still alive.
                if process.poll() is None:process.terminate()
                self.reap(process)
        threading.Thread(target=reader,name='tiny2-amscope-reader',daemon=True).start()

    def display(self,generation):
        if generation!=self.generation:return False
        with self.lock:frame,self.latest=self.latest,None
        if frame:
            width,height,stride,data=frame
            self.on_frame(Gdk.MemoryTexture.new(width,height,Gdk.MemoryFormat.R8G8B8,GLib.Bytes.new(data),stride))
        return True

    def failed(self,generation,message):
        if generation==self.generation:self.stop();self.on_error(message)
        return False

    @staticmethod
    def reap(process):
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:process.kill();process.wait()

    def stop(self):
        self.generation+=1
        if self.timer:GLib.source_remove(self.timer);self.timer=None
        process,self.process=self.process,None
        if process and process.poll() is None:
            process.terminate()
            threading.Thread(target=self.reap,args=(process,),name='tiny2-amscope-stop',daemon=True).start()
        with self.lock:self.latest=None
