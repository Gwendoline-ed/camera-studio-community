"""Offline Tesseract C API in a cancellable child process; no OCR service."""
from .i18n import tr as _t
import ctypes as C
import ctypes.util
import gzip
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import time

LANG_HASHES = {'deu': 'f5618a8b8d07f6c7a633ce243bf075bb90f4145bb15c9264734c7cc63aa33205',
               'eng': 'ed350f3752f81ee8f38769edc14d92d997dababe23b565c59879372cc46a2468'}


def language_data(cache):
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    for lang, digest in LANG_HASHES.items():
        target = cache / (lang + '.traineddata')
        if target.is_file(): continue
        source = Path(__file__).parent / 'data/ocr' / (lang + '.traineddata.gz')
        compressed = source.read_bytes()
        if hashlib.sha256(compressed).hexdigest() != digest: raise ValueError(_t('OCR-Sprachdatei ist beschädigt.'))
        with gzip.open(source, 'rb') as stream: data = stream.read(64*1024*1024+1)
        if len(data) > 64*1024*1024: raise ValueError(_t('OCR-Sprachdatei ist zu groß.'))
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as stream:
            temp = Path(stream.name); stream.write(data)
        temp.replace(target)
    return cache


def native_ocr(path, data):
    from PIL import Image
    library = ctypes.util.find_library('tesseract')
    if not library: raise RuntimeError(_t('Lokale Texterkennung fehlt: Paket libtesseract5 installieren.'))
    api = C.CDLL(library)
    signatures = {
        'TessBaseAPICreate': (C.c_void_p, []),
        'TessBaseAPIInit3': (C.c_int, [C.c_void_p,C.c_char_p,C.c_char_p]),
        'TessBaseAPISetImage': (None, [C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int]),
        'TessBaseAPISetSourceResolution': (None, [C.c_void_p,C.c_int]),
        'TessBaseAPIGetUTF8Text': (C.c_void_p,[C.c_void_p]),
        'TessBaseAPIMeanTextConf': (C.c_int,[C.c_void_p]),
        'TessDeleteText': (None,[C.c_void_p]), 'TessBaseAPIDelete': (None,[C.c_void_p])}
    for name,(restype,args) in signatures.items():
        function=getattr(api,name); function.restype=restype; function.argtypes=args
    with Image.open(path) as image:
        if image.width*image.height>20_000_000: raise ValueError(_t('Seitenbild zu groß.'))
        image=image.convert('RGB')
    handle=api.TessBaseAPICreate()
    if not handle: raise RuntimeError(_t('Texterkennung konnte nicht gestartet werden.'))
    try:
        if api.TessBaseAPIInit3(handle,os.fsencode(data),b'deu+eng'):
            raise RuntimeError(_t('OCR-Sprachen konnten nicht geladen werden.'))
        raw=C.create_string_buffer(image.tobytes())
        api.TessBaseAPISetImage(handle,raw,image.width,image.height,3,image.width*3)
        api.TessBaseAPISetSourceResolution(handle,200)
        pointer=api.TessBaseAPIGetUTF8Text(handle)
        if not pointer: raise RuntimeError(_t('Texterkennung lieferte keine Antwort.'))
        try: text=C.string_at(pointer).decode('utf-8',errors='replace')[:150000]
        finally: api.TessDeleteText(pointer)
        return {'text':text.strip(),'confidence':api.TessBaseAPIMeanTextConf(handle)}
    finally: api.TessBaseAPIDelete(handle)


def recognize(png, cache, cancel=None):
    cancel=cancel or threading.Event()
    if cancel.is_set(): raise InterruptedError(_t('Abgebrochen.'))
    data=language_data(cache)
    with tempfile.TemporaryDirectory(prefix='tiny2-ocr-') as folder:
        path=Path(folder)/'page.png'; path.write_bytes(png)
        env={**os.environ,'OMP_THREAD_LIMIT':'2','PYTHONDONTWRITEBYTECODE':'1'}
        process=subprocess.Popen([sys.executable,'-m','tiny2.book_ocr',str(path),str(data)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        deadline=time.monotonic()+90
        try:
            while True:
                if cancel.is_set(): raise InterruptedError(_t('Texterkennung abgebrochen.'))
                if time.monotonic()>deadline: raise TimeoutError(_t('Texterkennung dauerte zu lange.'))
                try: out,error=process.communicate(timeout=.2); break
                except subprocess.TimeoutExpired: continue
            if process.returncode: raise RuntimeError(error.decode(errors='replace')[-700:] or _t('Texterkennung fehlgeschlagen.'))
            result=json.loads(out)
            if not isinstance(result.get('text'),str): raise ValueError(_t('Ungültige OCR-Antwort.'))
            return result
        finally:
            if process.poll() is None: process.kill()
            process.wait()


if __name__=='__main__':
    try: print(json.dumps(native_ocr(sys.argv[1],sys.argv[2]),ensure_ascii=False))
    except Exception as error: print(str(error),file=sys.stderr); sys.exit(1)
