"""Native GTK book, stylus, and independent scope flows with synthetic images."""
import io
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib,Gio
from gui_integration import SyntheticCamera,pump
from gui_gwen_share import capture
from tiny2.app import Studio
from tiny2.book_window import texture
from tiny2.bookscan import png_bytes,export_pdf,export_epub
from tiny2.overlays import fitted_rect
from tiny2.preview import Preview
from tiny2.scope_window import Source


def main():
    root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(1000,1400),'white');draw=ImageDraw.Draw(im)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',38)
    for i,line in enumerate(['Mein Testbuch','Eine kleine Geschichte','Bücher, Grüße und schöne Seiten.','Die zweite Seite folgt.']):draw.text((65,100+i*85),line,font=font,fill='black')
    png=png_bytes(im);photo=texture(png);png=bytes(photo.save_to_png_bytes().get_data());camera=SyntheticCamera()
    with tempfile.TemporaryDirectory() as tmp,patch('tiny2.app.device.connect',return_value=camera):
        app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None));app.register(None);app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            app.preview.start(None,test=True);pump(lambda:app.frames_seen>3)
            with patch.object(app,'camera_snapshot',return_value=photo):
                app.open_book();assert app.book_window,app.notice.get_text()
                book=app.book_window;pump(lambda:book.get_realized() and book.get_width()>0)
                book.on_camera_frame(photo);book.title_entry.set_text('Mein Testbuch');book.author_entry.set_text('GTK-Funktionstest')
                book.use_gwen.set_active(True)
                with patch('tiny2.book_window.GwenClient') as client:
                    client.return_value.page_corners.return_value=[[0,0],[1000,0],[1000,1000],[0,1000]]
                    book.capture_button.emit('clicked');pump(lambda:not book.busy)
                    assert book.pending_image and not book.project.pages(),book.status.get_text()
                    capture(book,root/'Buchscan-Seitenpruefung.png')
                # Draw on the reviewed frozen page, with real mouse gesture callbacks.
                book.draw_button.emit('clicked');assert app.drawing_windows,app.notice.get_text()
                ink=app.drawing_windows[-1];pump(lambda:ink.get_realized() and ink.overlay.get_width()>0)
                rx,ry,rw,rh=fitted_rect(ink.overlay.get_width(),ink.overlay.get_height(),1000,1400)
                ink.width.set_value(20)
                ink.mouse.emit('drag-begin',rx+rw*.15,ry+rh*.42)
                # Claiming a mouse gesture may cancel the competing stylus gesture.
                # That cancellation must not end the active mouse stroke.
                ink.stylus.emit('cancel',None)
                ink.mouse.emit('drag-update',rw*.6,0);ink.mouse.emit('drag-end',rw*.6,0)
                assert len(ink.ink.strokes)==1 and len(ink.ink.strokes[0]['points'])>=2,'mouse stroke was reduced to a dot'
                ink.undo();assert not ink.ink.strokes;ink.redo();assert len(ink.ink.strokes)==1
                # Pressure values are supplied through the same callbacks GTK uses.
                pen=SimpleNamespace(get_axis=lambda _:(True,.3),get_device_tool=lambda:None,set_state=lambda _:None)
                ink.choose_color('#00bfff');ink.stylus_down(pen,rx+rw*.15,ry+rh*.5)
                # Conversely, the mouse controller may cancel/end while a pen owns
                # the pointer sequence. Neither signal may finish the pen stroke.
                ink.mouse.emit('cancel',None);ink.mouse.emit('drag-end',0,0)
                pen.get_axis=lambda _:(True,.9);ink.stylus_move(pen,rx+rw*.75,ry+rh*.5);ink.stylus_up(pen,rx+rw*.8,ry+rh*.5)
                assert len(ink.ink.strokes[-1]['points'])>=3,'pen stroke was reduced to a dot'
                assert ink.ink.strokes[-1]['points'][0][2]==.3 and ink.ink.strokes[-1]['points'][-1][2]==.9
                capture(ink,root/'Zeichnen-Fenstertest.png');ink.apply();assert not app.drawing_windows
                assert book.pending_original==png and book.pending_image!=png
                book.accept_button.emit('clicked');pump(lambda:not book.busy,timeout=45)
                pages=book.project.pages();assert len(pages)==1 and 'Bücher' in pages[0]['text'],book.status.get_text()
                assert book.project.image(pages[0]['id'],original=True)==png
                book.text.get_buffer().set_text('Vom Nutzer korrigierter Buchtext mit Umlauten: Bücher.');book.save_text_button.emit('clicked')
                assert book.project.pages()[0]['text'].startswith('Vom Nutzer')
                # A stable image is captured once in automatic mode without Gwen review.
                book.use_gwen.set_active(False);book.mode.set_selected(1);book.auto_button.set_active(True)
                book.detector.last=None;book.detector.pause()
                with patch.object(book,'is_active',return_value=True):
                    for now in (10,11,13):
                        with patch('tiny2.book_window.time.monotonic',return_value=now):
                            app.last_frame=(photo,app.preview.generation,now);book.auto_tick()
                pump(lambda:not book.busy,timeout=45);assert len(book.project.pages())==2,book.status.get_text()
                book.auto_button.set_active(False)
                capture(book,root/'Buchscan-Fenstertest.png')
                # Native chooser response exports the chosen path in each format.
                for kind,suffix in [('project','tinybook'),('pdf','pdf'),('epub','epub')]:
                    path=root/('Buchscan-Test.'+suffix)
                    chooser=SimpleNamespace(get_file=lambda p=path:Gio.File.new_for_path(str(p)),destroy=lambda:None)
                    book.chosen(chooser,Gtk.ResponseType.ACCEPT,kind);pump(lambda:not book.busy,timeout=15)
                    assert path.is_file() and path.stat().st_size>0,book.status.get_text()
                # Failure on re-recognition must keep the user's existing text.
                before_text=book.project.pages()[1]['text']
                with patch('tiny2.book_window.recognize',side_effect=RuntimeError('Testfehler')):
                    book.ocr_selected();pump(lambda:not book.busy)
                assert book.project.pages()[1]['text']==before_text
                book.close();assert app.book_window is None
                # Edited frames are handed to Gwen without being replaced on Send.
                app.open_gwen();chat=app.gwen_window;pump(lambda:chat.get_realized())
                chat.draw_image();ink=app.drawing_windows[-1];pump(lambda:ink.get_realized())
                ink.ink.begin(100,100,(1,0,0,1),10);ink.ink.add(500,100);ink.ink.end();ink.apply()
                assert not chat.fresh_image.get_active()
                edited=chat.frame[0]
                with patch('tiny2.gwen_window.GwenClient') as client:
                    client.return_value.chat.return_value={'answer':'Geprüfte Zeichnung','markers':[],'note':''}
                    chat.entry.set_text('Was habe ich markiert?');chat.send();pump(lambda:not chat.busy)
                    assert client.return_value.chat.call_args.args[1]==edited
                chat.close()
            # Independent negotiated scope pipeline; no actual camera is opened.
            src=Source('/dev/video99','AmScope · Funktionstest');auto=Preview.start_auto
            with patch('tiny2.scope_window.sources',return_value=[src]),patch.object(Preview,'start_auto',lambda self,device,mode=None:auto(self,device,test=True,mode=mode)):
                app.open_scope();controls=app.scope_controls;pump(lambda:not controls.searching)
                channel=controls.channels[src.key]
                controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching)
                scope=channel.viewer;assert scope,controls.status.get_text()
                pump(lambda:scope.picture.get_paintable() is not None and scope.get_realized())
                assert not scope.get_decorated() and scope.get_child()==scope.picture
                assert scope.preview is not app.preview and app.preview.pipeline
                assert app.g13.scope_target() is channel, 'scope has its own input target'
                capture(scope,root/'Scope-Fenstertest.png')
                before=app.frames_seen;scope.close();pump(lambda:app.frames_seen>before)
                assert channel.viewer is None and app.preview.pipeline and not controls.rows[channel.source.key]['enabled'].get_active()
                controls.rows[channel.source.key]['enabled'].set_active(True);pump(lambda:not controls.searching)
                scope=channel.viewer;pump(lambda:scope.picture.get_paintable() is not None)
                scope.failed('Test: USB getrennt');assert channel.viewer is None and 'USB getrennt' in controls.status.get_text()
                controls.close();assert app.scope_controls is controls and not controls.get_visible()
            capture(app.window,root/'Studio-0.6-Fenstertest.png')
            print('PASS: GTK book review/annotation/OCR/edit, manual/automatic capture, project/PDF/EPUB export, stylus pressure callbacks, Gwen drawing frame, independent scope preview/unplug/cleanup.')
        finally:app.close();app.window.destroy()


if __name__=='__main__':main()
