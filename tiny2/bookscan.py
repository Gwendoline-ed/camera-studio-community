"""Persistent book pages, stable-image capture, perspective correction and exports."""
from .i18n import tr as _t
from contextlib import contextmanager
from datetime import datetime, timezone
from html import escape
import io
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from PIL import Image

MAX_PAGES=500
MAX_IMAGE=24*1024*1024


def open_image(png):
    if len(png)>MAX_IMAGE: raise ValueError(_t('Seitenbild ist zu groß.'))
    image=Image.open(io.BytesIO(png))
    if image.width*image.height>20_000_000: raise ValueError(_t('Höchstens 20 Megapixel pro Seite.'))
    return image.convert('RGB')


def png_bytes(image):
    out=io.BytesIO(); image.save(out,format='PNG'); return out.getvalue()


def validate_corners(points):
    if not isinstance(points,list) or len(points)!=4: raise ValueError(_t('Vier Seitenecken werden benötigt.'))
    if any(not isinstance(p,(list,tuple)) or len(p)!=2 or
           any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1000 for v in p) for p in points):
        raise ValueError(_t('Ungültige Seitenecken.'))
    cross=[]
    for i in range(4):
        a,b,c=points[i],points[(i+1)%4],points[(i+2)%4]
        cross.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
    area=sum(points[i][0]*points[(i+1)%4][1]-points[i][1]*points[(i+1)%4][0] for i in range(4))/2
    if min(cross)<=100 or area<50000: raise ValueError(_t('Seitenränder unplausibel. Bitte die vier Ecken neu setzen.'))
    return points


def rectify(png,points):
    points=validate_corners(points); image=open_image(png)
    src=[(x*(image.width-1)/1000,y*(image.height-1)/1000) for x,y in points]
    width=round((math.dist(src[0],src[1])+math.dist(src[3],src[2]))/2)
    height=round((math.dist(src[0],src[3])+math.dist(src[1],src[2]))/2)
    if min(width,height)<32 or width*height>20_000_000: raise ValueError(_t('Die erkannte Seite ist zu klein oder zu groß.'))
    rows=[]
    for (u,v),(x,y) in zip([(0,0),(width-1,0),(width-1,height-1),(0,height-1)],src):
        rows.extend([[u,v,1,0,0,0,-x*u,-x*v,x],[0,0,0,u,v,1,-y*u,-y*v,y]])
    for col in range(8):
        pivot=max(range(col,8),key=lambda r:abs(rows[r][col]))
        rows[col],rows[pivot]=rows[pivot],rows[col]
        scale=rows[col][col]
        if abs(scale)<1e-10: raise ValueError(_t('Seitenränder sind nicht eindeutig.'))
        rows[col]=[v/scale for v in rows[col]]
        for r in range(8):
            if r!=col:
                factor=rows[r][col]; rows[r]=[a-factor*b for a,b in zip(rows[r],rows[col])]
    coefficients=[row[-1] for row in rows]
    return png_bytes(image.transform((width,height),Image.Transform.PERSPECTIVE,coefficients,
                                    resample=Image.Resampling.BICUBIC,fillcolor='white'))


def fingerprint(png):
    values=list(open_image(png).convert('L').resize((64,64)).getdata())
    mean=sum(values)/len(values)
    return tuple(v-mean for v in values)


def difference(a,b): return sum(abs(x-y) for x,y in zip(a,b))/len(a)


class AutoCapture:
    def __init__(self): self.last=self.stable=None; self.since=None
    def pause(self): self.stable=None; self.since=None
    def accept(self, sample): self.last=sample; self.pause()
    def observe(self,sample,now,delay=2,threshold=6):
        if self.stable is None or difference(sample,self.stable)>2.5:
            self.stable=sample; self.since=now; return False
        return now-self.since>=delay and (self.last is None or difference(sample,self.last)>=threshold)


class BookProject:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        existing=self.path.exists() and self.path.stat().st_size>0
        with self.connection() as db:
            if existing:
                try: kind=db.execute("SELECT value FROM meta WHERE key='kind'").fetchone()
                except sqlite3.Error as error: raise ValueError(_t('Keine Tiny-2-Buchprojektdatei.')) from error
                if kind!=('tiny2-book-v1',): raise ValueError(_t('Unbekanntes Buchprojektformat.'))
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS pages (id TEXT PRIMARY KEY, position INTEGER, original BLOB, image BLOB, text TEXT, confidence INTEGER, error TEXT, removed INTEGER DEFAULT 0)')
            db.execute("INSERT OR IGNORE INTO meta VALUES ('title',?)", (_t('Mein Buch'),))
            db.execute("INSERT OR IGNORE INTO meta VALUES ('author','')")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('kind','tiny2-book-v1')")
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=10); db.execute('PRAGMA trusted_schema=OFF')
        try:
            with db: yield db
        finally: db.close()
    def meta(self):
        with self.connection() as db: return dict(db.execute('SELECT key,value FROM meta'))
    def set_meta(self,title,author):
        with self.connection() as db:
            db.executemany('INSERT OR REPLACE INTO meta VALUES (?,?)',[('title',title[:250]),('author',author[:250])])
    def pages(self):
        with self.connection() as db:
            return [dict(id=r[0],text=r[1] or '',confidence=r[2],error=r[3] or '') for r in
                    db.execute('SELECT id,text,confidence,error FROM pages WHERE removed=0 ORDER BY position')]
    def image(self,page_id,original=False):
        column='original' if original else 'image'
        with self.connection() as db:
            row=db.execute('SELECT '+column+' FROM pages WHERE id=?',(page_id,)).fetchone()
        if not row: raise ValueError(_t('Seite nicht gefunden.'))
        return bytes(row[0])
    def add(self,original,image):
        open_image(original); open_image(image)
        with self.connection() as db:
            count=db.execute('SELECT COUNT(*) FROM pages WHERE removed=0').fetchone()[0]
            if count>=MAX_PAGES: raise ValueError(_t('Bitte nach 500 Seiten ein weiteres Buch beginnen.'))
            page_id=uuid.uuid4().hex
            position=db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM pages').fetchone()[0]
            db.execute('INSERT INTO pages VALUES (?,?,?,?,?,?,?,0)',
                       (page_id,position,original,image,'',None,'',))
        return page_id
    def text(self,page_id,text,confidence=None,error=''):
        with self.connection() as db:
            db.execute('UPDATE pages SET text=?,confidence=?,error=? WHERE id=?',(text[:150000],confidence,error[:500],page_id))
    def reorder(self,page_id,delta):
        pages=self.pages(); ids=[p['id'] for p in pages]; index=ids.index(page_id)
        target=max(0,min(len(ids)-1,index+delta)); ids[index],ids[target]=ids[target],ids[index]
        with self.connection() as db:
            db.executemany('UPDATE pages SET position=? WHERE id=?',enumerate(ids))
    def remove(self,page_id):
        with self.connection() as db: db.execute('UPDATE pages SET removed=1 WHERE id=?',(page_id,))
    def save_as(self,path):
        path=Path(path)
        if path.resolve()==self.path.resolve(): return
        with atomic_output(path) as temp:
            with self.connection() as db:
                other=sqlite3.connect(temp)
                try: db.backup(other)
                finally: other.close()


@contextmanager
def atomic_output(path):
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent); os.close(fd)
    temp=Path(name)
    try: yield temp; temp.replace(path)
    finally: temp.unlink(missing_ok=True)


def check_cancel(cancel):
    if cancel is not None and cancel.is_set(): raise InterruptedError(_t('Export abgebrochen.'))


def export_pdf(project,path,cancel=None):
    import cairo
    pages=project.pages()
    if not pages: raise ValueError(_t('Noch keine Buchseiten vorhanden.'))
    with atomic_output(path) as temp:
        surface=cairo.PDFSurface(str(temp),595,842)
        try:
            surface.set_metadata(cairo.PDF_METADATA_TITLE,project.meta()['title'])
            cr=cairo.Context(surface)
            for page in pages:
                check_cancel(cancel)
                picture=cairo.ImageSurface.create_from_png(io.BytesIO(project.image(page['id'])))
                w,h=picture.get_width(),picture.get_height()
                pw,ph=(842,595) if w>h else (595,842); surface.set_size(pw,ph)
                cr.set_source_rgb(1,1,1); cr.paint(); scale=min((pw-24)/w,(ph-24)/h)
                cr.save(); cr.translate((pw-w*scale)/2,(ph-h*scale)/2); cr.scale(scale,scale)
                cr.set_source_surface(picture,0,0); cr.paint(); cr.restore(); cr.show_page()
        finally: surface.finish()
        check_cancel(cancel)


def xml_text(value):
    return escape(''.join(c for c in str(value) if c in '\t\n\r' or 0x20<=ord(c)<=0xd7ff or 0xe000<=ord(c)<=0xfffd or 0x10000<=ord(c)<=0x10ffff))


def xhtml(title,body):
    return ('<?xml version="1.0" encoding="utf-8"?>'
      '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="de" lang="de">'
      '<head><title>'+xml_text(title)+'</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body>'+body+'</body></html>')


def export_epub(project,path,cancel=None):
    pages=project.pages(); meta=project.meta()
    if not pages: raise ValueError(_t('Noch keine Buchseiten vorhanden.'))
    identifier='urn:uuid:'+str(uuid.uuid4()); manifest=[]; spine=[]; nav=[]
    with atomic_output(path) as temp:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
            z.writestr('META-INF/container.xml','<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            z.writestr('EPUB/style.css','body{font-family:serif;line-height:1.5} img{max-width:100%;height:auto} p{white-space:pre-wrap} aside{font-size:.8em}')
            for n,page in enumerate(pages,1):
                check_cancel(cancel)
                text=page['text'].strip(); image=f'images/p{n}.png'; chapter=f'p{n}.xhtml'; scan=f'scan{n}.xhtml'
                z.writestr('EPUB/'+image,project.image(page['id']))
                body='<h2>'+xml_text(_t('Seite '))+str(n)+'</h2>'
                if text: body+=''.join('<p>'+xml_text(p)+'</p>' for p in text.split('\n\n') if p.strip())
                else: body+='<p>'+xml_text(_t('Kein Text erkannt. Das Seitenbild bleibt erhalten.'))+'</p><img src="'+image+'" alt="Scan '+str(n)+'"/>'
                body+='<aside><a href="'+scan+'">'+xml_text(_t('Seitenbild ansehen'))+'</a></aside>'
                z.writestr('EPUB/'+chapter,xhtml(_t('Seite ')+str(n),body))
                z.writestr('EPUB/'+scan,xhtml(_t('Seitenbild ')+str(n),'<p><a href="'+chapter+'">'+xml_text(_t('Zurück zum Text'))+'</a></p><img src="'+image+'" alt="Scan '+str(n)+'"/>'))
                manifest.extend([f'<item id="p{n}" href="{chapter}" media-type="application/xhtml+xml"/>',f'<item id="s{n}" href="{scan}" media-type="application/xhtml+xml"/>',f'<item id="i{n}" href="{image}" media-type="image/png"/>'])
                spine.append(f'<itemref idref="p{n}"/>'); nav.append(f'<li><a href="{chapter}">{xml_text(_t("Seite "))}{n}</a></li>')
            z.writestr('EPUB/nav.xhtml',xhtml(meta['title'],'<nav epub:type="toc" id="toc"><h1>'+xml_text(meta['title'])+'</h1><ol>'+''.join(nav)+'</ol></nav>'))
            manifest.extend(['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>','<item id="css" href="style.css" media-type="text/css"/>'])
            modified=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            z.writestr('EPUB/package.opf','<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">'+identifier+'</dc:identifier><dc:title>'+xml_text(meta['title'])+'</dc:title><dc:language>de</dc:language><dc:creator>'+xml_text(meta['author'])+'</dc:creator><meta property="dcterms:modified">'+modified+'</meta></metadata><manifest>'+''.join(manifest)+'</manifest><spine>'+''.join(spine)+'</spine></package>')
        check_cancel(cancel)
