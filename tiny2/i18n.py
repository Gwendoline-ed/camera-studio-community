"""Local JSON translations. Protocol identifiers and user data are never translated."""
import json
import os
from pathlib import Path
import tempfile

LANGUAGES = ('en', 'de', 'da', 'es', 'pl', 'fr')
NAMES = ('English', 'Deutsch', 'Dansk', 'Español', 'Polski', 'Français')
LANGUAGE_NAMES = dict(zip(LANGUAGES, ('English', 'German', 'Danish', 'Spanish', 'Polish', 'French')))
_language = os.environ.get('CAMERA_STUDIO_LANGUAGE', 'de')
if _language not in LANGUAGES: _language = 'de'
_catalogs = {}
_directory = None


def language():
    return _language


def config_path(directory=None):
    root = Path(directory) if directory else Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'camera-studio-community'
    return root/'language.json'


def detect_language(environ=None):
    env = os.environ if environ is None else environ
    raw = env.get('LANGUAGE') or env.get('LC_ALL') or env.get('LC_MESSAGES') or env.get('LANG') or 'en'
    for item in raw.split(':'):
        code = item.split('.')[0].split('_')[0].split('-')[0].lower()
        if code in LANGUAGES: return code
    return 'en'


def configure(directory=None, override=None):
    global _language, _directory
    _directory = directory
    selected = detect_language()
    try:
        with config_path(directory).open('rb') as stream: raw = stream.read(1025)
        value = json.loads(raw) if len(raw) <= 1024 else {}
        if isinstance(value, dict) and value.get('language') in LANGUAGES: selected = value['language']
    except (OSError, ValueError): pass
    if override is not None:
        if override not in LANGUAGES: raise ValueError('Unsupported language')
        selected = override
    _language = selected
    # Worker processes use the same language for their status/error messages.
    os.environ['CAMERA_STUDIO_LANGUAGE'] = selected
    return selected


def save_language(code, directory=None):
    if code not in LANGUAGES: raise ValueError('Unsupported language')
    path = config_path(_directory if directory is None else directory)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.language-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'language': code}, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def tr(message, **values):
    """German source keys; format after translation so values stay intact."""
    if _language not in _catalogs:
        try:
            _catalogs[_language] = json.loads((Path(__file__).parent/'locales'/(_language+'.json')).read_text(encoding='utf-8'))
        except (OSError, ValueError): _catalogs[_language] = {}
    text = _catalogs[_language].get(message, message)
    return text.format(**values) if values else text


def manual_path():
    """Resolve the same manual from a source checkout or installed DEB."""
    root = Path(__file__).resolve().parent.parent
    candidates = (root/'docs'/('guide-'+_language+'.html'), root.parent/'doc'/'camera-studio-community'/'docs'/('guide-'+_language+'.html'))
    return next((p for p in candidates if p.is_file()), candidates[0])
