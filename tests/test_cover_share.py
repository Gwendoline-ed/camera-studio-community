import http.client
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tiny2.cover_share import CoverShare, MAX_SHARES

PNG = b'\x89PNG\r\n\x1a\nsynthetic-image'


class CoverShareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / 'web'; root.mkdir()
        (root / 'index.html').write_text('<head><script defer src="app.js"></script></head>')
        (root / 'app.js').write_text("const workerPath='/vendor/worker.min.js'; window.name='lager-cover-import';")
        (root / 'panini-reader.js').write_text("postMessage(message,'http://localhost:8089');else window.open('http://localhost:8089/#panini='+encodeURIComponent(JSON.stringify(data)),'lager-cover-import');")
        (root.parent / 'secret.txt').write_text('private')
        self.share = CoverShare(root)
        # Unit tests require no listening socket.
        self.share.server = SimpleNamespace(server_port=12345)
        self.url = self.share.share(PNG)
        self.path = self.url.removeprefix(self.share.origin)
        self.host = '127.0.0.1:12345'

    def tearDown(self): self.tmp.cleanup()

    def test_snapshot_requires_unpredictable_token_and_correct_host_origin(self):
        self.assertEqual(self.share.response(self.path + 'snapshot.png', self.host)[2], PNG)
        self.assertEqual(self.share.response('/snapshot.png', self.host)[0], 404)
        self.assertEqual(self.share.response('/invalid/snapshot.png', self.host)[0], 404)
        self.assertEqual(self.share.response(self.path, 'evil.example')[0], 403)
        self.assertEqual(self.share.response(self.path, self.host, 'http://elsewhere')[0], 403)
        self.assertEqual(self.share.response(self.path, self.host, self.share.origin)[0], 200)

    def test_traversal_and_symlinks_cannot_escape_web_root(self):
        (self.share.root / 'leak.txt').symlink_to(self.share.root.parent / 'secret.txt')
        for name in ('../secret.txt', '%2e%2e/secret.txt', '%2Fetc/passwd', 'leak.txt', '%00'):
            self.assertEqual(self.share.response(self.path + name, self.host)[0], 404, name)

    def test_worker_and_panini_routes_stay_on_this_share(self):
        html = self.share.response(self.path, self.host)[2].decode()
        self.assertLess(html.index('tiny2-config.js'), html.index('app.js'))
        self.assertGreater(html.index('tiny2-share.js'), html.index('app.js'))
        self.assertEqual(html.count('tiny2-config.js'), 1)
        app = self.share.response(self.path + 'app.js', self.host)[2].decode()
        self.assertIn(self.path + 'vendor/worker.min.js', app)
        panini = self.share.response(self.path + 'panini-reader.js', self.host)[2].decode()
        self.assertIn("postMessage(message,'*')", panini)
        self.assertIn('Produktseite zuerst aus der Cover-Erfassung', panini)
        self.assertNotIn('8089', panini)

    def test_images_expire_and_storage_is_bounded(self):
        for _ in range(MAX_SHARES + 2): self.share.share(PNG)
        self.assertEqual(len(self.share.frames), MAX_SHARES)
        self.assertEqual(self.share.response(self.path, self.host)[0], 404)
        with patch('tiny2.cover_share.time.monotonic', return_value=10**15): self.share.prune()
        self.assertFalse(self.share.frames)

    def test_bad_images_rejected_before_opening_port(self):
        fresh = CoverShare(self.share.root)
        with self.assertRaises(ValueError): fresh.share(b'not-png')
        self.assertIsNone(fresh.server)

    def test_loopback_http_roundtrip_and_shutdown(self):
        live = CoverShare(self.share.root)
        try:
            url = live.share(PNG)
            self.assertEqual(live.server.server_address[0], '127.0.0.1')
            connection = http.client.HTTPConnection('127.0.0.1', live.server.server_port, timeout=2)
            connection.request('GET', url.removeprefix(live.origin) + 'snapshot.png')
            result = connection.getresponse()
            self.assertEqual(result.status, 200); self.assertEqual(result.read(), PNG)
            self.assertEqual(result.getheader('Cache-Control'), 'no-store')
            self.assertIn("frame-ancestors 'none'", result.getheader('Content-Security-Policy'))
            connection.close()
        finally: live.close()
        self.assertFalse(live.frames); self.assertFalse(live.thread.is_alive())


if __name__ == '__main__': unittest.main()
