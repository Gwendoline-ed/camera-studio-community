"""Optional AI and local services, configured only for the Community edition."""
from .i18n import tr as _t
import json
import re
from pathlib import Path
from .camera_profiles import config_root,atomic_json
from .ai_providers import PROVIDERS,LABELS,MODEL_KEYS,ENV_KEYS

_directory=None
DEFAULTS={'provider':'local','model':'','port':11434,'openai_model':'','xai_model':'','gemini_model':'',
          'whisper_python':'','whisper_model':'','memory_guard':'','cover_root':''}


def configure(directory):
    global _directory
    _directory=directory


def load():
    try:
        path=config_root(_directory)/'integrations.json'
        with path.open('rb') as stream:raw=stream.read(16385)
        if len(raw)>16384:raise ValueError(_t('Zusatzdienste-Konfiguration ist zu groß.'))
        return validate(json.loads(raw))
    except FileNotFoundError:return dict(DEFAULTS)


def validate(data):
    if not isinstance(data,dict) or set(data)-DEFAULTS.keys():raise ValueError(_t('Ungültige Zusatzdienste-Konfiguration.'))
    result=dict(DEFAULTS);result.update(data)
    if type(result['port']) is not int or not 1<=result['port']<=65535:raise ValueError(_t('Port muss zwischen 1 und 65535 liegen.'))
    for key in DEFAULTS.keys()-{'port'}:
        if not isinstance(result[key],str) or len(result[key])>4096 or '\x00' in result[key]:raise ValueError(_t('Ungültige Zusatzdienste-Einstellung.'))
        result[key]=result[key].strip()
    if result['provider'] not in PROVIDERS:raise ValueError(_t('Unbekannter KI-Anbieter.'))
    for key in MODEL_KEYS.values():
        if result[key] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/+\-]{0,199}',result[key]):
            raise ValueError(_t('Bitte eine gültige Modell-ID mit höchstens 200 Zeichen verwenden.'))
    return result


def save(data):atomic_json(config_root(_directory)/'integrations.json',validate(data))


def open_settings(app,provider=None,on_saved=None):
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk
    from . import api_keys
    window=Gtk.ApplicationWindow(application=app,title=_t('KI & Zusatzdienste · Community'),transient_for=app.window,modal=True)
    window.set_destroy_with_parent(True);window.set_default_size(660,740)
    outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    for side in ('top','bottom','start','end'):getattr(outer,'set_margin_'+side)(18)
    scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_child(outer);window.set_child(scroll)
    outer.append(Gtk.Label(label=_t('KI-Anbieter, Modell und Zugang'),xalign=0,css_classes=['heading']))
    status=Gtk.Label(wrap=True,xalign=0)
    try:data=load()
    except (OSError,ValueError) as error:data=dict(DEFAULTS);status.set_text(str(error))
    choice=Gtk.DropDown.new_from_strings([_t(LABELS[p]) for p in PROVIDERS]);outer.append(choice)
    current=[provider if provider in PROVIDERS else data['provider']]
    choice.set_selected(PROVIDERS.index(current[0]))
    notice=Gtk.Label(wrap=True,xalign=0);outer.append(notice)
    outer.append(Gtk.Label(label=_t('Modell-ID · Bildanalyse und JSON-Antworten erforderlich'),xalign=0))
    model=Gtk.Entry(placeholder_text=_t('Modell-ID aus deiner lokalen Installation oder deinem API-Konto'));outer.append(model)
    port_box=Gtk.Box(spacing=8);port_box.append(Gtk.Label(label=_t('Ollama-Port · 127.0.0.1')))
    port=Gtk.SpinButton.new_with_range(1,65535,1);port.set_value(data['port']);port_box.append(port);outer.append(port_box)
    cloud_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);outer.append(cloud_box)
    cloud_box.append(Gtk.Label(label=_t('API-Schlüssel · leer lassen, um einen hinterlegten Schlüssel zu behalten'),wrap=True,xalign=0))
    secret=Gtk.PasswordEntry(show_peek_icon=True);cloud_box.append(secret)
    remember=Gtk.CheckButton(label=_t('Neuen Schlüssel auf diesem Rechner speichern'))
    remember.set_tooltip_text(_t('Unverschlüsselte Datei api-keys.json mit Dateirechten 0600. Ohne Häkchen nur für diese Sitzung.'))
    cloud_box.append(remember)
    forget=Gtk.CheckButton(label=_t('Hinterlegten Schlüssel entfernen'));cloud_box.append(forget)
    key_note=Gtk.Label(wrap=True,xalign=0);cloud_box.append(key_note)
    drafts={}
    def keep_draft():
        selected=current[0];data[MODEL_KEYS[selected]]=model.get_text()
        if selected!='local':drafts[selected]=(secret.get_text(),remember.get_active(),forget.get_active())
    def show(*_):
        selected=current[0];model.set_text(data[MODEL_KEYS[selected]])
        local=selected=='local';port_box.set_visible(local);cloud_box.set_visible(not local)
        notice.set_text(_t('Lokal: Bilder und Text gehen an Ollama auf diesem Rechner.') if local else
            _t(LABELS[selected])+_t(': Beim Senden werden Standbild und der zugehörige Chatverlauf an den Anbieter übertragen. Eigener API-Zugang erforderlich; API-Nutzung kann Kosten verursachen.'))
        if not local:
            draft=drafts.get(selected,('',False,False));secret.set_text(draft[0]);remember.set_active(draft[1]);forget.set_active(draft[2])
            try:present=bool(api_keys.get(selected))
            except (OSError,ValueError) as error:present=False;status.set_text(str(error))
            key_note.set_text((_t('Schlüssel vorhanden. ') if present else _t('Noch kein Schlüssel hinterlegt. '))+
                _t('Alternativ Umgebungsvariable ')+ENV_KEYS[selected]+_t('. Ohne Speichern bleibt ein neuer Schlüssel nur in dieser Sitzung.'))
    def changed(*_):
        keep_draft();current[0]=PROVIDERS[choice.get_selected()];show()
    choice.connect('notify::selected',changed);show()
    extras=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
    expander=Gtk.Expander(label=_t('Diktat und weitere lokale Dienste'));expander.set_child(extras);outer.append(expander)
    entries={}
    for key,title in [('whisper_python',_t('Python mit faster-whisper · vollständiger Pfad')),('whisper_model',_t('Lokaler Whisper-Modellordner')),
                      ('memory_guard',_t('Optionaler Speicherschutz · Ordner mit guard_common.py')),('cover_root',_t('Optionales Cover-Tool · Web-Ordner'))]:
        extras.append(Gtk.Label(label=title,xalign=0));entry=Gtk.Entry();entry.set_text(data[key]);extras.append(entry);entries[key]=entry
    outer.append(status)
    def persist(_):
        try:
            keep_draft();values=dict(data,provider=current[0],port=port.get_value_as_int())
            values.update({k:e.get_text() for k,e in entries.items()});values=validate(values)
            for selected,(key,store,remove) in drafts.items():
                if key.strip() and remove:raise ValueError(_t('Bitte entweder einen neuen Schlüssel eingeben oder den bisherigen entfernen.'))
                if key.strip():api_keys._validate(key.strip())
            for selected,(key,store,remove) in drafts.items():
                if remove:api_keys.forget(selected)
                elif key.strip():api_keys.set_key(selected,key,persist=store)
            save(values);window.close();app.notify(_t('KI-Einstellungen gespeichert. Für die nächste Anfrage wirksam.'))
            if on_saved:on_saved()
        except (OSError,ValueError) as error:status.set_text(str(error))
    button=Gtk.Button(label=_t('Speichern'));button.connect('clicked',persist);outer.append(button);window.present()
    return window
