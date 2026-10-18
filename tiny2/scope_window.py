"""Independent microscope view. No PTZ or zoom commands are sent."""
from .i18n import tr as _t
from dataclasses import dataclass
from copy import deepcopy
import fcntl
import os
from pathlib import Path
import struct
import subprocess
import threading
import time
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
from . import device
from .preview import Preview
from .camera_profiles import Registry, usb_identity
from . import video_modes
from .mode_picker import ModePicker
from .gwen_window import button

last_discovery_error=''


@dataclass(frozen=True)
class Source:
    path: str
    name: str
    backend: str = 'v4l2'
    available: bool = True
    modes: object = None

    @property
    def key(self):return (self.backend,self.path)


def sources(registry=None):
    registry=registry or Registry()
    global last_discovery_error
    last_discovery_error=''
    # Exclude both the Tiny's video and metadata nodes: its stream stays independent.
    tiny={x.path for x in device.discover()}
    found=[]
    for node in sorted(Path('/sys/class/video4linux').glob('video*')):
        path='/dev/'+node.name
        if path in tiny:continue
        profile=registry.match_usb(usb_identity(node))
        if profile is None:continue
        try:
            fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NONBLOCK)
            try:
                caps=bytearray(104);fcntl.ioctl(fd,device.QUERYCAP,caps,True)
                capabilities,device_caps=struct.unpack_from('<II',caps,84)
                effective=device_caps if capabilities&0x80000000 else capabilities
                if not effective&(1|0x1000):continue
                name=bytes(caps[16:48]).split(b'\0',1)[0].decode('utf-8',errors='replace')
                try:modes=video_modes.enumerate_fd(fd)
                except (OSError,ValueError) as error:modes=video_modes.Catalog(note=_t('Modi nicht lesbar: ')+str(error))
                found.append(Source(path,(profile.name if profile.usb else name) or node.name,modes=modes))
            finally:os.close(fd)
        except OSError:continue
    try:
        from .amcam_preview import discover
        if registry.active('amcam'):
            found.extend(Source(c['path'],c['name'],'amcam',c['available']) for c in discover())
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as error:
        last_discovery_error=str(error)
    from .andonstar import discover as wifi_discover
    if registry.active('andonstar'):
        found.extend(Source(c['path'],c['name'],'andonstar') for c in wifi_discover())
    return sorted(found,key=lambda s:(s.backend!='amcam','scope' not in s.name.lower(),s.path))


class ScopeChannel:
    """One source owns its preview, snapshots, chat history and digital zoom."""
    def __init__(self,controls,source):
        self.controls=controls;self.source=source;self.viewer=None;self.chat=None;self.zoom=1.0;self.mode=None

    def ready(self):
        return bool(self.viewer and self.viewer.fresh())

    def snapshot(self):
        if not self.ready():raise ValueError(self.source.name+_t(': Bitte zuerst ein laufendes Scope-Bild einschalten.'))
        return self.viewer.picture.get_paintable()

    def open_gwen(self):
        from .gwen_window import GwenWindow
        if self.chat is None:
            self.chat=GwenWindow(self.controls.app,self.snapshot,self.chat_closed,scope=self)
        self.chat.present()
        return self.chat

    def chat_closed(self):
        self.controls.app.g13.suspend_motion();self.chat=None

    def share(self):
        try:self.controls.app.open_share(self.snapshot(),self.viewer,source_name=self.source.name)
        except Exception as error:self.controls.status.set_text(str(error))

    def draw(self):
        try:
            self.controls.app.open_drawing(self.snapshot(),self.accept_drawing,self.viewer,
                source_name=self.source.name,accept_label=_t('An KI übergeben'))
        except Exception as error:self.controls.status.set_text(str(error))

    def accept_drawing(self,texture):
        self.open_gwen().accept_drawing(texture)

    def zoom_by(self,steps):
        if self.source.backend!='andonstar' or not self.ready():return
        self.zoom=max(1.0,min(6.0,self.zoom*1.15**max(-4,min(4,steps))))
        if self.chat and self.chat.is_active():self.chat.live_button.set_active(True)
        self.viewer.render();self.controls.sync()

    def reset_zoom(self):
        if self.source.backend!='andonstar':return
        self.zoom=1.0
        if self.chat and self.chat.is_active():self.chat.live_button.set_active(True)
        if self.ready():self.viewer.render()
        self.controls.sync()

    def scroll(self,_controller,_dx,dy):
        if self.source.backend!='andonstar':return False
        if not self.controls.app.g13.active and dy:self.zoom_by(-dy)
        return True

    def zoom_label(self):return _t('Bildzoom {v0:.1f}×', v0=self.zoom)

    def show(self):
        if self.viewer:self.viewer.present()

    def toggle_fullscreen(self):
        if self.viewer:
            self.viewer.unfullscreen() if self.viewer.is_fullscreen() else self.viewer.fullscreen()


class ScopeWindow(Gtk.ApplicationWindow):
    def __init__(self,controls,channel):
        source=channel.source
        super().__init__(application=controls.app,title='Scope · '+source.name,decorated=False)
        self.controls=controls;self.channel=channel;self.source=source
        self.closed=False;self.first=True;self.ratio=4/3;self.scale=.5
        self.last_texture=None;self.frame_time=0;self.frames_seen=0
        self.set_default_size(450,338)
        self.picture=Gtk.Picture();self.picture.set_can_shrink(True);self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_size_request(160,90);self.set_child(self.picture)
        if source.backend=='amcam':
            from .amcam_preview import AmcamPreview
            self.preview=AmcamPreview(self.frame,self.failed)
        elif source.backend=='andonstar':
            from .network_preview import NetworkPreview
            self.preview=NetworkPreview(self.frame,self.failed)
        else:self.preview=Preview(self.frame,self.failed)
        self.connect('close-request',self.cleanup)
        self.connect('notify::is-active',controls.app.g13.focus_changed)
        keys=Gtk.EventControllerKey();keys.connect('key-pressed',self.key);self.add_controller(keys)
        move=Gtk.GestureClick.new();move.set_button(1);move.connect('pressed',self.move);self.picture.add_controller(move)
        menu=Gtk.GestureClick.new();menu.set_button(3);menu.connect('pressed',self.menu);self.picture.add_controller(menu)
        self.wheel_controller=Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL|Gtk.EventControllerScrollFlags.DISCRETE)
        self.wheel_controller.connect('scroll',channel.scroll);self.picture.add_controller(self.wheel_controller)
        self.popover=Gtk.Popover();self.popover.set_parent(self.picture)
        items=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        items.append(Gtk.Label(label=source.name))
        for name,callback in [(_t('KI-Chat'),channel.open_gwen),(_t('Bild teilen …'),channel.share),(_t('Zeichnen …'),channel.draw),
                (_t('Klein · 50 %'),lambda:self.resize_view(.5)),(_t('Mittel · 75 %'),lambda:self.resize_view(.75)),
                (_t('Groß · 100 %'),lambda:self.resize_view(1)),(_t('Schließen'),self.close)]:
            items.append(button(name,lambda cb=callback:self.menu_action(cb)))
        self.g13_button=controls.app.g13.make_toggle(short=True);items.append(self.g13_button)
        self.zoom_status=Gtk.Label();items.append(self.zoom_status)
        if source.backend=='andonstar':items.append(button(_t('Bildzoom zurücksetzen'),channel.reset_zoom))
        self.popover.set_child(items)

    def menu_action(self,callback):self.popover.popdown();callback()

    def fresh(self):return not self.closed and self.last_texture is not None and time.monotonic()-self.frame_time<=2

    def frame(self,texture):
        if self.closed:return
        self.last_texture=texture;self.frame_time=time.monotonic();self.frames_seen+=1;self.render()
        if self.first:
            self.first=False;self.ratio=texture.get_width()/texture.get_height();self.resize_view(.5)
            self.controls.status.set_text(self.source.name+_t(': Bild läuft. Weitere Kameras können eingeschaltet bleiben.'))
            self.controls.sync()

    def render(self):
        texture=self.last_texture
        if texture is None:return
        if self.channel.zoom>1:
            # Crop native pixels; Gtk.Picture scales the crop for display. Snapshots
            # and Gwen use this exact crop, never an unrelated or hidden full frame.
            pixbuf=Gdk.pixbuf_get_from_texture(texture)
            width=max(1,round(pixbuf.get_width()/self.channel.zoom));height=max(1,round(pixbuf.get_height()/self.channel.zoom))
            crop=pixbuf.new_subpixbuf((pixbuf.get_width()-width)//2,(pixbuf.get_height()-height)//2,width,height)
            texture=Gdk.Texture.new_for_pixbuf(crop)
        self.picture.set_paintable(texture)
        if self.channel.chat:self.channel.chat.on_camera_frame(texture)
        self.zoom_status.set_text(self.channel.zoom_label() if self.source.backend=='andonstar' else '')
        if self.channel.chat and self.source.backend=='andonstar':
            self.channel.chat.camera_zoom_state.set_text(self.channel.zoom_label())

    def resize_view(self,scale):
        self.scale=scale;self.popover.popdown()
        width=int(900*scale);height=int(width/self.ratio)
        self.set_default_size(width,height)

    def move(self,gesture,_n,x,y):
        event=gesture.get_current_event();surface=self.get_surface()
        if event and surface:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            surface.begin_move(event.get_device(),1,x,y,event.get_time())

    def menu(self,_gesture,_n,x,y):
        rect=Gdk.Rectangle();rect.x=int(x);rect.y=int(y);rect.width=rect.height=1
        self.popover.set_pointing_to(rect);self.popover.popup()

    def key(self,_controller,key,*_):
        if key==Gdk.KEY_Escape:self.close();return True
        return False

    def failed(self,message):
        self.controls.status.set_text(self.source.name+_t(' · Vorschau beendet: ')+message+_t(' · Kamera prüfen und neu einschalten.'))
        if not self.controls.app.closed:self.controls.present()
        self.close()

    def cleanup(self,*_):
        if not self.closed:
            self.closed=True;self.preview.stop();self.last_texture=None;self.popover.unparent()
            self.controls.app.g13.remove_button(self.g13_button)
            if self.channel.viewer is self:self.channel.viewer=None
            if self.channel.chat:
                self.channel.chat.live_button.set_active(False)
                self.channel.chat.status.set_text(_t('Scope-Bild ausgeschaltet. Das letzte Standbild bleibt im Chat.'))
            self.controls.sync()
        return False


class ScopeControls(Gtk.ApplicationWindow):
    def __init__(self,app):
        super().__init__(application=app,title=_t('Kameras & Profile · Community'),transient_for=app.window)
        self.app=app;self.channels={};self.rows={};self.cameras=[];self.updating=False
        self.searching=False;self.search_generation=0
        self.registry=Registry(app.args.config_dir);self.profile_chooser=None
        self.set_default_size(670,560);self.connect('close-request',self.cleanup)
        header=Gtk.HeaderBar();header.set_title_widget(Gtk.Label(label=_t('Kameras & Profile · gleichzeitig anzeigen')));self.set_titlebar(header)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        for side in ('top','bottom','start','end'):getattr(outer,'set_margin_'+side)(16)
        self.set_child(outer)
        row=Gtk.Box(spacing=8)
        self.refresh_button=button(_t('Neu suchen'),self.refresh);row.append(self.refresh_button)
        self.g13_button=app.g13.make_toggle();row.append(self.g13_button);outer.append(row)
        row.append(button(_t('Profil laden …'),self.import_profile))
        self.profile_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        self.profiles_expander=Gtk.Expander(label=_t('Kamera-Erweiterungen'));self.profiles_expander.set_child(self.profile_box);outer.append(self.profiles_expander)
        self.render_profiles()
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);scroll.set_min_content_height(300)
        self.camera_list=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);scroll.set_child(self.camera_list);outer.append(scroll)
        self.status=Gtk.Label(xalign=0,wrap=True);outer.append(self.status)
        self.g13_status=Gtk.Label(xalign=0,wrap=True);self.g13_status.add_css_class('subtitle')
        app.g13.labels.append(self.g13_status);outer.append(self.g13_status)
        hint=Gtk.Label(label=_t('Jede Kamera einzeln einschalten – mehrere Bilder können gleichzeitig laufen. Im Bild ziehen: Fenster verschieben. Rechtsklick: KI, Teilen, Zeichnen und Größe. Andonstar: Mausrad oder G13 G2/G3 für Bildzoom (G13 an sperrt das Mausrad). Für WLAN Ubuntu mit dem Andonstar-Netz verbinden und „Neu suchen“. Vergrößerung und Fokus am Mikroskop bleiben unabhängig.'),xalign=0,wrap=True)
        hint.add_css_class('subtitle');outer.append(hint);self.refresh()

    def render_profiles(self):
        child=self.profile_box.get_first_child()
        while child:
            following=child.get_next_sibling();self.profile_box.remove(child);child=following
        for profile in self.registry.profiles:
            toggle=Gtk.CheckButton(label=_t(profile.name) if profile.id in ('tiny2','usb-video','amscope','andonstar') else profile.name);toggle.set_active(profile.id in self.registry.enabled)
            toggle.set_sensitive(profile.id!='tiny2')
            toggle.connect('toggled',self.profile_changed,profile.id);self.profile_box.append(toggle)
        if self.registry.errors:self.profile_box.append(Gtk.Label(label='; '.join(self.registry.errors),wrap=True,xalign=0))

    def profile_changed(self,toggle,ident):
        try:
            self.registry.enable(ident,toggle.get_active())
            self.status.set_text(_t('Profilauswahl gespeichert. Laufende Bilder bleiben geöffnet; neue Auswahl mit „Neu suchen“ übernehmen.'))
        except (OSError,ValueError) as error:
            self.status.set_text(str(error));self.render_profiles()

    def import_profile(self):
        if self.profile_chooser:self.profile_chooser.show();return
        chooser=Gtk.FileChooserNative.new(_t('Kameraprofil laden'),self,Gtk.FileChooserAction.OPEN,_t('Laden'),_t('Abbrechen'))
        file_filter=Gtk.FileFilter();file_filter.set_name(_t('Kameraprofile (*.json)'));file_filter.add_pattern('*.json');chooser.add_filter(file_filter)
        chooser.connect('response',self.profile_selected);self.profile_chooser=chooser;chooser.show()

    def profile_selected(self,chooser,response):
        try:
            if response==Gtk.ResponseType.ACCEPT:
                selected=chooser.get_file();path=selected.get_path() if selected else None
                if not path:raise ValueError(_t('Bitte eine lokale Profildatei auswählen.'))
                profile=self.registry.install(path);self.render_profiles()
                self.status.set_text(profile.name+_t(' geladen. „Neu suchen“ übernimmt die Auswahl.'))
        except (OSError,ValueError) as error:self.status.set_text(str(error))
        finally:chooser.destroy();self.profile_chooser=None

    def focused_channel(self):
        for channel in self.channels.values():
            if ((channel.viewer and channel.viewer.is_active()) or (channel.chat and channel.chat.is_active())):return channel
        return None

    def refresh(self):
        if not self.searching:self.scan(self.refreshed)

    def scan(self,callback):
        self.search_generation+=1;generation=self.search_generation
        self.searching=True;self.sync();self.status.set_text(_t('Kameras werden gesucht …'))
        def finished(cameras,error):
            if generation!=self.search_generation or self.app.closed:return False
            self.searching=False;callback(cameras,error);self.sync();return False
        registry=deepcopy(self.registry)
        def run():
            try:cameras=sources(registry);error=last_discovery_error
            except Exception as exc:cameras=[];error=str(exc)
            GLib.idle_add(finished,cameras,error)
        threading.Thread(target=run,daemon=True).start()

    def refreshed(self,cameras,error):
        # Some drivers omit occupied cameras during discovery. Keep running views
        # and chats, whose capture callback is bound to this channel across restarts.
        found={c.key:c for c in cameras}
        for key,channel in self.channels.items():
            if channel.viewer or channel.chat:found.setdefault(key,channel.source)
        self.cameras=list(found.values())
        for source in self.cameras:
            if source.key not in self.channels:self.channels[source.key]=ScopeChannel(self,source)
            else:self.channels[source.key].source=source
        child=self.camera_list.get_first_child()
        while child:
            following=child.get_next_sibling();self.camera_list.remove(child);child=following
        self.rows={}
        for source in self.cameras:
            channel=self.channels[source.key]
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);card.add_css_class('card')
            title=Gtk.Label(label=source.name,xalign=0);title.add_css_class('heading');card.append(title)
            detail=Gtk.Label(xalign=0,wrap=True);detail.add_css_class('subtitle');card.append(detail)
            picker=ModePicker();picker.set_catalog(source.modes or video_modes.Catalog(note=_t('Aufnahmegröße wird vom Kamera-Adapter ausgehandelt.')))
            card.append(picker)
            picker.set_mode(channel.mode)
            actions=Gtk.Box(spacing=6);card.append(actions)
            enabled=Gtk.ToggleButton();enabled.connect('toggled',lambda b,c=channel:self.toggle(c))
            actions.append(enabled)
            show=button(_t('Fenster zeigen'),channel.show);actions.append(show)
            gwen=button(_t('KI-Chat'),channel.open_gwen);actions.append(gwen)
            share=button(_t('Bild teilen …'),channel.share);actions.append(share)
            draw=button(_t('Zeichnen …'),channel.draw);actions.append(draw)
            self.rows[source.key]=dict(enabled=enabled,show=show,gwen=gwen,share=share,draw=draw,detail=detail,picker=picker)
            self.camera_list.append(card)
        self.sync()
        self.status.set_text((_t('Kameras einzeln einschalten.') if self.cameras else
            _t('Keine zusätzliche Kamera gefunden. Profil einschalten, Kamera anschließen und „Neu suchen“ drücken.'))+(' '+error if error else ''))

    def sync(self):
        self.updating=True
        for key,row in self.rows.items():
            channel=self.channels[key];viewer=channel.viewer;source=channel.source
            row['enabled'].set_active(viewer is not None)
            row['enabled'].set_label(_t('Bild ausschalten') if viewer else _t('Bild anzeigen'))
            row['enabled'].set_sensitive(bool(viewer) or not self.searching)
            row['show'].set_sensitive(viewer is not None)
            row['picker'].set_sensitive(viewer is None and not self.searching)
            if channel.ready():row['picker'].observed(viewer.last_texture,getattr(viewer.preview,'negotiated',None))
            else:row['picker'].observed_label.set_text('')
            for name in ('share','draw'):row[name].set_sensitive(channel.ready())
            row['gwen'].set_sensitive(channel.ready() or channel.chat is not None)
            row['detail'].set_text(('Live · '+channel.zoom_label() if source.backend=='andonstar' else 'Live') if channel.ready()
                else _t('Vorschau startet …') if viewer else _t('USB erkannt · Bildzugriff prüfen / AmLite schließen') if not source.available
                else _t('WLAN · ausgeschaltet') if source.backend=='andonstar' else _t('Ausgeschaltet'))
        self.refresh_button.set_sensitive(not self.searching);self.updating=False

    def toggle(self,channel):
        if self.updating:return
        if channel.viewer:channel.viewer.close();return
        if self.searching:self.sync();return
        self.scan(lambda cameras,error:self.start_selected(channel,cameras,error))

    def start_selected(self,channel,cameras,error):
        source=channel.source
        if not any(c.key==source.key for c in cameras):
            self.refreshed(cameras,error);self.status.set_text(source.name+_t(': Kamerazuordnung geändert. Bitte neu auswählen.'));return
        if channel.viewer:channel.viewer.present();return
        try:
            self.app.g13.suspend_motion();self.app.end_manual_drag();self.app.cancel_wheel_zoom()
            channel.viewer=ScopeWindow(self,channel);channel.viewer.present()
            self.status.set_text(source.name+_t(': Vorschau wird gestartet …'))
            channel.mode=self.rows[source.key]['picker'].selected_mode()
            if source.backend=='v4l2':channel.viewer.preview.start_auto(source.path,mode=channel.mode)
            else:channel.viewer.preview.start_auto(source.path)
            self.sync()
        except Exception as error:
            if channel.viewer:channel.viewer.close()
            self.status.set_text(source.name+': '+str(error));self.sync()

    def cleanup(self,*_):
        self.search_generation+=1;self.searching=False;self.sync()
        if self.profile_chooser:self.profile_chooser.destroy();self.profile_chooser=None
        if not self.app.closed:self.set_visible(False);return True
        for channel in list(self.channels.values()):
            if channel.viewer:channel.viewer.close()
            if channel.chat:channel.chat.close()
        self.app.g13.remove_button(self.g13_button)
        if self.g13_status in self.app.g13.labels:self.app.g13.labels.remove(self.g13_status)
        self.app.scope_controls=None
        return False
