"""GTK selection for enumerated modes and camera-declared size ranges."""
from .i18n import tr as _t
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from .video_modes import Catalog, SizeRange


class ModePicker(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        self.catalog=Catalog();self.options=[None]
        self.dropdown=Gtk.DropDown.new_from_strings([_t('Automatisch')]);self.append(self.dropdown)
        self.custom=Gtk.Box(spacing=4);self.append(self.custom)
        self.width=Gtk.SpinButton.new_with_range(1,16384,1)
        self.height=Gtk.SpinButton.new_with_range(1,16384,1)
        self.custom.append(self.width);self.custom.append(Gtk.Label(label='×'));self.custom.append(self.height)
        self.observed_label=Gtk.Label(xalign=0);self.observed_label.add_css_class("subtitle");self.append(self.observed_label)
        self.custom.set_visible(False);self.dropdown.connect('notify::selected',self.changed)
        self.set_tooltip_text(_t('Aufnahmegröße und Bildrate. Änderungen werden beim nächsten Vorschau-Start angewendet.'))

    def set_catalog(self,catalog):
        self.catalog=catalog;self.options=[None]+catalog.modes+catalog.ranges
        self.dropdown.set_model(Gtk.StringList.new([_t('Automatisch')]+[x.label for x in self.options[1:]]))
        self.dropdown.set_selected(0);self.changed()
        self.set_tooltip_text(catalog.note or _t('Von der Kamera gemeldete Aufnahmemodi. Änderung beim nächsten Vorschau-Start.'))

    def changed(self,*_):
        index=self.dropdown.get_selected();option=self.options[index] if index<len(self.options) else None
        self.custom.set_visible(isinstance(option,SizeRange))
        if isinstance(option,SizeRange):
            for widget,low,high,step in ((self.width,option.min_width,option.max_width,option.step_width),(self.height,option.min_height,option.max_height,option.step_height)):
                widget.set_range(low,high);widget.set_increments(step,step*10);widget.set_value(low)

    def set_mode(self,mode):
        if mode in self.options:
            self.dropdown.set_selected(self.options.index(mode));return
        if mode is not None:
            for index,option in enumerate(self.options):
                if isinstance(option,SizeRange) and option.fourcc==mode.fourcc:
                    try:option.mode(mode.width,mode.height)
                    except ValueError:continue
                    self.dropdown.set_selected(index);self.width.set_value(mode.width);self.height.set_value(mode.height);return

    def observed(self,texture,negotiated=None):
        text=_t('Bildquelle: {v0} × {v1}', v0=texture.get_width(), v1=texture.get_height())
        if negotiated and negotiated[2]:text+=" · "+negotiated[2]+_t(' Bilder/s')
        if text!=self.observed_label.get_text():self.observed_label.set_text(text)

    def selected_mode(self):
        index=self.dropdown.get_selected();option=self.options[index] if index<len(self.options) else None
        if isinstance(option,SizeRange):return option.mode(self.width.get_value_as_int(),self.height.get_value_as_int())
        return option
