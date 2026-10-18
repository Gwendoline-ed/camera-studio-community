from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from tiny2.overlays import DEFAULTS, OverlayStore, fitted_rect, positioned, validate


class GeometryTests(unittest.TestCase):
    def test_landscape_video_in_portrait_window(self):
        self.assertEqual(fitted_rect(400, 800, 1280, 720), (0, 287.5, 400, 225))

    def test_four_by_three_in_wide_window(self):
        self.assertEqual(fitted_rect(1280, 720, 640, 480), (160, 0, 960, 720))

    def test_overlay_at_bottom_right_stays_inside_video(self):
        rect = fitted_rect(400, 800, 1280, 720)
        self.assertEqual(positioned(rect, 100, 20, 100, 100), (300, 492.5))

    def test_minimized_window_has_empty_rectangle(self):
        self.assertEqual(fitted_rect(0, 0, 1280, 720), (0, 0, 0, 0))


class OverlayStorageTests(unittest.TestCase):
    def test_roundtrip_all_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OverlayStore(tmp); settings = store.load()
            settings['text'].update(enabled=True, text='Grüße <b>Daniel</b>', opacity=73)
            settings['clock'].update(enabled=True, seconds=False)
            settings['image'].update(enabled=True, path='/tmp/Mein Logo.png', size=23)
            store.save(settings)
            self.assertEqual(store.load(), settings)
            self.assertEqual(list(Path(tmp).iterdir()), [store.path])

    def test_invalid_file_survives_failed_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OverlayStore(tmp); store.path.write_text('{broken')
            with self.assertRaises(ValueError): store.load()
            self.assertEqual(store.path.read_text(), '{broken')

    def test_bad_save_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OverlayStore(tmp); store.save(DEFAULTS)
            before = store.path.read_bytes()
            settings = deepcopy(DEFAULTS); settings['text']['x'] = float('nan')
            with self.assertRaises(ValueError): store.save(settings)
            self.assertEqual(store.path.read_bytes(), before)

    def test_corrupt_values_are_rejected(self):
        for kind, key, value in [('text','enabled',1), ('clock','seconds','false'),
                                 ('image','size',0), ('image','opacity',101),
                                 ('text','text','x'*201), ('image','path','bad\0path')]:
            with self.subTest(kind=kind,key=key):
                settings = deepcopy(DEFAULTS); settings[kind][key] = value
                with self.assertRaises(ValueError): validate(settings)

    def test_default_instances_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OverlayStore(tmp); value = store.load(); value['text']['text'] = 'Changed'
            self.assertEqual(store.load(), DEFAULTS)


if __name__ == '__main__': unittest.main()
