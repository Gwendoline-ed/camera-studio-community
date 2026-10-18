"""Declarative, per-user camera profiles; executable plug-ins are not loaded."""
from .i18n import tr as _t
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import tempfile


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    backend: str
    usb: dict | None = None
    version: int = 1


BUILTINS = (
    Profile('tiny2', 'OBSBOT Tiny 2 · fest integriert', 'tiny2', {'vendor':'3564','product':'fef8'}),
    Profile('usb-video', 'USB-Kameras · Linux / UVC', 'v4l2'),
    Profile('amscope', 'AmScope / MU300 · optionales AmLite-SDK', 'amcam'),
    Profile('andonstar', 'Andonstar · WLAN', 'andonstar'),
)
RESERVED = {p.id for p in BUILTINS}
MAX_BYTES = 16384


def config_root(directory=None):
    return Path(directory) if directory else Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'camera-studio-community'


def parse_profile(data):
    if not isinstance(data, dict) or set(data)-{'version','id','name','backend','usb'}:
        raise ValueError(_t('Unbekannte Felder im Kameraprofil.'))
    if type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError(_t('Dieses Kameraprofil benötigt eine andere Formatversion.'))
    ident, name = data.get('id'), data.get('name')
    if not isinstance(ident,str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,63}',ident) or ident in RESERVED:
        raise ValueError(_t('Profil-ID ungültig oder für ein integriertes Profil reserviert.'))
    if not isinstance(name,str) or not 1 <= len(name.strip()) <= 100 or any(ord(c)<32 for c in name):
        raise ValueError(_t('Bitte einen lesbaren Profilnamen mit höchstens 100 Zeichen verwenden.'))
    if data.get('backend') != 'v4l2':
        raise ValueError(_t('Importierte Profile unterstützen derzeit Linux-/UVC-Kameras (v4l2). Spezialtreiber müssen als Adapter entwickelt werden.'))
    usb=data.get('usb')
    if not isinstance(usb,dict) or set(usb)!={'vendor','product'} or not all(isinstance(v,str) and re.fullmatch('[0-9a-fA-F]{4}',v) for v in usb.values()):
        raise ValueError(_t('USB-Hersteller und Produkt müssen je vier Hexadezimalstellen enthalten.'))
    usb={k:v.lower() for k,v in usb.items()}
    if usb==BUILTINS[0].usb:
        raise ValueError(_t('Die feste Tiny-2-Unterstützung kann nicht überschrieben werden.'))
    return Profile(ident,name.strip(),'v4l2',usb)


def atomic_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


class Registry:
    def __init__(self,directory=None):
        self.root=config_root(directory);self.profiles=list(BUILTINS);self.errors=[]
        self.enabled={'tiny2','usb-video'}
        for path in sorted((self.root/'profiles').glob('*.json')):
            try:
                profile=self.read(path)
                if any(p.id==profile.id or p.usb==profile.usb for p in self.profiles):
                    raise ValueError(_t('Doppeltes Profil oder USB-Gerät.'))
                self.profiles.append(profile)
            except (OSError,ValueError) as error:self.errors.append(path.name+': '+str(error))
        try:
            state=json.loads((self.root/'camera-profiles.json').read_text())
            if not isinstance(state,list) or not all(isinstance(x,str) for x in state):raise ValueError(_t('Ungültige Profilauswahl.'))
            self.enabled={p.id for p in self.profiles if p.id in state}|{'tiny2'}
        except FileNotFoundError:pass
        except (OSError,ValueError) as error:self.errors.append(str(error))

    @staticmethod
    def read(path):
        with Path(path).open('rb') as stream:raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError(_t('Kameraprofil ist größer als 16 KB.'))
        return parse_profile(json.loads(raw))

    def enable(self,ident,active):
        if ident not in {p.id for p in self.profiles}:raise ValueError(_t('Unbekanntes Profil.'))
        if ident=='tiny2' and not active:raise ValueError(_t('Tiny 2 bleibt fest integriert.'))
        enabled=(self.enabled|{ident}) if active else (self.enabled-{ident})
        atomic_json(self.root/'camera-profiles.json',sorted(enabled))
        self.enabled=enabled

    def install(self,path):
        profile=self.read(path)
        if any(p.id==profile.id or p.usb==profile.usb for p in self.profiles):
            raise ValueError(_t('Dieses Profil oder USB-Gerät ist bereits vorhanden.'))
        target=self.root/'profiles'/(profile.id+'.json')
        atomic_json(target,asdict(profile))
        self.profiles.append(profile)
        self.enable(profile.id,True)
        return profile

    def active(self,backend):
        return [p for p in self.profiles if p.id in self.enabled and p.backend==backend]

    def match_usb(self,identity):
        profiles=self.active('v4l2')
        return next((p for p in profiles if p.usb and p.usb==identity),None) or next((p for p in profiles if p.usb is None),None)


def usb_identity(node):
    for parent in Path(node).resolve().parents:
        try:return {'vendor':(parent/'idVendor').read_text().strip().lower(),'product':(parent/'idProduct').read_text().strip().lower()}
        except OSError:continue
    return None
