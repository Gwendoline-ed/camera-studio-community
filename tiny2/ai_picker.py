"""Visible destination selection; changing provider never sends a request."""
from .i18n import tr as _t
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from . import integrations
from .ai_providers import PROVIDERS,LABELS,MODEL_KEYS


class AIPicker(Gtk.Box):
    def __init__(self,app,on_changed=None,*,history=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        self.app=app;self.on_changed=on_changed;self.history=history
        row=Gtk.Box(spacing=6);self.append(row)
        self.dropdown=Gtk.DropDown.new_from_strings([_t(LABELS[p]) for p in PROVIDERS]);self.dropdown.set_hexpand(True);row.append(self.dropdown)
        self.settings_button=Gtk.Button(label=_t('KI-Einstellungen …'));row.append(self.settings_button)
        self.settings_button.connect('clicked',lambda _:integrations.open_settings(app,self.provider,self.update_notice))
        self.notice=Gtk.Label(wrap=True,xalign=0);self.notice.add_css_class('subtitle');self.append(self.notice)
        try:selected=integrations.load()['provider']
        except (OSError,ValueError):selected='local'
        self.dropdown.set_selected(PROVIDERS.index(selected));self.dropdown.connect('notify::selected',self.changed);self.update_notice()

    @property
    def provider(self):return PROVIDERS[self.dropdown.get_selected()]
    @property
    def label(self):return _t(LABELS[self.provider])

    def update_notice(self):
        try:model=integrations.load()[MODEL_KEYS[self.provider]] or _t('Modell noch nicht eingerichtet')
        except (OSError,ValueError) as error:model=str(error)
        content=_t('Standbild und dieser Verlauf') if self.history else _t('Standbild und Analyseauftrag')
        destination=_t('Bleibt auf diesem Rechner') if self.provider=='local' else _t('{content} werden erst beim Senden an {provider} übertragen',content=content,provider=self.label)
        self.notice.set_text(destination+' · '+model)

    def changed(self,*_):
        self.update_notice()
        if self.on_changed:self.on_changed(self.provider)
