"""A frozen, reviewable snapshot with explicit sharing destinations."""
from .i18n import tr as _t
from datetime import datetime
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, Gdk
from .gwen import MAX_IMAGE


class ShareWindow(Gtk.ApplicationWindow):
    def __init__(self, application, texture, parent, on_close, *, source_name="Tiny 2"):
        super().__init__(application=application, title=_t('Bild teilen · ')+source_name)
        self.source_name=source_name
        self.texture = texture
        self.png = bytes(texture.save_to_png_bytes().get_data())
        if len(self.png) > MAX_IMAGE: raise ValueError(_t('Bild zu groß. Bitte eine kleinere Vorschauauflösung wählen.'))
        self.on_close = on_close
        self.chooser = None
        self.set_transient_for(parent); self.set_default_size(760, 560)
        self.connect('close-request', self.closed)
        header = Gtk.HeaderBar(); header.set_title_widget(Gtk.Label(label=_t('Bild teilen · ')+source_name)); self.set_titlebar(header)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'bottom', 'start', 'end'): getattr(outer, 'set_margin_' + side)(16)
        self.set_child(outer)
        outer.append(Gtk.Label(label=_t('Dieses Standbild teilen · ') + datetime.now().strftime('%H:%M:%S'), xalign=0))
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN); picture.set_can_shrink(True)
        picture.set_size_request(320, 180); picture.set_vexpand(True); outer.append(picture)
        row = Gtk.Box(spacing=8)
        for title, callback in [(_t('Bild kopieren'), self.copy), (_t('Bild speichern …'), self.save),
                                (_t('Comic lesen · lokale OCR'), self.comic)]:
            button = Gtk.Button(label=title); button.connect('clicked', lambda _, cb=callback: cb()); row.append(button)
        outer.append(row)
        self.status = Gtk.Label(label=_t('Dieses Standbild wird geteilt. Ziel auswählen.'), xalign=0, wrap=True)
        self.status.add_css_class('notice'); outer.append(self.status)

    def copy(self):
        provider = Gdk.ContentProvider.new_for_value(self.texture)
        if self.get_display().get_clipboard().set_content(provider):
            self.status.set_text(_t('Bild kopiert. Du kannst es jetzt in eine andere Anwendung einfügen.'))
        else:
            self.status.set_text(_t('Das Bild konnte nicht in die Zwischenablage übernommen werden.'))

    def save(self):
        if self.chooser: self.chooser.show(); return
        chooser = Gtk.FileChooserNative.new(_t('Kamerabild speichern'), self, Gtk.FileChooserAction.SAVE,
                                            _t('Speichern'), _t('Abbrechen'))
        chooser.set_current_name('Kamerabild-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.png')
        chooser.connect('response', self.saved); self.chooser = chooser; chooser.show()

    def saved(self, chooser, response):
        try:
            if response == Gtk.ResponseType.ACCEPT:
                file = chooser.get_file(); path = file.get_path() if file else None
                if not path: raise ValueError(_t('Bitte einen lokalen Speicherort wählen.'))
                # GTK confirms overwrites for the selected path before ACCEPT.
                Path(path).write_bytes(self.png)
                self.status.set_text(_t('Kamerabild gespeichert: ') + path)
        except Exception as error: self.status.set_text(_t('Speichern fehlgeschlagen: ') + str(error))
        finally: chooser.destroy(); self.chooser = None

    def comic(self):
        try:
            url = self.get_application().share_cover(self.png)
            Gio.AppInfo.launch_default_for_uri(url, None)
            self.status.set_text(_t('Lokale Texterkennung im Cover-Werkzeug geöffnet · unabhängig vom KI-Anbieter. Angaben dort prüfen. Es wird noch kein Bestand in InvenTree gebucht.'))
        except Exception as error: self.status.set_text(str(error))

    def closed(self, *_):
        if self.chooser: self.chooser.destroy(); self.chooser = None
        self.png = b''; self.texture = None
        self.on_close(self); return False
