"""Minimal Linux AmScope SDK binding; used only by the isolated camera worker."""
from .i18n import tr as _t
import ctypes as C
import os
from pathlib import Path
import queue
import threading
import time

MAX_CAMERAS=128
MAX_PIXELS=20_000_000
EVENT_IMAGE=0x0004
EVENT_ERRORS={0x0080:_t('AmScope meldet einen Aufnahmefehler.'),0x0081:_t('AmScope-Kamera wurde getrennt.'),
              0x0082:_t('AmScope liefert keine Bilder.'),0x0085:_t('AmScope liefert keine USB-Daten.')}
EVENT_CALLBACK=C.CFUNCTYPE(None,C.c_uint,C.c_void_p)


class Resolution(C.Structure):
    _fields_=[('width',C.c_uint),('height',C.c_uint)]


class Model(C.Structure):
    _fields_=[('name',C.c_char_p),('flag',C.c_ulonglong),('maxspeed',C.c_uint),('preview',C.c_uint),
              ('still',C.c_uint),('maxfanspeed',C.c_uint),('ioctrol',C.c_uint),
              ('xpixsz',C.c_float),('ypixsz',C.c_float),('res',Resolution*16)]


class Device(C.Structure):
    _fields_=[('displayname',C.c_char*64),('id',C.c_char*64),('model',C.POINTER(Model))]


class FrameInfo(C.Structure):
    _fields_=[('width',C.c_uint),('height',C.c_uint),('flag',C.c_uint),('seq',C.c_uint),('timestamp',C.c_ulonglong)]


def library_path():
    explicit=os.environ.get('TINY2_AMCAM_LIBRARY')
    if explicit:return Path(explicit)
    for path in (Path.home()/'.local/opt/AmLite/libamcam.so',Path('/opt/AmLite/libamcam.so'),
                 Path('/usr/local/lib/libamcam.so'),Path('/usr/lib/libamcam.so')):
        if path.is_file():return path
    raise RuntimeError(_t('AmScope-Bibliothek fehlt. Bitte AmLite für Linux installieren.'))


def check(result,action):
    if result<0:raise RuntimeError(_t('{v0} fehlgeschlagen (AmScope 0x{v1:08x}).', v0=action, v1=result&0xffffffff))


class SDK:
    def __init__(self,path=None):
        self.path=Path(path) if path else library_path()
        self.lib=C.CDLL(str(self.path))
        pointer=C.c_void_p;integer=C.c_int
        signatures={
            'Version':(C.c_char_p,[]),
            'EnumV2':(C.c_uint,[C.POINTER(Device)]),
            'get_Model':(C.POINTER(Model),[C.c_ushort,C.c_ushort]),
            'Open':(pointer,[C.c_char_p]),'Close':(None,[pointer]),'Stop':(integer,[pointer]),
            'get_Size':(integer,[pointer,C.POINTER(integer),C.POINTER(integer)]),
            'get_FinalSize':(integer,[pointer,C.POINTER(integer),C.POINTER(integer)]),
            'put_Option':(integer,[pointer,C.c_uint,integer]),
            'put_RealTime':(integer,[pointer,integer]),
            'StartPullModeWithCallback':(integer,[pointer,EVENT_CALLBACK,pointer]),
            'PullImageWithRowPitchV2':(integer,[pointer,pointer,integer,integer,C.POINTER(FrameInfo)])}
        for name,(result,args) in signatures.items():
            function=getattr(self.lib,'Amcam_'+name);function.restype=result;function.argtypes=args
            setattr(self,name,function)

    def cameras(self):
        devices=(Device*MAX_CAMERAS)();count=self.EnumV2(devices)
        if count>MAX_CAMERAS:raise RuntimeError(_t('Ungültige AmScope-Geräteliste.'))
        result=[]
        for device in devices[:count]:
            if not device.model:continue
            name=device.model.contents.name.decode('utf-8',errors='replace')
            result.append({'path':device.id.decode('utf-8'),'name':'AmScope '+(device.displayname.decode('utf-8',errors='replace') or name),
                           'model':name,'backend':'amcam','available':True})
        return result

    def usb_cameras(self,root=Path('/sys/bus/usb/devices')):
        result=[]
        for node in sorted(root.glob('*')):
            try:
                vendor=int((node/'idVendor').read_text().strip(),16)
                product=int((node/'idProduct').read_text().strip(),16)
                model=self.get_Model(vendor,product)
                if not model:continue
                name=model.contents.name.decode('utf-8',errors='replace')
                result.append({'path':'amcam-usb:'+node.name,'name':'AmScope '+name,'model':name,
                               'backend':'amcam','available':False})
            except (OSError,ValueError):continue
        return result

    def discover(self):
        cameras=self.cameras();models={c['model'] for c in cameras}
        # USB identity can be visible even if another app or device permissions prevent SDK access.
        cameras.extend(c for c in self.usb_cameras() if c['model'] not in models)
        return cameras

    def resolve(self,identifier):
        cameras=self.cameras()
        if identifier.startswith('amcam-usb:'):
            usb=next((c for c in self.usb_cameras() if c['path']==identifier),None)
            if usb:
                candidates=[c for c in cameras if c['model']==usb['model']]
                if len(candidates)==1:return candidates[0]['path']
        elif any(c['path']==identifier for c in cameras):return identifier
        raise RuntimeError(_t('AmScope-Kamera am USB erkannt, aber nicht zugänglich. Bitte die Kameravorschau in AmLite schließen und „Neu suchen“ wählen. Falls nötig USB-Verbindung und Geräteberechtigung prüfen.'))


class Capture:
    """Pull frames on SDK notifications; stop/close strictly outside its callback."""
    def __init__(self,sdk,identifier):
        self.sdk=sdk;self.handle=None;self.closed=False;self.started=False
        self.frames=queue.Queue(maxsize=1);self.error=None;self.lock=threading.Lock();self.callback=None
        try:
            self.handle=sdk.Open(sdk.resolve(identifier).encode('utf-8'))
            if not self.handle:raise RuntimeError(_t('MU/AmScope-Kamera kann nicht geöffnet werden. Bitte die Kameravorschau in AmLite schließen und erneut versuchen.'))
            # Native Linux RGB orientation; no PTZ, zoom, EEPROM or exposure changes.
            for option,value in ((0x04,0),(0x0c,0),(0x2a,0),(0x23,0)):
                check(sdk.put_Option(self.handle,option,value),_t('AmScope-Bildformat'))
            check(sdk.put_RealTime(self.handle,1),_t('AmScope-Livebild'))
            width,height=C.c_int(),C.c_int()
            check(sdk.get_FinalSize(self.handle,C.byref(width),C.byref(height)),_t('AmScope-Bildgröße'))
            self.width,self.height=width.value,height.value
            if min(self.width,self.height)<1 or self.width*self.height>MAX_PIXELS:
                raise RuntimeError(_t('Ungültige oder zu große AmScope-Bildgröße.'))
            self.stride=self.width*3
            self.buffer=C.create_string_buffer(self.stride*self.height)
            self.callback=EVENT_CALLBACK(self.event)
            check(sdk.StartPullModeWithCallback(self.handle,self.callback,None),_t('AmScope-Aufnahme'))
            self.started=True
        except BaseException:
            self.close();raise

    def event(self,event,_context):
        with self.lock:
            if self.closed:return
            if event in EVENT_ERRORS:self.error=EVENT_ERRORS[event];return
            if event!=EVENT_IMAGE:return
            try:
                info=FrameInfo()
                result=self.sdk.PullImageWithRowPitchV2(self.handle,self.buffer,24,self.stride,C.byref(info))
                if result&0xffffffff==0x8000000a:return  # E_PENDING: no frame ready
                check(result,_t('AmScope-Bildabruf'))
                if (info.width,info.height)!=(self.width,self.height):
                    raise RuntimeError(_t('AmScope-Bildgröße hat sich geändert. Vorschau bitte neu starten.'))
                frame=(self.width,self.height,self.stride,self.buffer.raw)
                try:self.frames.get_nowait()
                except queue.Empty:pass
                self.frames.put_nowait(frame)
            except Exception as error:self.error=str(error)

    def next_frame(self,timeout=.2):
        if self.error:raise RuntimeError(self.error)
        try:return self.frames.get(timeout=timeout)
        except queue.Empty:return None

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True
        if self.handle:
            handle,self.handle=self.handle,None
            try:
                if self.started:self.sdk.Stop(handle)
            finally:self.sdk.Close(handle)
        self.callback=None
