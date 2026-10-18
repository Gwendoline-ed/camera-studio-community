"""Camera book capture with manual/automatic mode and reviewed KI correction."""
from .i18n import tr as _t
import io
import os
import sqlite3
from pathlib import Path
import threading
import time
import uuid
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk, GLib
from .bookscan import BookProject, AutoCapture, fingerprint, open_image, png_bytes, rectify, export_pdf, export_epub
from .book_ocr import recognize
from .gwen import GwenClient
from .ai_picker import AIPicker
from .gwen_window import Markers, button
from .overlays import fitted_rect


def texture(png): return Gdk.Texture.new_from_bytes(GLib.Bytes.new(png))


def column(spacing=8): return Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=spacing)


class BookWindow(Gtk.ApplicationWindow):
    def __init__(self,app):
        super().__init__(application=app,title=_t('Buchscan · Camera Studio Community'))
        self.app=app; self.closed=self.busy=False; self.cancel=threading.Event(); self.client=None
        self.pending_original=self.pending_source=self.pending_image=None; self.replace_id=None
        self.selected=None; self.selecting=False; self.picking=False; self.corners=[]; self.dialogs=[]
        self.detector=AutoCapture(); self.last_auto=0; self.sample=None; self.latest=None
        self.root=(Path(app.args.config_dir)/'books' if app.args.config_dir else
            Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'camera-studio-community/books')
        self.root.mkdir(parents=True,exist_ok=True)
        pointer=self.root/'current.txt'
        try:
            path=Path(pointer.read_text().strip())
            self.project=BookProject(path)
        except (OSError,ValueError,sqlite3.DatabaseError): self.project=BookProject(self.root/(uuid.uuid4().hex+'.tinybook'))
        pointer.write_text(str(self.project.path))
        self.set_default_size(1280,850)
        self.connect('close-request',self.close_scan)
        self.connect('notify::is-active',app.g13.focus_changed)
        keys=Gtk.EventControllerKey(); keys.connect('key-pressed',self.key); self.add_controller(keys)
        header=Gtk.HeaderBar(); header.set_title_widget(Gtk.Label(label=_t('Buchscan · PDF und EPUB'))); self.set_titlebar(header)
        outer=column(10)
        for side in ('top','bottom','start','end'): getattr(outer,'set_margin_'+side)(12)
        self.set_child(outer)
        meta=Gtk.Box(spacing=8)
        self.title_entry=Gtk.Entry(placeholder_text=_t('Buchtitel'),hexpand=True,max_length=250)
        self.author_entry=Gtk.Entry(placeholder_text=_t('Autor/in'),hexpand=True,max_length=250)
        meta.append(self.title_entry); meta.append(self.author_entry); outer.append(meta)
        toolbar=Gtk.Box(spacing=8); self.project_buttons=[]
        for text,callback in [(_t('Neues Buch'),self.new_book),(_t('Projekt öffnen …'),lambda:self.choose('open')),
                (_t('Projekt speichern …'),lambda:self.choose('project')),(_t('PDF exportieren …'),lambda:self.choose('pdf')),
                (_t('EPUB exportieren …'),lambda:self.choose('epub'))]:
            b=button(text,callback); toolbar.append(b); self.project_buttons.append(b)
        outer.append(toolbar)
        body=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL); body.set_position(440); body.set_vexpand(True); outer.append(body)
        left=column(); body.set_start_child(left); body.set_shrink_start_child(True)
        left.append(Gtk.Label(label=_t('Kamera · eine Buchseite pro Aufnahme'),xalign=0))
        self.live=Gtk.Picture(); self.live.set_can_shrink(True); self.live.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.live.set_size_request(280,180); self.live.set_vexpand(True); self.live.add_css_class('preview'); left.append(self.live)
        row=Gtk.Box(spacing=8)
        self.mode=Gtk.DropDown.new_from_strings([_t('Manuell'),_t('Automatisch')]); self.mode.connect('notify::selected',self.mode_changed)
        row.append(self.mode)
        self.capture_button=button(_t('Seite aufnehmen'),self.capture_page); row.append(self.capture_button); left.append(row)
        self.auto_button=Gtk.ToggleButton(label=_t('Automatik starten')); self.auto_button.connect('toggled',self.auto_changed); left.append(self.auto_button)
        self.auto_options=Gtk.Box(spacing=8)
        self.auto_options.append(Gtk.Label(label=_t('Ruhezeit')))
        self.delay=Gtk.SpinButton.new_with_range(1,5,.5); self.delay.set_value(2); self.delay.set_digits(1)
        self.auto_options.append(self.delay); self.auto_options.append(Gtk.Label(label=_t('Sekunden')))
        left.append(self.auto_options)
        self.sensitivity=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,3,18,1)
        self.sensitivity.set_value(6); self.sensitivity.set_tooltip_text(_t('Seitenwechsel-Schwelle: höher = weniger empfindlich'))
        left.append(self.sensitivity)
        self.use_gwen=Gtk.CheckButton(label=_t('Neue Aufnahmen mit ausgewählter KI begradigen'),active=False);left.append(self.use_gwen)
        self.ai_picker=AIPicker(app,lambda _:self.use_gwen.set_active(False),history=False);left.append(self.ai_picker)
        self.g13_button=app.g13.make_toggle(short=True); left.append(self.g13_button)
        left.append(Gtk.Label(label=_t('G16: aufnehmen · G17: geprüfte Seite übernehmen\nAutomatik pausiert während der Seitenprüfung.'),xalign=0,wrap=True))
        self.auto_status=Gtk.Label(label=_t('Manuelle Aufnahme bereit.'),xalign=0,wrap=True); left.append(self.auto_status)
        hint=Gtk.Label(label=_t('Für kleine Schrift 1080p oder 4K in der Hauptansicht wählen. Kamera ruhig halten und die ganze Seite gleichmäßig beleuchten.'),xalign=0,wrap=True)
        hint.add_css_class('subtitle'); left.append(hint)
        right=Gtk.Box(spacing=10); right.set_margin_start(10); body.set_end_child(right); body.set_shrink_end_child(True)
        self.page_list=Gtk.ListBox(); self.page_list.connect('row-selected',self.select_page)
        listing=Gtk.ScrolledWindow(); listing.set_min_content_width(115); listing.set_child(self.page_list); right.append(listing)
        detail=column(); detail.set_hexpand(True); right.append(detail)
        self.page_heading=Gtk.Label(label=_t('Noch keine Seiten'),xalign=0); detail.append(self.page_heading)
        self.review=Gtk.Overlay(); self.review.add_css_class('preview'); self.review.set_vexpand(True)
        self.picture=Gtk.Picture(); self.picture.set_can_shrink(True); self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_size_request(280,220); self.review.set_child(self.picture)
        self.points=Markers(); self.review.add_overlay(self.points); detail.append(self.review)
        click=Gtk.GestureClick.new(); click.set_button(1); click.connect('pressed',self.pick_corner); self.review.add_controller(click)
        self.original_button=Gtk.CheckButton(label=_t('Original zum Vergleich')); self.original_button.connect('toggled',lambda _:self.show_pending()); detail.append(self.original_button)
        row=Gtk.Box(spacing=6)
        self.correct_button=button(_t('Mit KI begradigen'),self.correct)
        self.corners_button=button(_t('4 Ecken setzen'),self.pick_start)
        self.rotate_button=button(_t('↻ Drehen'),self.rotate)
        for b in (self.correct_button,self.corners_button,self.rotate_button):row.append(b)
        detail.append(row); row=Gtk.Box(spacing=6)
        self.accept_button=button(_t('Seite übernehmen'),self.accept_pending); self.accept_button.add_css_class('suggested-action')
        self.discard_button=button(_t('Verwerfen'),self.discard_pending)
        self.cancel_button=button(_t('Abbrechen'),self.cancel_work)
        for b in (self.accept_button,self.discard_button,self.cancel_button):row.append(b)
        self.draw_button=button(_t('Zeichnen'),self.draw_page);row.append(self.draw_button)
        detail.append(row)
        row=Gtk.Box(spacing=6); self.page_buttons=[]
        for text,callback in [('↑',lambda:self.move(-1)),('↓',lambda:self.move(1)),(_t('Entfernen'),self.remove),
                              (_t('Bearbeiten'),self.edit_page),(_t('Text erkennen'),self.ocr_selected)]:
            b=button(text,callback); row.append(b); self.page_buttons.append(b)
        detail.append(row)
        self.text=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text.set_top_margin(6); self.text.set_left_margin(8)
        scroll=Gtk.ScrolledWindow(); scroll.set_min_content_height(115); scroll.set_child(self.text); detail.append(scroll)
        self.save_text_button=button(_t('Textkorrektur speichern'),self.save_text); detail.append(self.save_text_button)
        self.status=Gtk.Label(label=_t('Seiten werden lokal als Buchprojekt gesichert.'),xalign=0,wrap=True)
        self.status.add_css_class('notice'); outer.append(self.status)
        self.load_project(); self.mode_changed(); self.timer=GLib.timeout_add(400,self.auto_tick)

    def key(self,_c,key,*_):
        if key==Gdk.KEY_Escape:
            self.auto_button.set_active(False); self.app.stop(); return True
        return False

    def load_project(self):
        meta=self.project.meta(); self.title_entry.set_text(meta['title']); self.author_entry.set_text(meta['author'])
        self.selected=None; self.refresh_pages()
        draft=self.project.path.with_suffix('.draft.png')
        if draft.is_file():
            self.pending_original=self.pending_source=self.pending_image=draft.read_bytes()
            self.show_pending(); self.status.set_text(_t('Nicht übernommene Aufnahme wiederhergestellt. Bitte prüfen.')); self.refresh()

    def save_meta(self): self.project.set_meta(self.title_entry.get_text().strip() or _t('Mein Buch'),self.author_entry.get_text().strip())

    def new_book(self):
        if self.busy or self.pending_image: return
        self.save_text(); self.save_meta(); self.auto_button.set_active(False)
        self.project=BookProject(self.root/(uuid.uuid4().hex+'.tinybook'))
        (self.root/'current.txt').write_text(str(self.project.path)); self.detector=AutoCapture(); self.load_project()

    def refresh(self):
        pending=self.pending_image is not None; ready=not self.busy and not self.closed
        self.ai_picker.set_sensitive(ready and not self.auto_button.get_active())
        self.use_gwen.set_sensitive(ready and not self.auto_button.get_active())
        self.capture_button.set_sensitive(ready and not pending)
        for b in (self.correct_button,self.corners_button,self.rotate_button,self.discard_button): b.set_sensitive(ready and pending)
        self.accept_button.set_sensitive(ready and pending and not self.picking)
        self.cancel_button.set_sensitive(self.busy)
        self.draw_button.set_sensitive(ready and pending)
        self.original_button.set_sensitive(pending)
        self.page_list.set_sensitive(ready and not pending)
        for b in self.project_buttons:b.set_sensitive(ready and not pending)
        for b in self.page_buttons:b.set_sensitive(ready and not pending and self.selected is not None)
        self.save_text_button.set_sensitive(ready and not pending and self.selected is not None)
        self.text.set_editable(ready and not pending and self.selected is not None)

    def refresh_pages(self,select=None):
        self.selecting=True
        while self.page_list.get_first_child():self.page_list.remove(self.page_list.get_first_child())
        pages=self.project.pages(); target=None
        for index,page in enumerate(pages,1):
            row=Gtk.ListBoxRow(); row.page_id=page['id']
            label=Gtk.Label(label=_t('Seite {v0}\n', v0=index)+(_t('Text ✓') if page['text'] else _t('Bild')),xalign=0)
            for side in ('top','bottom','start','end'):getattr(label,'set_margin_'+side)(8)
            row.set_child(label); self.page_list.append(row)
            if page['id']==select:target=row
        self.selecting=False
        if target is None:target=self.page_list.get_row_at_index(0)
        if target:self.page_list.select_row(target)
        else:self.selected=None; self.picture.set_paintable(None); self.text.get_buffer().set_text('')
        self.page_heading.set_text(_t('{v0} Buchseiten', v0=len(pages))); self.refresh()

    def select_page(self,_list,row):
        if self.selecting or self.pending_image is not None or row is None:return
        self.save_text(); self.selected=row.page_id
        self.picture.set_paintable(texture(self.project.image(self.selected)))
        page=next(p for p in self.project.pages() if p['id']==self.selected)
        self.text.get_buffer().set_text(page['text']); self.points.markers=[]; self.points.queue_draw()
        self.status.set_text(page['error'] or (_t('Texterkennung: {v0} % · bitte prüfen.', v0=page["confidence"]) if page['confidence'] is not None else _t('Seitenbild lokal gespeichert.')))
        self.refresh()

    def save_text(self):
        if self.selected and self.pending_image is None:
            buffer=self.text.get_buffer(); text=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False)
            old=next((p for p in self.project.pages() if p['id']==self.selected),None)
            if old and text!=old['text']:self.project.text(self.selected,text,old['confidence'])

    def move(self,delta):
        if self.selected:self.save_text(); self.project.reorder(self.selected,delta); self.refresh_pages(self.selected)

    def remove(self):
        if self.selected:self.project.remove(self.selected); self.selected=None; self.refresh_pages()

    def on_camera_frame(self,frame):
        if not self.closed:self.latest=frame; self.live.set_paintable(frame)

    def mode_changed(self,*_):
        auto=self.mode.get_selected()==1
        self.auto_button.set_visible(auto); self.auto_options.set_visible(auto); self.sensitivity.set_visible(auto)
        if not auto:self.auto_button.set_active(False)
        self.detector.pause()

    def auto_changed(self,*_):
        self.auto_button.set_label(_t('Automatik pausieren') if self.auto_button.get_active() else _t('Automatik starten'))
        self.detector.pause()
        self.auto_status.set_text(_t('Warte auf ein ruhiges Seitenbild …') if self.auto_button.get_active() else _t('Automatik pausiert.'))
        self.refresh()

    def auto_tick(self):
        if self.closed:return False
        if not self.auto_button.get_active():return True
        if self.busy or self.pending_image or not self.is_active() or self.app.busy or self.app.manual_drag.active:
            self.detector.pause(); return True
        try:
            frame=self.app.last_frame
            if not self.app.preview.pipeline or frame is None or frame[1]!=self.app.preview.generation or time.monotonic()-frame[2]>2:
                self.detector.pause(); self.auto_status.set_text(_t('Bitte eine laufende Kameravorschau starten.'));return True
            png=bytes(frame[0].save_to_png_bytes().get_data()); sample=fingerprint(png)
            if self.detector.observe(sample,time.monotonic(),self.delay.get_value(),self.sensitivity.get_value()):
                self.capture_page(automatic=True,png=png,sample=sample)
            else:self.auto_status.set_text(_t('Warte auf Seitenwechsel und ruhiges Bild …'))
        except Exception as error:self.auto_button.set_active(False);self.status.set_text(str(error))
        return True

    def capture_page(self,automatic=False,png=None,sample=None):
        if self.busy or self.pending_image is not None:return
        try:
            self.save_text(); self.save_meta()
            if png is None:png=bytes(self.app.camera_snapshot().save_to_png_bytes().get_data())
            open_image(png); self.app.g13.suspend_motion()
            self.detector.accept(sample if sample is not None else fingerprint(png))
            self.pending_original=self.pending_source=self.pending_image=png; self.replace_id=None
            self.project.path.with_suffix('.draft.png').write_bytes(png)
            self.original_button.set_active(False); self.show_pending(); self.refresh()
            if self.use_gwen.get_active():self.correct()
            elif automatic:self.accept_pending()
            else:self.status.set_text(_t('Aufnahme prüfen und Seite übernehmen.'))
        except Exception as error:self.status.set_text(str(error))

    def show_pending(self):
        if self.pending_image is None:return
        image=self.pending_source if self.original_button.get_active() else self.pending_image
        self.picture.set_paintable(texture(image)); im=open_image(self.pending_source)
        self.points.source_size=im.size; self.points.set_visible(self.original_button.get_active())
        self.page_heading.set_text(_t('Aufnahme prüfen · noch nicht im Buch'))

    def correct(self):
        if self.pending_source is None or self.busy:return
        source=self.pending_source; self.picking=False; self.points.markers=[]; self.points.queue_draw()
        # Only a smaller analysis image goes to Gwen. Rectification uses the full original.
        small=open_image(source); small.thumbnail((1600,1600)); analysis=png_bytes(small)
        try:
            client=GwenClient(self.ai_picker.provider);client.configured()
        except (OSError,ValueError,RuntimeError) as error:self.status.set_text(str(error));return
        self.client=client;frame_id=uuid.uuid4().hex
        self.ai_picker.update_notice();self.status.set_text(self.ai_picker.label+_t(' sucht die Seitenränder …'))
        def work():
            corners=client.page_corners(analysis,frame_id); return rectify(source,corners),corners
        def done(result):
            self.pending_image,self.corners=result
            self.points.markers=[dict(label=str(i+1),x=p[0],y=p[1]) for i,p in enumerate(self.corners)]
            self.points.queue_draw(); self.original_button.set_active(False); self.show_pending()
            self.status.set_text(_t('Begradigte Seite prüfen. Bei Bedarf Ecken nachsetzen; dann übernehmen.'))
        self.work(work,done)

    def pick_start(self):
        self.picking=True; self.corners=[]; self.points.markers=[]; self.points.queue_draw()
        self.original_button.set_active(True); self.show_pending();self.refresh()
        self.status.set_text(_t('Vier Ecken anklicken: oben links → oben rechts → unten rechts → unten links.'))

    def pick_corner(self,_gesture,_n,x,y):
        if not self.picking or self.busy:return
        im=open_image(self.pending_source); rx,ry,rw,rh=fitted_rect(self.review.get_width(),self.review.get_height(),*im.size)
        if not rw or not rh or not rx<=x<=rx+rw or not ry<=y<=ry+rh:return
        self.corners.append([(x-rx)*1000/rw,(y-ry)*1000/rh])
        self.points.markers=[dict(label=str(i+1),x=p[0],y=p[1]) for i,p in enumerate(self.corners)]; self.points.queue_draw()
        if len(self.corners)==4:
            self.picking=False
            try:
                self.pending_image=rectify(self.pending_source,self.corners)
                self.original_button.set_active(False);self.show_pending();self.status.set_text(_t('Korrektur prüfen und Seite übernehmen.'))
            except Exception as error:self.status.set_text(str(error))
            self.refresh()

    def rotate(self):
        if self.pending_source is None:return
        self.pending_source=png_bytes(open_image(self.pending_source).rotate(-90,expand=True))
        self.pending_image=self.pending_source;self.picking=False;self.points.markers=[];self.points.queue_draw();self.show_pending();self.refresh()

    def edit_page(self):
        if not self.selected:return
        self.save_text();self.replace_id=self.selected
        self.pending_original=self.project.image(self.selected,original=True)
        self.pending_source=self.pending_image=self.project.image(self.selected)
        self.original_button.set_active(False);self.show_pending();self.refresh()

    def draw_page(self):
        if self.busy or self.pending_image is None:return
        def accept(image):
            self.pending_image=bytes(image.save_to_png_bytes().get_data())
            self.original_button.set_active(False);self.show_pending()
        self.app.open_drawing(texture(self.pending_image),accept,self)

    def discard_pending(self):
        self.pending_original=self.pending_source=self.pending_image=None;self.replace_id=None;self.picking=False
        self.project.path.with_suffix('.draft.png').unlink(missing_ok=True)
        self.points.markers=[];self.points.queue_draw();self.refresh_pages(self.selected);self.detector.pause()

    def accept_pending(self):
        if self.busy or self.pending_image is None or self.picking:return
        try:
            self.save_meta(); png=self.pending_image
            if self.replace_id:
                page_id=self.replace_id
                with self.project.connection() as db:db.execute('UPDATE pages SET image=?,text=?,confidence=NULL,error=? WHERE id=?',(png,'','',page_id))
            else:page_id=self.project.add(self.pending_original,png)
            self.discard_pending();self.selected=None;self.refresh_pages(page_id);self.ocr_selected()
        except Exception as error:self.status.set_text(str(error))

    def ocr_selected(self):
        if self.busy or not self.selected:return
        page_id=self.selected;project=self.project;png=project.image(page_id)
        self.status.set_text(_t('Seite gespeichert · Text wird lokal erkannt …'))
        def done(result):
            project.text(page_id,**result);self.selected=None;self.refresh_pages(page_id)
            self.status.set_text(_t('Seite gespeichert · Texterkennung {v0} %. Text bitte prüfen.', v0=result["confidence"]))
        def failed(error):
            previous=next(p for p in project.pages() if p['id']==page_id)
            project.text(page_id,previous['text'],previous['confidence'],error=str(error));self.selected=None;self.refresh_pages(page_id)
            self.status.set_text(_t('Seitenbild gespeichert. Texterkennung: ')+str(error))
        self.work(lambda:recognize(png,self.root/'ocr-data',self.cancel),done,failed)

    def work(self,function,done,failed=None):
        self.busy=True;self.cancel=threading.Event();self.refresh()
        def worker():
            try:value,error=function(),None
            except Exception as error_:value,error=None,error_
            GLib.idle_add(deliver,value,error)
        def deliver(value,error):
            if self.closed:return False
            self.busy=False;self.client=None
            if self.cancel.is_set():self.status.set_text(_t('Abgebrochen. Die gespeicherten Seiten bleiben erhalten.'))
            elif error:
                if failed:failed(error)
                else:self.status.set_text(str(error))
            else:done(value)
            self.refresh();return False
        threading.Thread(target=worker,name='tiny2-book',daemon=True).start()

    def cancel_work(self):
        self.cancel.set()
        if self.client:self.client.cancel()

    def choose(self,kind):
        if self.busy or self.pending_image:return
        self.save_text();self.save_meta();self.auto_button.set_active(False)
        action=Gtk.FileChooserAction.OPEN if kind=='open' else Gtk.FileChooserAction.SAVE
        names={'open':_t('Buchprojekt öffnen'),'project':_t('Buchprojekt speichern'),'pdf':_t('PDF exportieren'),'epub':_t('EPUB exportieren')}
        chooser=Gtk.FileChooserNative.new(names[kind],self,action,_t('Öffnen') if kind=='open' else _t('Speichern'),_t('Abbrechen'))
        extension='tinybook' if kind in ('open','project') else kind
        filter=Gtk.FileFilter();filter.set_name(extension.upper());filter.add_pattern('*.'+extension);chooser.add_filter(filter)
        if kind!='open':chooser.set_current_name('Buch.'+extension)
        chooser.connect('response',lambda dialog,response:self.chosen(dialog,response,kind))
        self.dialogs.append(chooser);chooser.show()

    def chosen(self,dialog,response,kind):
        try:
            if response!=Gtk.ResponseType.ACCEPT:return
            path=Path(dialog.get_file().get_path())
            if kind=='open':
                project=BookProject(path);self.discard_pending();self.project=project
                (self.root/'current.txt').write_text(str(path));self.detector=AutoCapture();self.load_project()
                return
            extension='.tinybook' if kind=='project' else '.'+kind
            if path.suffix.lower()!=extension:
                path=path.with_name(path.name+extension)
                if path.exists():raise FileExistsError(_t('Diese Datei existiert bereits. Zum Ersetzen bitte den vollständigen Dateinamen auswählen: ')+str(path))
            self.status.set_text(_t('Export wird erstellt …'))
            def work():
                if kind=='project':self.project.save_as(path)
                elif kind=='pdf':export_pdf(self.project,path,self.cancel)
                else:export_epub(self.project,path,self.cancel)
            def done(_):
                if kind=='project':
                    self.project=BookProject(path)
                    (self.root/'current.txt').write_text(str(path))
                self.status.set_text(_t('Gespeichert: ')+str(path))
            self.work(work,done)
        except Exception as error:self.status.set_text(str(error))
        finally:
            dialog.destroy()
            if dialog in self.dialogs:self.dialogs.remove(dialog)

    def close_scan(self,*_):
        if not self.closed:
            self.save_text();self.save_meta();self.closed=True;self.cancel_work()
            self.app.g13.suspend_motion();self.app.g13.remove_button(self.g13_button)
            if self.timer:GLib.source_remove(self.timer);self.timer=None
            for dialog in self.dialogs:dialog.destroy()
            self.dialogs=[];self.app.book_window=None
        return False
