#!/usr/bin/env python3
"""Build Community DEB and source ZIP. Never installs or uploads anything."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from tiny2 import __version__ as VERSION

ROOT=Path(__file__).resolve().parent
DEPENDENCIES=('python3 (>= 3.10), python3-gi, python3-cairo, python3-gi-cairo, python3-pil, '
              'libtesseract5, gir1.2-gtk-4.0 (>= 4.8), gir1.2-gdkpixbuf-2.0, '
              'gir1.2-pango-1.0, gir1.2-gstreamer-1.0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good')
DIRECTORIES={'tiny2','profiles','docs','tests','tools','.github'}
TOP_FILES={'build.py','Starten.sh','Camera-Studio-Community.desktop','.gitignore','.gitattributes',
           'README.txt','README.md','LICENSE','THIRD_PARTY_NOTICES.md','CONTRIBUTING.md',
           'CHANGELOG.md','SECURITY.md','SOURCES.txt','TESTERGEBNIS.txt'}
PRIVATE_FILES={'api-keys.json','integrations.json','language.json','presets.json','overlays.json','camera-profiles.json'}
BLOCKED_SUFFIXES={'.pyc','.pyo','.deb','.zip','.tinybook','.db','.sqlite','.sqlite3','.log','.key','.pem'}


def allowed_source(relative):
    relative=Path(relative)
    if relative.is_absolute() or '..' in relative.parts:return False
    if len(relative.parts)==1:return relative.name in TOP_FILES
    if relative.parts[0] not in DIRECTORIES:return False
    if any(part in ('__pycache__','.git','.venv','dist') or part.startswith('.env') for part in relative.parts):return False
    return relative.name not in PRIVATE_FILES and relative.suffix not in BLOCKED_SUFFIXES


def source_files():
    result=[]
    for path in sorted(ROOT.rglob('*')):
        if not allowed_source(path.relative_to(ROOT)):continue
        if path.is_symlink():raise ValueError('Symlink not allowed in release: '+str(path.relative_to(ROOT)))
        if path.is_file():result.append(path)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist');args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-B',str(ROOT/'tools/render_docs.py')],check=True)
    files=source_files();deb=out/f'camera-studio-community_{VERSION}_all.deb';archive_path=out/f'camera-studio-community-{VERSION}.zip'
    with tempfile.TemporaryDirectory(prefix='camera-studio-build-') as tmp:
        stage=Path(tmp);share=stage/'usr/share/camera-studio-community';docs=stage/'usr/share/doc/camera-studio-community'
        share.mkdir(parents=True);docs.mkdir(parents=True)
        for path in files:
            rel=path.relative_to(ROOT)
            if rel.parts[0] in ('tiny2','profiles'):dest=share/rel
            elif rel.parts[0]=='docs' or (path.name in TOP_FILES and path.suffix in ('.md','.txt')) or path.name=='LICENSE':dest=docs/rel
            else:continue
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        (docs/'copyright').write_text((ROOT/'LICENSE').read_text()+'\nThird-party notices:\n'+(ROOT/'THIRD_PARTY_NOTICES.md').read_text())
        binary=stage/'usr/bin/camera-studio-community';binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nset -eu\ncd /usr/share/camera-studio-community\nexec /usr/bin/python3 -B -m tiny2 "$@"\n');binary.chmod(0o755)
        desktop=stage/'usr/share/applications';desktop.mkdir(parents=True)
        shutil.copy2(ROOT/'Camera-Studio-Community.desktop',desktop/'camera-studio-community.desktop')
        control=stage/'DEBIAN';control.mkdir()
        (control/'control').write_text(f'''Package: camera-studio-community
Version: {VERSION}
Section: video
Priority: optional
Architecture: all
Maintainer: Camera Studio Community contributors
Depends: {DEPENDENCIES}
Recommends: gstreamer1.0-plugins-bad, gstreamer1.0-libav
Description: Independent Ubuntu camera studio with six interface languages
 Built-in Tiny 2 controller, camera profiles, capture modes and optional image AI.
 Offline guides in English, German, Danish, Spanish, Polish and French.
 Separate settings and launcher; does not replace Tiny 2 Studio.
''')
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(deb)],check=True)
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest_path=ROOT/'MANIFEST.json';manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in files+[manifest_path]:archive.write(path,Path('camera-studio-community')/path.relative_to(ROOT))
    (out/'SHA256SUMS-community.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in (deb,archive_path)))
    print(out)

if __name__=='__main__':main()
