"""Short-lived, loopback-only image handoff to the existing local cover reader.

The InvenTree preparation is read without changing or restarting its service.
No inventory API is called. Images live only in memory until expiry or shutdown.
"""
from .i18n import tr as _t
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import unquote, urlsplit
from .gwen import MAX_IMAGE
from . import integrations

TTL = 30 * 60
MAX_SHARES = 8
REQUIRED = ('index.html', 'app.js', 'panini-reader.js', 'photo-editor.js',
            'label-reader.js', 'vendor/tesseract.min.js', 'vendor/worker.min.js')


def cover_root(home=None):
    configured=integrations.load()['cover_root']
    if not configured:raise RuntimeError(_t('Kein Cover-Tool eingerichtet. Bitte KI & Dienste öffnen oder das Bild kopieren / speichern.'))
    root=Path(configured).expanduser()
    if not all((root / name).is_file() for name in REQUIRED):
        raise RuntimeError(_t('Die lokale InvenTree-Cover-Erfassung wurde nicht gefunden. Du kannst das Bild stattdessen kopieren oder speichern.'))
    app = (root / 'app.js').read_text()
    if not all(text in app for text in ('function drawPhoto(', 'async function recognize(', 'function stop(')):
        raise RuntimeError(_t('Die Cover-Erfassung hat sich geändert. Die Bildübergabe muss angepasst werden.'))
    return root.resolve()


BRIDGE = rb'''"use strict";
(async () => {
  if (window.tiny2PaniniReturn) return;
  try {
    status('Kamerabild aus Tiny 2 Studio wird \u00fcbernommen ...');
    const response = await fetch('snapshot.png', {cache: 'no-store'});
    if (!response.ok) throw Error('Das geteilte Bild ist abgelaufen. Bitte erneut in Tiny 2 Studio teilen.');
    const image = await createImageBitmap(await response.blob());
    try { drawPhoto(image, image.width, image.height); } finally { image.close(); }
    stop();
    await recognize();
  } catch (error) { status(error.message, true); }
})();
'''


class CoverShare:
    def __init__(self, root=None):
        self.root = cover_root() if root is None else Path(root).resolve()
        self.lock = threading.Lock()
        self.frames = {}
        self.server = None
        self.thread = None

    def share(self, png):
        if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png) > MAX_IMAGE:
            raise ValueError(_t('Bitte ein PNG-Kamerabild bis 8 MB teilen.'))
        if self.server is None:
            owner = self
            class Handler(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup(); self.connection.settimeout(5)

                def do_GET(self):
                    code, kind, data = owner.response(self.path, self.headers.get('Host'), self.headers.get('Origin'))
                    self.send_response(code)
                    self.send_header('Content-Type', kind)
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
                    self.send_header('Permissions-Policy', 'camera=(self), microphone=()')
                    self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self' blob:; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
                    self.end_headers()
                    try: self.wfile.write(data)
                    except (BrokenPipeError, ConnectionResetError): pass

                def log_message(self, *_): pass

            self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            self.server.daemon_threads = True
            self.server.service_actions = self.prune
            self.thread = threading.Thread(target=self.server.serve_forever,
                                           name='tiny2-cover-share', daemon=True)
            self.thread.start()
        token = secrets.token_urlsafe(24)
        with self.lock:
            self._prune()
            while len(self.frames) >= MAX_SHARES: self.frames.pop(next(iter(self.frames)))
            self.frames[token] = (time.monotonic() + TTL, bytes(png))
        return self.origin + '/' + token + '/'

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def _prune(self):
        now = time.monotonic()
        for token, (expiry, _) in list(self.frames.items()):
            if expiry <= now: del self.frames[token]

    def prune(self):
        with self.lock: self._prune()

    def response(self, target, host, origin=None):
        missing = (404, 'text/plain; charset=utf-8', b'Bild nicht vorhanden oder abgelaufen.')
        if host != self.origin.removeprefix('http://') or (origin and origin != self.origin):
            return 403, 'text/plain', b'Forbidden'
        path = urlsplit(target).path
        parts = path.split('/', 2)
        if len(parts) != 3: return missing
        _, token, name = parts
        with self.lock:
            self._prune(); frame = self.frames.get(token)
        if frame is None: return missing
        name = unquote(name or 'index.html')
        if '\x00' in name or '\\' in name: return missing
        prefix = '/' + token + '/'
        if name == 'snapshot.png': return 200, 'image/png', frame[1]
        if name == 'tiny2-config.js':
            return 200, 'text/javascript', b'window.tiny2PaniniReturn = location.hash.startsWith("#panini=");'
        if name == 'tiny2-share.js': return 200, 'text/javascript', BRIDGE
        file = (self.root / name).resolve()
        if not file.is_relative_to(self.root) or not file.is_file(): return missing
        data = file.read_bytes()
        if name == 'index.html':
            # Capture fragment before the existing app clears it.
            data = data.replace(b'<script defer src="app.js">',
                b'<script defer src="tiny2-config.js"></script><script defer src="app.js">', 1)
            data = data.replace(b'</head>', b'<script defer src="tiny2-share.js"></script></head>')
        elif name == 'app.js':
            data = data.replace(b"'/vendor/", ("'" + prefix + 'vendor/').encode())
            data = data.replace(b'http://localhost:8089', self.origin.encode())
            data = data.replace(b'lager-cover-import', ('tiny2-cover-' + token).encode())
        elif name == 'panini-reader.js':
            # The bookmark remains reusable across randomly assigned local ports.
            # It sends only public product metadata to its opener; app.js checks
            # both the Panini origin and the exact window it opened for searching.
            data = data.replace(b"postMessage(message,'http://localhost:8089')",
                                b"postMessage(message,'*')")
            data = data.replace(b"else window.open('http://localhost:8089/#panini='+encodeURIComponent(JSON.stringify(data)),'lager-cover-import');",
                                b"else alert('Bitte die Produktseite zuerst aus der Cover-Erfassung mit Bei Panini suchen oeffnen. Alternativ den Produkttext dort einfuegen.');")
        kind = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        if file.suffix == '.js': kind = 'text/javascript'
        return 200, kind, data

    def close(self):
        if self.server is not None:
            server = self.server
            server.shutdown(); server.server_close()
            if self.thread: self.thread.join(timeout=2)
            self.server = None
        with self.lock: self.frames.clear()
