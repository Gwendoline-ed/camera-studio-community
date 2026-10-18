"""Read-only V4L2 capability enumeration. All intervals are exact fractions."""
from .i18n import tr as _t
from dataclasses import dataclass, field
import errno
import fcntl
from fractions import Fraction
import os
import re
import stat
import struct
from .device import ioc, QUERYCAP

ENUM_FMT=ioc(3,'V',2,64)
ENUM_SIZE=ioc(3,'V',74,44)
ENUM_INTERVAL=ioc(3,'V',75,52)
MAX_PIXELS=32_000_000
RAW={'YUYV':'YUY2','UYVY':'UYVY','NV12':'NV12','NV21':'NV21','YU12':'I420','YV12':'YV12',
     'RGB3':'RGB','BGR3':'BGR','GREY':'GRAY8','Y16 ':'GRAY16_LE'}
MEDIA={'MJPG':'image/jpeg','JPEG':'image/jpeg','H264':'video/x-h264','HEVC':'video/x-h265'}


def valid_size(width,height):
    return type(width) is int and type(height) is int and 1<=width<=16384 and 1<=height<=16384 and width*height<=MAX_PIXELS


@dataclass(frozen=True)
class VideoMode:
    width:int
    height:int
    fourcc:str
    fps:Fraction | None = None

    def __post_init__(self):
        if not valid_size(self.width,self.height) or self.fourcc not in RAW.keys()|MEDIA.keys():
            raise ValueError(_t('Nicht unterstützte Bildgröße oder Bildkodierung.'))
        if self.fps is not None and (not isinstance(self.fps,Fraction) or not 0<self.fps<=1000 or max(self.fps.numerator,self.fps.denominator)>2147483647):
            raise ValueError(_t('Ungültige Bildrate.'))

    @property
    def label(self):
        rate=_t('{v0:g} Bilder/s', v0=float(self.fps)) if self.fps else _t('Bildrate automatisch')
        return f'{self.width} × {self.height} · {rate} · {self.fourcc.strip()}'

    @property
    def caps(self):
        result=('video/x-raw,format='+RAW[self.fourcc]) if self.fourcc in RAW else MEDIA[self.fourcc]
        result+=f',width={self.width},height={self.height}'
        if self.fps:result+=f',framerate={self.fps.numerator}/{self.fps.denominator}'
        return result


@dataclass(frozen=True)
class SizeRange:
    fourcc:str
    min_width:int
    max_width:int
    step_width:int
    min_height:int
    max_height:int
    step_height:int

    def mode(self,width,height):
        if not (self.min_width<=width<=self.max_width and self.min_height<=height<=self.max_height and
                (width-self.min_width)%self.step_width==0 and (height-self.min_height)%self.step_height==0):
            raise ValueError(_t('Diese Größe passt nicht zum Größenraster der Kamera.'))
        return VideoMode(width,height,self.fourcc)

    @property
    def label(self):return _t('Eigene Größe · {v0}', v0=self.fourcc.strip())


@dataclass
class Catalog:
    modes:list = field(default_factory=list)
    ranges:list = field(default_factory=list)
    note:str = ''


def _enum(fd,request,data):
    try:fcntl.ioctl(fd,request,data,True);return True
    except OSError as error:
        if error.errno in (errno.EINVAL,errno.ENOTTY):return False
        raise


def frame_rates(fd,pixel,width,height):
    rates=[]
    for index in range(256):
        data=bytearray(52);struct.pack_into('=IIII',data,0,index,pixel,width,height)
        if not _enum(fd,ENUM_INTERVAL,data):break
        kind=struct.unpack_from('=I',data,16)[0]
        if kind==1:
            numerator,denominator=struct.unpack_from('=II',data,20)
            if numerator and denominator:rates.append(Fraction(denominator,numerator))
        elif kind in (2,3):
            # A range cannot be represented by a finite list: negotiate the rate.
            return [None]
        else:break
    return sorted({r for r in rates if 0<r<=1000},reverse=True) or [None]


def enumerate_fd(fd):
    caps=bytearray(104);fcntl.ioctl(fd,QUERYCAP,caps,True)
    capabilities,devcaps=struct.unpack_from('=II',caps,84)
    effective=devcaps if capabilities&0x80000000 else capabilities
    if not effective&(1|0x1000):raise ValueError(_t('Dieses Gerät liefert Metadaten, kein Kamerabild.'))
    buf_type=1 if effective&1 else 9
    result=Catalog()
    for index in range(128):
        fmt=bytearray(64);struct.pack_into('=II',fmt,0,index,buf_type)
        if not _enum(fd,ENUM_FMT,fmt):break
        pixel=struct.unpack_from('=I',fmt,44)[0];fourcc=struct.pack('=I',pixel).decode('latin1')
        if fourcc not in RAW.keys()|MEDIA.keys():continue
        for size_index in range(512):
            size=bytearray(44);struct.pack_into('=II',size,0,size_index,pixel)
            if not _enum(fd,ENUM_SIZE,size):break
            kind=struct.unpack_from('=I',size,8)[0]
            if kind==1:
                width,height=struct.unpack_from('=II',size,12)
                if valid_size(width,height):
                    result.modes.extend(VideoMode(width,height,fourcc,rate) for rate in frame_rates(fd,pixel,width,height))
            elif kind in (2,3):
                loww,highw,stepw,lowh,highh,steph=struct.unpack_from('=6I',size,12)
                if kind==2:stepw=steph=1
                if stepw and steph and 1<=loww<=highw and 1<=lowh<=highh and valid_size(loww,lowh):
                    result.ranges.append(SizeRange(fourcc,loww,min(highw,16384),stepw,lowh,min(highh,16384),steph))
                break
            else:break
    result.modes=sorted(set(result.modes),key=lambda m:(m.width*m.height,m.width,m.height,m.fourcc,-(m.fps or 0)))
    if not result.modes and not result.ranges:result.note=_t('Der Treiber meldet keine auswählbaren Modi. Automatische Aushandlung verwenden.')
    return result


def discover(path):
    if not re.fullmatch(r'/dev/video[0-9]+',str(path)):raise ValueError(_t('Ungültiger Kamerapfad.'))
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        if not stat.S_ISCHR(os.fstat(fd).st_mode):raise ValueError(_t('Kein Kameragerät.'))
        return enumerate_fd(fd)
    finally:os.close(fd)


def available(path):
    try:return discover(path)
    except (OSError,ValueError) as error:return Catalog(note=_t('Bildmodi nicht lesbar: ')+str(error))
