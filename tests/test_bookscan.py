import io,json,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from PIL import Image,ImageDraw
from tiny2.bookscan import *
from tiny2.gwen import GwenClient
from tiny2.drawing import Ink


def page(color='white'):
    image=Image.new('RGB',(200,300),color);ImageDraw.Draw(image).rectangle((20,25,180,270),outline='black',width=3)
    return png_bytes(image)


class BookTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.book=BookProject(self.root/'book.tinybook');self.png=page()
    def tearDown(self):self.tmp.cleanup()
    def test_page_order_removed_page_and_original_preservation(self):
        a=self.book.add(self.png,page('red'));b=self.book.add(self.png,page('blue'))
        self.book.text(a,'Äpfel & <Text>',92);self.book.reorder(b,-1)
        self.assertEqual([p['id'] for p in self.book.pages()],[b,a])
        self.book.remove(b);c=self.book.add(self.png,page('green'))
        self.assertEqual([p['id'] for p in self.book.pages()],[a,c])
        self.assertEqual(self.book.image(a,True),self.png)
        self.book.save_as(self.root/'copy.tinybook')
        self.assertEqual(BookProject(self.root/'copy.tinybook').pages()[0]['text'],'Äpfel & <Text>')
    def test_pdf_epub_have_pages_order_text_and_images(self):
        a=self.book.add(self.png,self.png);b=self.book.add(self.png,self.png)
        self.book.text(a,'Erste Seite & <Buch>\n\nGrüße');self.book.set_meta('Äpfel & Bücher','D. Test')
        export_pdf(self.book,self.root/'book.pdf');self.assertTrue((self.root/'book.pdf').read_bytes().startswith(b'%PDF'))
        export_epub(self.book,self.root/'book.epub')
        with zipfile.ZipFile(self.root/'book.epub') as z:
            self.assertEqual(z.infolist()[0].filename,'mimetype');self.assertEqual(z.infolist()[0].compress_type,0)
            for name in z.namelist():
                if name.endswith(('.xhtml','.opf','.xml')):ET.fromstring(z.read(name))
            self.assertIn('Grüße',z.read('EPUB/p1.xhtml').decode());self.assertIn('Kein Text erkannt',z.read('EPUB/p2.xhtml').decode())
            self.assertEqual(z.read('EPUB/images/p1.png'),self.png)
            root=ET.fromstring(z.read('EPUB/package.opf'));ns={'o':'http://www.idpf.org/2007/opf'}
            self.assertEqual([p.get('idref') for p in root.findall('o:spine/o:itemref',ns)],['p1','p2'])
    def test_cancel_export_keeps_existing_file(self):
        self.book.add(self.png,self.png);cancel=threading.Event();cancel.set()
        target=self.root/'book.epub';target.write_bytes(b'old')
        with self.assertRaises(InterruptedError):export_epub(self.book,target,cancel)
        self.assertEqual(target.read_bytes(),b'old')
        self.assertEqual(list(self.root.glob('.book.epub-*')),[])
    def test_reject_unrelated_database_without_altering_it(self):
        import sqlite3
        p=self.root/'other.sqlite'
        with sqlite3.connect(p) as db:db.execute('CREATE TABLE unrelated (x)')
        before=p.read_bytes()
        with self.assertRaises(ValueError):BookProject(p)
        self.assertEqual(before,p.read_bytes())
    def test_perspective_corrects_corners_and_rejects_crossings(self):
        image=Image.new('RGB',(400,400),'black');ImageDraw.Draw(image).polygon([(60,20),(350,60),(300,370),(40,340)],fill='white')
        result=open_image(rectify(png_bytes(image),[[150,50],[875,150],[750,925],[100,850]]))
        self.assertEqual(result.getpixel((result.width//2,result.height//2)),(255,255,255))
        for bad in ([[0,0],[1000,1000],[1000,0],[0,1000]],[[0,0],[1,0],[1,1],[0,1]],[[0,0],[1001,0],[1000,1000],[0,1000]]):
            with self.assertRaises(ValueError):rectify(self.png,bad)
    def test_auto_waits_for_stability_and_does_not_capture_same_page_twice(self):
        auto=AutoCapture();a=(0,0,0,0);b=(20,-20,20,-20)
        self.assertFalse(auto.observe(a,0));self.assertFalse(auto.observe(a,1));self.assertTrue(auto.observe(a,2))
        auto.accept(a);auto.observe(a,3);self.assertFalse(auto.observe(a,6))
        auto.observe(b,7);auto.observe(a,8);self.assertFalse(auto.observe(a,11))
        auto.observe(b,12);self.assertTrue(auto.observe(b,14));auto.pause();self.assertFalse(auto.observe(b,20))
    def test_gwen_only_returns_checked_geometry_for_exact_frame(self):
        client=GwenClient();good=dict(frame_id='f',uncertain=False,corners=[[0,0],[1000,0],[1000,1000],[0,1000]])
        for changes,valid in [({},True),({'frame_id':'wrong'},False),({'uncertain':True},False),({'corners':[[0,0]]},False)]:
            reply={'done':True,'message':{'content':json.dumps({**good,**changes})}}
            with patch.object(client,'request',side_effect=[{'capabilities':['vision']},reply]):
                if valid:self.assertEqual(client.page_corners(self.png,'f'),good['corners'])
                else:
                    with self.assertRaises(ValueError):client.page_corners(self.png,'f')


class DrawingTests(unittest.TestCase):
    def test_pressure_width_and_background_preserved_by_erase_undo(self):
        ink=Ink();original=page();ink.begin(50,60,(1,0,0,1),20,.5);ink.add(150,60,1);ink.end()
        drawn=ink.render(original);self.assertNotEqual(drawn,original)
        image=open_image(drawn);self.assertEqual(image.getpixel((100,60)),(255,0,0))
        self.assertEqual(image.getpixel((100,100)),(255,255,255))
        ink.begin(100,60,(0,0,0,1),5,erase=True);ink.end();self.assertFalse(ink.strokes)
        self.assertEqual(open_image(ink.render(original)).tobytes(),open_image(original).tobytes())
        ink.undo();self.assertEqual(len(ink.strokes),1);ink.redo();self.assertFalse(ink.strokes)
    def test_clear_and_undo_preserve_multiple_strokes(self):
        ink=Ink()
        for y in (40,80):ink.begin(30,y,(0,0,1,1),4);ink.add(160,y);ink.end()
        ink.clear();self.assertFalse(ink.strokes);ink.undo();self.assertEqual(len(ink.strokes),2)
        ink.undo();self.assertEqual(len(ink.strokes),1)


if __name__=='__main__':unittest.main()
