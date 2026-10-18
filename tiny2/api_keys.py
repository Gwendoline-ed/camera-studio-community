"""Session credentials, opt-in owner-only file, or named environment variables.

No keys are included in integration settings, archives, URLs or diagnostics.
"""
from .i18n import tr as _t
import json
import os
import stat
from .camera_profiles import config_root,atomic_json
from .ai_providers import ENV_KEYS

_sessions={}


def _path():
    from .integrations import _directory
    return config_root(_directory)/'api-keys.json'


def _validate(key):
    if not isinstance(key,str) or len(key)>4096 or any(not 33<=ord(c)<=126 for c in key):
        raise ValueError(_t('API-Schlüssel ungültig. Bitte ohne Leerzeichen oder Zeilenumbruch eingeben.'))
    return key


def _saved():
    path=_path()
    try:
        with path.open('rb') as stream:
            info=os.fstat(stream.fileno())
            if info.st_uid!=os.getuid() or info.st_mode&0o077:
                raise ValueError(_t('Die Schlüsseldatei muss ausschließlich für dein Benutzerkonto lesbar sein (0600).'))
            raw=stream.read(16385)
        if len(raw)>16384:raise ValueError(_t('Schlüsseldatei zu groß.'))
        data=json.loads(raw)
        if not isinstance(data,dict) or set(data)-ENV_KEYS.keys():raise ValueError(_t('Ungültige Schlüsseldatei.'))
        return {p:_validate(k) for p,k in data.items()}
    except FileNotFoundError:return {}


def get(provider):
    if provider not in ENV_KEYS:return ''
    ident=(str(_path()),provider)
    if ident in _sessions:return _sessions[ident]
    # Environment configuration wins over a saved file, never printed to the UI.
    env=os.environ.get(ENV_KEYS[provider],'')
    if not env and provider=='gemini':env=os.environ.get('GOOGLE_API_KEY','')
    return _validate(env) if env else _saved().get(provider,'')


def saved(provider):return provider in _saved()


def set_key(provider,key,*,persist=False):
    if provider not in ENV_KEYS:raise ValueError(_t('Unbekannter Schlüssel-Anbieter.'))
    key=_validate(key.strip());data=_saved()
    if persist and key:data[provider]=key
    else:data.pop(provider,None)
    if data or _path().exists():atomic_json(_path(),data)
    _sessions[(str(_path()),provider)]=key


def forget(provider):set_key(provider,'')
