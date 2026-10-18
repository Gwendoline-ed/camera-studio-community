"""Behavioral coverage for languages, stored preferences and protocol isolation."""
import ast
import json
import os
from pathlib import Path
import string
import tempfile
import unittest
from unittest.mock import patch
from tiny2 import i18n, protocol

ROOT=Path(__file__).resolve().parents[1]

class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.old=i18n.language();self.directory=i18n._directory
        self.env=patch.dict(os.environ);self.env.start()
    def tearDown(self):
        i18n.configure(self.directory,self.old);self.env.stop()

    def test_catalogs_cover_calls_and_preserve_formatting(self):
        catalogs={lang:json.loads((ROOT/'tiny2/locales'/(lang+'.json')).read_text()) for lang in i18n.LANGUAGES}
        source=catalogs['de'];self.assertGreater(len(source),600)
        fields=lambda s:sorted((field,spec,conv) for _,field,spec,conv in string.Formatter().parse(s) if field is not None)
        for lang,data in catalogs.items():
            self.assertEqual(set(source),set(data),lang)
            for key,value in data.items():
                self.assertIsInstance(value,str);self.assertTrue(value.strip(),(lang,key))
                self.assertEqual(fields(key),fields(value),(lang,key))
        for path in (ROOT/'tiny2').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='_t' and node.args and isinstance(node.args[0],ast.Constant):
                    self.assertIn(node.args[0].value,source,(path.name,node.lineno))

    def test_persistence_requires_restart_and_is_scoped(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            i18n.configure(a,'de');i18n.save_language('pl')
            self.assertEqual(i18n.language(),'de')
            self.assertEqual(i18n.configure(a),'pl')
            with patch.dict(os.environ,{'LANGUAGE':'da_DK:en','LC_ALL':'fr_FR'}):
                self.assertEqual(i18n.configure(b),'da')
            self.assertEqual(json.loads((Path(a)/'language.json').read_text()),{'language':'pl'})
            self.assertFalse((Path(b)/'language.json').exists())
            self.assertEqual(i18n.configure(a,'es'),'es')
            self.assertEqual(i18n.configure(a),'pl')

    def test_locale_normalization_and_invalid_preferences(self):
        for env,expected in [({'LANG':'fr_FR.UTF-8'},'fr'),({'LANGUAGE':'xx:es-ES'},'es'),({'LANG':'C'},'en'),({},'en')]:
            self.assertEqual(i18n.detect_language(env),expected)
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LANGUAGE':'en'}):
            for value in ('{', '[]', '{"language":"../../secret"}', 'x'*1025):
                (Path(tmp)/'language.json').write_text(value)
                self.assertEqual(i18n.configure(tmp),'en')
            with self.assertRaises(ValueError):i18n.save_language('../../other',tmp)

    def test_translated_labels_do_not_change_wire_modes(self):
        original=dict(protocol.MODES);data=bytearray(60);data[0x18]=2;data[0x1c]=1
        for lang in i18n.LANGUAGES:
            i18n.configure(None,lang)
            self.assertEqual(protocol.MODES,original)
            self.assertEqual(protocol.status(data)['mode'],'Oberkörper')
            self.assertEqual(protocol.status(data)['fov'],'Weit')
            if lang!='de':self.assertNotEqual(i18n.tr('Oberkörper'),'Oberkörper')
            self.assertEqual(i18n.tr('Zoom: {v0:g} %',v0=42).count('42'),1)
            self.assertEqual(i18n.tr('My personal camera name'),'My personal camera name')

    def test_ai_language_request_and_local_guides(self):
        from tiny2.gwen import make_request
        for lang in i18n.LANGUAGES:
            i18n.configure(None,lang)
            request=make_request('test-model','test',b'\x89PNG\r\n\x1a\n','frame')
            self.assertIn('in '+i18n.LANGUAGE_NAMES[lang],request['messages'][0]['content'])
            path=i18n.manual_path();self.assertTrue(path.is_file(),path)
            self.assertIn('lang="'+lang+'"',path.read_text())
            self.assertTrue((ROOT/'docs'/('guide-'+lang+'.md')).is_file())

if __name__=='__main__':unittest.main()
