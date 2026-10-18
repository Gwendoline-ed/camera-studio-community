"""Check release boundaries without packaging user configuration or Git internals."""
import unittest
from pathlib import Path
from build import allowed_source

class ReleaseFilesTests(unittest.TestCase):
    def test_expected_source_included(self):
        for name in ('README.md','LICENSE','.gitignore','.github/workflows/ci.yml','tiny2/locales/fr.json','docs/guide-pl.html','tests/test_i18n.py'):
            self.assertTrue(allowed_source(Path(name)),name)
    def test_private_and_generated_files_excluded(self):
        for name in ('.git/config','api-keys.json','tiny2/api-keys.json','docs/.env','tiny2/__pycache__/app.pyc','dist/test.deb','tiny2/test.tinybook','docs/private.pem','../secret','/etc/passwd'):
            self.assertFalse(allowed_source(Path(name)),name)

if __name__=='__main__':unittest.main()
