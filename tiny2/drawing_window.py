"""XP-Pen/stylus pressure and mouse annotations on a frozen camera image."""
from .i18n import tr as _t
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
from .drawing import Ink
from .gwen_window import button
from .overlays import fitted_rect


class DrawingWindow(Gtk.ApplicationWindow):
    def __init__(self,app,texture,accept,parent,*,source_name="Tiny 2",accept_label=_t('Zeichnung übernehmen')):
        super().__init__(application=app,title=_t('Zeichnen · ')+source_name,transient_for=parent,modal=True)
        self.source_name=source_name
        self.app=app;self.accept=accept;self.ink=Ink();self.closed=False;self.dialogs=[]
        self.active_input=None;self.mouse_start=None
        self.original=bytes(texture.save_to_png_bytes().get_data());self.source_size=(texture.get_width(),texture.get_height())
        self.set_default_size(1050,760);self.connect('close-request',self.closed_window)
        header=Gtk.HeaderBar();header.set_title_widget(Gtk.Label(label=_t('Zeichnen · ')+source_name+_t(' · XP-Pen und Maus')));self.set_titlebar(header)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        for side in ('top','bottom','start','end'):getattr(outer,'set_margin_'+side)(12)
        self.set_child(outer)
        row=Gtk.Box(spacing=8)
        self.tool=Gtk.DropDown.new_from_strings([_t('Stift'),_t('Textmarker'),_t('Strichradierer')]);row.append(self.tool)
        self.color=Gtk.ColorButton();rgba=Gdk.RGBA();rgba.parse('#ff4040');self.color.set_rgba(rgba);self.color.set_title(_t('Stiftfarbe'));row.append(self.color)
        for name,color in [(_t('Rot'),'#ff4040'),(_t('Blau'),'#00bfff'),(_t('Grün'),'#00d895'),(_t('Gelb'),'#ffd33d'),(_t('Weiß'),'#ffffff'),(_t('Schwarz'),'#111111')]:
            row.append(button(name,lambda c=color:self.choose_color(c)))
        outer.append(row)
        row=Gtk.Box(spacing=8);row.append(Gtk.Label(label=_t('Stiftdicke')))
        self.width=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,1,80,1);self.width.set_value(8);self.width.set_hexpand(True);self.width.set_digits(0);row.append(self.width)
        self.pressure=Gtk.CheckButton(label=_t('Stiftdruck'),active=True);row.append(self.pressure)
        row.append(button(_t('Rückgängig'),self.undo));row.append(button(_t('Wiederholen'),self.redo));row.append(button(_t('Alles löschen'),self.clear));outer.append(row)
        self.overlay=Gtk.Overlay();self.overlay.set_vexpand(True);self.overlay.add_css_class('preview');outer.append(self.overlay)
        picture=Gtk.Picture.new_for_paintable(texture);picture.set_can_shrink(True);picture.set_content_fit(Gtk.ContentFit.CONTAIN);picture.set_size_request(320,240);self.overlay.set_child(picture)
        self.canvas=Gtk.DrawingArea();self.canvas.set_can_target(False);self.canvas.set_draw_func(self.draw);self.overlay.add_overlay(self.canvas)
        self.stylus=Gtk.GestureStylus.new()
        if hasattr(self.stylus,'set_stylus_only'):self.stylus.set_stylus_only(True)
        self.stylus.connect('down',self.stylus_down);self.stylus.connect('motion',self.stylus_move);self.stylus.connect('up',self.stylus_up)
        self.stylus.connect('cancel',self.stylus_cancel);self.overlay.add_controller(self.stylus)
        self.mouse=Gtk.GestureDrag.new();self.mouse.set_button(1)
        self.mouse.connect('drag-begin',self.mouse_down);self.mouse.connect('drag-update',self.mouse_move)
        self.mouse.connect('drag-end',self.mouse_up);self.mouse.connect('cancel',self.mouse_cancel);self.overlay.add_controller(self.mouse)
        self.connect('notify::is-active',lambda w,_:None if w.is_active() else self.finish())
        row=Gtk.Box(spacing=8)
        if accept:row.append(button(accept_label,self.apply))
        else:row.append(button(_t('An KI übergeben'),self.to_gwen))
        row.append(button(_t('Bild teilen …'),self.share));row.append(button(_t('PNG speichern …'),self.save));row.append(button(_t('Schließen'),self.close));outer.append(row)
        self.status=Gtk.Label(label=_t('Auf dem Standbild zeichnen. Strichradierer entfernt ganze Striche; Rückgängig stellt sie wieder her.'),xalign=0,wrap=True);outer.append(self.status)

    def choose_color(self,color):
        rgba=Gdk.RGBA();rgba.parse(color);self.color.set_rgba(rgba)
    def position(self,x,y):
        rx,ry,rw,rh=fitted_rect(self.overlay.get_width(),self.overlay.get_height(),*self.source_size)
        if not rw or not rh or not rx<=x<=rx+rw or not ry<=y<=ry+rh:return None
        return ((x-rx)*self.source_size[0]/rw,(y-ry)*self.source_size[1]/rh)
    def draw(self,_area,cr,w,h):
        x,y,rw,rh=fitted_rect(w,h,*self.source_size)
        if not rw or not rh:return
        cr.save();cr.rectangle(x,y,rw,rh);cr.clip();cr.translate(x,y);cr.scale(rw/self.source_size[0],rh/self.source_size[1]);self.ink.draw(cr);cr.restore()
    def begin(self,x,y,pressure=1,eraser=False):
        p=self.position(x,y)
        if p is None:return False
        color=self.color.get_rgba();tool=self.tool.get_selected()
        try:self.ink.begin(*p,(color.red,color.green,color.blue,.3 if tool==1 else 1),self.width.get_value(),pressure,eraser or tool==2)
        except Exception as error:self.status.set_text(str(error));return False
        self.canvas.queue_draw();return True
    def update(self,x,y,pressure=1):
        p=self.position(x,y)
        if p:self.ink.add(*p,pressure);self.canvas.queue_draw()
    def finish(self):
        self.active_input=None;self.mouse_start=None;self.ink.end();self.canvas.queue_draw()
    def pen_pressure(self,gesture):
        valid,value=gesture.get_axis(Gdk.AxisUse.PRESSURE)
        return max(.15,min(1,value)) if valid and self.pressure.get_active() else 1
    def stylus_down(self,gesture,x,y):
        self.finish()
        tool=gesture.get_device_tool();eraser=bool(tool and tool.get_tool_type()==Gdk.DeviceToolType.ERASER)
        if self.begin(x,y,self.pen_pressure(gesture),eraser):
            self.active_input='stylus'
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
    def stylus_move(self,gesture,x,y):
        if self.active_input=='stylus':self.update(x,y,self.pen_pressure(gesture))
    def stylus_up(self,gesture,x,y):
        if self.active_input=='stylus':
            self.update(x,y,self.pen_pressure(gesture));self.finish()
    def stylus_cancel(self,*_):
        # Claiming one gesture can cancel its sibling. Only the owner may end ink.
        if self.active_input=='stylus':self.finish()
    def mouse_down(self,gesture,x,y):
        event=gesture.get_current_event()
        if self.active_input=='stylus' or (event is not None and event.get_device_tool() is not None):
            gesture.set_state(Gtk.EventSequenceState.DENIED);return
        self.finish()
        if self.begin(x,y):
            self.active_input='mouse';self.mouse_start=(x,y)
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        else:gesture.set_state(Gtk.EventSequenceState.DENIED)
    def mouse_move(self,_gesture,dx,dy):
        if self.active_input=='mouse':self.update(self.mouse_start[0]+dx,self.mouse_start[1]+dy)
    def mouse_up(self,gesture,dx,dy):
        if self.active_input=='mouse':self.mouse_move(gesture,dx,dy);self.finish()
    def mouse_cancel(self,*_):
        if self.active_input=='mouse':self.finish()
    def undo(self):self.ink.undo();self.canvas.queue_draw()
    def redo(self):self.ink.redo();self.canvas.queue_draw()
    def clear(self):self.ink.clear();self.canvas.queue_draw()
    def result(self):self.finish();return Gdk.Texture.new_from_bytes(GLib.Bytes.new(self.ink.render(self.original)))
    def apply(self):
        try:self.accept(self.result());self.close()
        except Exception as error:self.status.set_text(str(error))
    def to_gwen(self):
        try:self.app.open_gwen();self.app.gwen_window.accept_drawing(self.result());self.close()
        except Exception as error:self.status.set_text(str(error))
    def share(self):self.app.open_share(self.result(),self,source_name=self.source_name)
    def save(self):
        chooser=Gtk.FileChooserNative.new(_t('Zeichnung speichern'),self,Gtk.FileChooserAction.SAVE,_t('Speichern'),_t('Abbrechen'));chooser.set_current_name('Kamerabild-Zeichnung.png')
        chooser.connect('response',self.saved);self.dialogs.append(chooser);chooser.show()
    def saved(self,chooser,response):
        try:
            if response==Gtk.ResponseType.ACCEPT:
                from .bookscan import atomic_output
                path=Path(chooser.get_file().get_path())
                with atomic_output(path) as temp:temp.write_bytes(self.ink.render(self.original))
                self.status.set_text(_t('Zeichnung gespeichert: ')+str(path))
        except Exception as error:self.status.set_text(str(error))
        finally:chooser.destroy();self.dialogs.remove(chooser)
    def closed_window(self,*_):
        if not self.closed:
            self.closed=True;self.finish()
            for chooser in self.dialogs:chooser.destroy()
            self.dialogs=[]
            if self in self.app.drawing_windows:self.app.drawing_windows.remove(self)
        return False
