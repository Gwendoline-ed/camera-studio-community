"""GTK 4 desktop application; all camera I/O runs outside the GTK thread."""
from .i18n import tr as _t
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import errno
import json
import time
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gio, GLib
from . import device, __version__
from .controller import Controller, Presets, Result
from .preview import Preview
from .mode_picker import ModePicker
from . import video_modes
from .protocol import MODES
from .overlays import DEFAULTS, OverlayStore
from .overlay_view import OverlayView
from .wheel_zoom import WheelZoom
from .manual_drag import ManualDrag
from .g13_control import G13Controls
from copy import deepcopy

CSS = b"""
window { background: #10151d; color: #edf1f8; }
headerbar { background: #151d28; border: none; }
.title { font-size: 23px; font-weight: 700; }
.subtitle { color: #9baabe; font-size: 12px; }
.card { background: #1a2330; border-radius: 14px; padding: 18px; }
.card-title { font-size: 15px; font-weight: 700; margin-bottom: 10px; }
.preview { background: #080c12; border-radius: 14px; }
.pill { background: #26344a; color: #b8d5ff; border-radius: 14px; padding: 7px 12px; }
.warning { color: #ffd58c; }
.good { color: #8cdec1; }
button { background: #29384d; color: #edf1f8; border-radius: 9px; padding: 9px 13px; border: none; }
button:hover { background: #364c69; }
button:checked { background: #295e70; color: white; }
button.suggested-action { background: #3a72e6; color: white; }
button.destructive-action { background: #793342; color: #fff1f3; }
button:disabled { opacity: 0.4; }
spinbutton, dropdown { background: #111a27; border-radius: 8px; }
spinbutton text { padding: 9px; }
textview, textview text, entry { background: #111a27; color: #edf1f8; }
entry { border-radius: 8px; padding: 8px; }
list { background: #111a27; color: #edf1f8; border-radius: 8px; }
list row:selected { background: #295e70; color: white; }
.metric { font-size: 17px; font-weight: 600; }
.notice { background: #222d3b; padding: 12px 16px; border-radius: 10px; }
stackswitcher button { padding: 9px; }
"""


def label(text, cls=None, wrap=False):
    widget = Gtk.Label(label=_t(text), xalign=0, wrap=wrap)
    if cls: widget.add_css_class(cls)
    return widget


def box(vertical=False, spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


def spin(minimum, maximum, step, value=0, digits=0):
    widget = Gtk.SpinButton.new_with_range(minimum, maximum, step)
    widget.set_digits(digits); widget.set_value(value); widget.set_hexpand(True)
    return widget


class Studio(Gtk.Application):
    def __init__(self, args):
        super().__init__(application_id="io.local.CameraStudioCommunity", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.args = args
        from . import integrations
        integrations.configure(args.config_dir)
        self.camera = self.controller = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tiny2-usb")
        self.busy = False
        self.closed = False
        self.preset_store = Presets(args.config_dir)
        self.actions = []
        self.log_lines = []
        self.frames_seen = 0
        self.stop_pending = False
        self.image_actions = []
        self.smoke_ok = False
        self.preview = Preview(self.on_frame, self.preview_error)
        self.overlay_store = OverlayStore(args.config_dir)
        self.overlay_load_error = None
        try: self.overlay_settings = self.overlay_store.load()
        except ValueError as exc:
            self.overlay_settings = deepcopy(DEFAULTS); self.overlay_load_error = str(exc)
        self.detached_window = None
        self.detached_zoom_state = None
        self.wheel_zoom = WheelZoom()
        self.wheel_zoom_timer = None
        self.wheel_zoom_surface = None
        self.manual_drag = ManualDrag()
        self.manual_timer = None
        self.manual_enabled = self.manual_ready = False
        self.manual_epoch = 0
        self.manual_surface = None
        self.syncing_manual_controls = False
        self.manual_button = self.manual_hint = None
        self.g13 = G13Controls(self)
        self.detached_g13_button = None
        self.gwen_window = None
        self.book_window = None
        self.scope_controls = None
        self.drawing_windows = []
        self.share_windows = []
        self.cover_share = None
        self.last_frame = None
        self.image_chooser = None
        self.loading_overlay_controls = False
        self.connect("activate", self.activate)

    def button(self, title, callback, *, controlled=True, style=None):
        widget = Gtk.Button(label=_t(title))
        widget.connect("clicked", lambda _button: callback())
        if style: widget.add_css_class(style)
        if controlled:
            self.actions.append(widget); widget.set_sensitive(False)
        return widget

    def card(self, title):
        widget = box(True)
        widget.add_css_class("card")
        widget.append(label(title, "card-title"))
        return widget

    def activate(self, _application):
        self.window = Gtk.ApplicationWindow(application=self, title="Camera Studio Community · Ubuntu")
        self.window.set_default_size(1180, 820)
        self.window.connect("close-request", self.close)
        self.window.connect("notify::is-active", self.g13.focus_changed)
        provider = Gtk.CssProvider(); provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        header = Gtk.HeaderBar()
        title = box(True, 2); title.append(label("Camera Studio Community", "title")); title.append(label(_t('Kamerasteuerung für Ubuntu · {v0}', v0=__version__), "subtitle"))
        header.set_title_widget(title)
        self.connection = label(_t('Nicht verbunden'), "pill")
        header.pack_start(self.connection)
        self.connect_button = self.button(_t('Verbinden'), self.connect_camera, controlled=False)
        header.pack_end(self.connect_button)
        header.pack_end(self.button("KI", self.open_gwen, controlled=False))
        header.pack_end(self.button(_t('Buchscan'), self.open_book, controlled=False))
        header.pack_end(self.button(_t('Bild teilen …'), self.open_share, controlled=False))
        self.window.set_titlebar(header)

        outer = box(True, 14)
        for side in ("top", "bottom", "start", "end"): getattr(outer, "set_margin_" + side)(18)
        self.window.set_child(outer)
        body = box(False, 18); body.set_vexpand(True); outer.append(body)
        left = box(True, 14); left.set_hexpand(True); body.append(left)

        preview_head = box()
        title = label(_t('Kameravorschau'), "card-title"); title.set_hexpand(True); preview_head.append(title)
        self.resolution = ModePicker()
        self.resolution.set_valign(Gtk.Align.CENTER)
        preview_head.append(self.resolution)
        self.preview_button = self.button(_t('Vorschau starten'), self.toggle_preview)
        self.preview_button.set_valign(Gtk.Align.CENTER)
        preview_head.append(self.preview_button); left.append(preview_head)
        self.detach_button = self.button(_t('Bild auslagern ↗'), self.toggle_detached, controlled=False)
        self.detach_button.set_tooltip_text(_t('Kamerabild in einem frei verschiebbaren Fenster öffnen'))
        self.detach_button.set_valign(Gtk.Align.CENTER)
        preview_head.append(self.detach_button)
        self.preview_slot = box(True); self.preview_slot.set_vexpand(True); left.append(self.preview_slot)
        self.detached_placeholder = box(True)
        self.detached_placeholder.set_valign(Gtk.Align.CENTER)
        self.detached_placeholder.append(label(_t('Das Kamerabild ist im separaten Fenster.'), "subtitle", True))
        self.detached_placeholder.append(self.button(_t('Kamerafenster zeigen'), self.present_detached, controlled=False))
        self.detached_placeholder.set_visible(False); self.preview_slot.append(self.detached_placeholder)
        self.overlay = Gtk.Overlay(); self.overlay.add_css_class("preview"); self.overlay.set_vexpand(True)
        self.picture = Gtk.Picture(); self.picture.set_can_shrink(True); self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_size_request(320, 180); self.overlay.set_child(self.picture)
        self.overlay_view = OverlayView(self.overlay_settings, lambda message: self.notify(message, True))
        self.overlay.add_overlay(self.overlay_view)
        self.empty = label(_t('Verbinde deine Tiny 2, um das Bild zu sehen.'), "subtitle", True)
        self.empty.set_halign(Gtk.Align.CENTER); self.empty.set_valign(Gtk.Align.CENTER)
        self.empty.set_can_target(False)
        self.overlay.add_overlay(self.empty); self.preview_slot.append(self.overlay)
        self.wheel_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        self.wheel_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.wheel_controller.connect("scroll", self.scroll_camera_zoom)
        self.overlay.add_controller(self.wheel_controller)
        self.drag_controller = Gtk.GestureDrag.new()
        self.drag_controller.set_button(1)
        self.drag_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.drag_controller.connect("drag-begin", self.manual_drag_begin)
        self.drag_controller.connect("drag-update", self.manual_drag_update)
        self.drag_controller.connect("drag-end", lambda *_: self.end_manual_drag())
        self.drag_controller.connect("cancel", lambda *_: self.end_manual_drag())
        self.overlay.add_controller(self.drag_controller)
        motion = Gtk.EventControllerMotion.new()
        motion.connect("leave", lambda *_: self.end_manual_drag())
        self.overlay.add_controller(motion)
        metrics = box(False, 12)
        self.mode_state = label(_t('Tracking: —'), "metric")
        self.zoom_state = label(_t('Zoom: —'), "metric")
        self.mode_state.set_hexpand(True)
        metrics.append(self.mode_state); metrics.append(self.zoom_state); left.append(metrics)
        self.detail_state = label(_t('Noch keine Kamerarückmeldung.'), "subtitle", True); left.append(self.detail_state)
        left.append(self.presets_ui())
        tools = box(False)
        tools.append(self.button(_t('Rohwinkel lesen'), self.read_angles))
        tools.append(self.button(_t('KI & Dienste …'), self.open_integrations, controlled=False))
        tools.append(self.button(_t('Kameras & Profile …'), self.open_scope, controlled=False))
        left.append(tools)

        right = box(True, 12); right.set_size_request(380, -1)
        self.stack = Gtk.Stack(); self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        switcher = Gtk.StackSwitcher(stack=self.stack); switcher.set_halign(Gtk.Align.FILL)
        right.append(switcher)
        scroll = Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True); scroll.set_child(self.stack); right.append(scroll); body.append(right)
        self.stack.add_titled(self.movement_ui(), "motion", _t('Bewegung'))
        self.stack.add_titled(self.tracking_ui(), "tracking", _t('Tracking'))
        self.stack.add_titled(self.image_ui(), "image", _t('Bild'))
        self.stack.add_titled(self.overlays_ui(), "overlays", _t('Overlays'))
        self.stack.add_titled(self.g13.page(), "g13", "G13")
        if getattr(self.args, 'tab', None): self.stack.set_visible_child_name(self.args.tab)
        from . import i18n
        preferences = box(False, 8)
        preferences.append(label(_t('Sprache')))
        self.language_dropdown = Gtk.DropDown.new_from_strings(list(i18n.NAMES))
        self.language_dropdown.set_selected(i18n.LANGUAGES.index(i18n.language()))
        preferences.append(self.language_dropdown)
        self.language_notice = label('', 'subtitle', True)
        self.language_notice.set_hexpand(True); preferences.append(self.language_notice)
        self.language_dropdown.connect('notify::selected', self.choose_language)
        preferences.append(self.button(_t('Anleitung'), self.open_manual, controlled=False))
        outer.append(preferences)
        self.notice = label(_t('Bereit. Beim Verbinden werden nur Einstellungen gelesen.'), "notice", True)
        outer.append(self.notice)
        self.window.present()
        if self.overlay_load_error: self.notify(self.overlay_load_error, True)
        try: self.overlay_view.load_image(self.overlay_settings["image"]["path"])
        except (OSError, ValueError, GLib.Error) as exc: self.notify(_t('Overlay-Bild: ') + str(exc), True)
        if self.args.smoke_test:
            self.empty.set_text(_t('Testbild · keine Kameraaufnahme'))
            self.preview.start(None, test=True)
            GLib.timeout_add_seconds(3, self.smoke_finish)
        else:
            GLib.idle_add(self.connect_camera)
            GLib.timeout_add_seconds(2, self.poll)

    def choose_language(self, dropdown, *_):
        from . import i18n
        try:
            i18n.save_language(i18n.LANGUAGES[dropdown.get_selected()], self.args.config_dir)
            self.language_notice.set_text(_t('Sprache gespeichert. Bitte die Anwendung neu starten.'))
        except (OSError, ValueError) as error:
            self.notify(str(error), True)

    def open_manual(self):
        from .i18n import manual_path
        try:
            path = manual_path()
            if not path.is_file(): raise OSError(_t('Anleitung konnte nicht geöffnet werden.'))
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)
        except (OSError, GLib.Error) as error:
            self.notify(str(error), True)

    def movement_ui(self):
        page = box(True, 12)
        card = self.card(_t('Ausrichtung'))
        card.append(label(_t('Zielwinkel · Neigen positiv = nach oben'), "subtitle"))
        row = box()
        column = box(True, 4); column.append(label(_t('Schwenken'))); self.pan = spin(-130, 130, 0.1, digits=1); column.append(self.pan); row.append(column)
        column = box(True, 4); column.append(label(_t('Neigen'))); self.tilt = spin(-90, 90, 0.1, digits=1); column.append(self.tilt); row.append(column); card.append(row)
        self.move_button = self.button(_t('Ziel anfahren'), self.move_target, style="suggested-action"); card.append(self.move_button)
        card.append(label(_t('Manuelle Bewegungen schalten Tracking aus. Die Zielwerte sind keine gemessenen Positionen.'), "subtitle", True))
        row = box(); row.append(label(_t('Schrittweite'))); self.step = spin(0.1, 20, 0.1, 2, 1); row.append(self.step); row.append(label(_t('Grad'))); card.append(row)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, halign=Gtk.Align.CENTER)
        for text, x, y, dp, dt in [("↑", 1, 0, 0, 1), ("←", 0, 1, 1, 0), ("→", 2, 1, -1, 0), ("↓", 1, 2, 0, -1)]:
            button = self.button(text, lambda dp=dp,dt=dt: self.step_move(dp, dt)); grid.attach(button,x,y,1,1)
        grid.attach(self.button(_t('Mitte'), self.center),1,1,1,1); card.append(grid)
        self.stop_button = self.button(_t('■  Stop'), self.stop, style="destructive-action"); card.append(self.stop_button)
        page.append(card)
        card = self.card(_t('Zoom'))
        self.zoom = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1); self.zoom.set_value(0); self.zoom.set_digits(0)
        card.append(self.zoom); card.append(label(_t('0 = weit · 100 = maximaler UVC-Zoom'), "subtitle"))
        card.append(self.button(_t('Zoom übernehmen'), self.apply_zoom))
        row=box()
        for name in ["Weit", "Mittel", "Eng"]:
            row.append(self.button(name, lambda n=name: self.run_action(lambda: self.controller.fov(n))))
        card.append(row); page.append(card)
        power = box(); power.append(self.button(_t('Aufwecken'), lambda: self.run_action(lambda: self.controller.power(True))))
        power.append(self.button(_t('Ruhemodus'), lambda: self.run_action(lambda: self.controller.power(False))))
        page.append(power)
        return page

    def tracking_ui(self):
        page = box(True, 12)
        card = self.card(_t('Gestensteuerung'))
        card.append(label(_t('Die Tiny 2 erkennt Gesten selbst, wenn sie in der Kamera aktiviert sind.'), "subtitle", True))
        card.append(label(_t('Offene Handfläche: Personenverfolgung an/aus.\nL aus Daumen und Zeigefinger: Zoom umschalten.\nZwei L-Gesten: dynamischer Zoom durch Ändern des Handabstands.'), wrap=True))
        card.append(label(_t('Ein-/Ausschalter für die Gestenerkennung sind hier noch nicht verfügbar. Ob sie aktiviert ist, kann diese App noch nicht auslesen.'), "subtitle", True))
        card.append(Gtk.LinkButton.new_with_label("https://www.obsbot.com/explore/obsbot-tiny-2", _t('Gesten-Anleitung von OBSBOT')))
        page.append(card)
        card = self.card(_t('Verfolgung'))
        card.append(label(_t('Die Kamera übernimmt Erkennung und Nachführung.'), "subtitle", True))
        for name in MODES:
            card.append(self.button(name, lambda n=name: self.run_action(lambda: self.controller.mode(n))))
        page.append(card); card = self.card(_t('Verfolgungstempo'))
        row = box()
        for name in ["Standard", "Sport"]:
            row.append(self.button(name, lambda n=name: self.run_action(lambda: self.controller.speed(n))))
        card.append(row); page.append(card)
        page.append(label(_t('Moduswechsel werden erst nach passender Rückmeldung als bestätigt angezeigt.'), "subtitle", True))
        return page

    def image_ui(self):
        page=box(True,12);card=self.card(_t('Dynamikumfang'));row=box()
        row.append(self.button(_t('HDR an'),lambda:self.run_action(lambda:self.controller.hdr(True))))
        row.append(self.button(_t('HDR aus'),lambda:self.run_action(lambda:self.controller.hdr(False))))
        card.append(row);page.append(card)
        self.image_box=self.card(_t('Bildeinstellungen'))
        self.image_box.append(label(_t('Unterstützte Regler werden nach dem Verbinden geladen.'), "subtitle", True))
        page.append(self.image_box)
        page.append(label(_t('Text, Uhrzeit und Logos findest du unter Overlays. Beauty-Effekte und Hintergrundersatz sind noch nicht enthalten.'), "subtitle",True))
        return page

    def toggle_detached(self):
        if self.detached_window:
            self.dock_preview(); return
        window = Gtk.ApplicationWindow(application=self, title=_t('Tiny 2 · Kamerabild'))
        window.set_default_size(900, 560)
        header = Gtk.HeaderBar()
        title = box(True, 2)
        title.append(label(_t('Kamerabild · Tiny 2'), "card-title"))
        self.detached_zoom_state = label("", "subtitle")
        title.append(self.detached_zoom_state)
        self.manual_hint = label("", "subtitle")
        self.manual_hint.set_visible(False); title.append(self.manual_hint)
        header.set_title_widget(title)
        header.pack_start(self.button(_t('Andocken'), self.dock_preview, controlled=False))
        self.manual_button = Gtk.ToggleButton(label=_t('Manuell'))
        self.manual_button.set_tooltip_text(_t('Tracking ausschalten und die Kamera mit gedrückter linker Maustaste steuern'))
        self.manual_button.connect("toggled", self.toggle_manual)
        header.pack_start(self.manual_button)
        self.detached_g13_button = self.g13.make_toggle(short=True)
        header.pack_start(self.detached_g13_button)
        header.pack_start(self.button("KI", self.open_gwen, controlled=False))
        header.pack_end(self.button(_t('Bild teilen …'), self.open_share, controlled=False))
        header.pack_end(self.button(_t('Zeichnen'), self.open_drawing, controlled=False))
        self.fullscreen_button = self.button(_t('Vollbild'), self.toggle_fullscreen, controlled=False)
        header.pack_end(self.fullscreen_button)
        window.set_titlebar(header)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.preview_key)
        window.add_controller(keys)
        window.connect("close-request", self.dock_preview)
        window.connect("notify::is-active", self.manual_focus_changed)
        window.connect("notify::is-active", self.g13.focus_changed)
        window.connect("notify::fullscreened", lambda w, _p: self.fullscreen_button.set_label(_t('Vollbild verlassen') if w.is_fullscreen() else _t('Vollbild')))
        self.preview_slot.remove(self.overlay)
        self.picture.set_size_request(160, 90)
        window.set_child(self.overlay)
        self.detached_window = window
        self.refresh_manual_controls()
        self.refresh_wheel_zoom_label()
        self.overlay.set_tooltip_text(_t('Mausrad: Kamerazoom · nach oben näher, nach unten weiter'))
        self.detached_placeholder.set_visible(True)
        self.detach_button.set_label(_t('Bild andocken ↙'))
        window.present()

    def dock_preview(self, *_):
        window = self.detached_window
        if window is None: return True
        self.g13.suspend_motion()
        if self.detached_g13_button is not None:
            self.g13.remove_button(self.detached_g13_button); self.detached_g13_button = None
        self.disable_manual()
        self.manual_button = self.manual_hint = None
        self.cancel_wheel_zoom()
        self.detached_zoom_state = None
        self.overlay.set_tooltip_text(None)
        self.detached_window = None
        window.set_child(None)
        self.picture.set_size_request(320, 180)
        self.preview_slot.append(self.overlay)
        self.detached_placeholder.set_visible(False)
        self.detach_button.set_label(_t('Bild auslagern ↗'))
        window.destroy()
        return True

    def present_detached(self):
        if self.detached_window: self.detached_window.present()

    def open_gwen(self):
        if self.gwen_window is None:
            from .gwen_window import GwenWindow
            self.gwen_window = GwenWindow(self, self.camera_snapshot, self.gwen_closed)
            self.refresh_manual_controls(); self.refresh_wheel_zoom_label()
        self.gwen_window.present()

    def gwen_closed(self):
        self.end_manual_drag('gwen')
        if self.wheel_zoom_surface == 'gwen': self.cancel_wheel_zoom()
        self.g13.suspend_motion()
        self.gwen_window = None
        if self.detached_window is None: self.disable_manual()

    def open_integrations(self):
        from .integrations import open_settings
        open_settings(self)

    def open_scope(self):
        if self.scope_controls is None:
            from .scope_window import ScopeControls
            self.scope_controls = ScopeControls(self)
        self.scope_controls.present()

    def open_book(self):
        if self.book_window is None:
            try:
                from .book_window import BookWindow
                self.book_window = BookWindow(self)
                if self.last_frame: self.book_window.on_camera_frame(self.last_frame[0])
            except Exception as error: self.notify(str(error), True); return
        self.book_window.present()

    def open_drawing(self, texture=None, accept=None, parent=None, *, source_name="Tiny 2", accept_label=_t('Zeichnung übernehmen')):
        try:
            from .drawing_window import DrawingWindow
            if texture is None: texture = self.camera_snapshot()
            self.g13.suspend_motion(); self.end_manual_drag(); self.cancel_wheel_zoom()
            window = DrawingWindow(self, texture, accept, parent or self.detached_window or self.window,
                                   source_name=source_name,accept_label=accept_label)
            self.drawing_windows.append(window); window.present()
        except Exception as error: self.notify(str(error), True)

    def mouse_surface_available(self, surface):
        if surface == 'gwen':
            return self.gwen_window is not None and not self.gwen_window.closed
        return self.detached_window is not None

    def camera_input_started(self, surface=None):
        chat = self.gwen_window
        if chat is not None and not chat.closed and (surface == 'gwen' or (surface is None and chat.is_active())):
            chat.live_button.set_active(True)

    def open_share(self, texture=None, parent=None, *, source_name="Tiny 2"):
        try:
            from .share_window import ShareWindow
            if texture is None: texture = self.camera_snapshot()
            if len(self.share_windows) >= 4: self.share_windows[0].close()
            window = ShareWindow(self, texture, parent or self.detached_window or self.window,
                                 self.share_closed,source_name=source_name)
            self.share_windows.append(window); window.present()
        except Exception as error: self.notify(str(error), True)

    def share_closed(self, window):
        if window in self.share_windows: self.share_windows.remove(window)

    def share_cover(self, png):
        if self.cover_share is None:
            from .cover_share import CoverShare
            self.cover_share = CoverShare()
        return self.cover_share.share(png)

    def camera_snapshot(self):
        if (not self.preview.pipeline or self.last_frame is None
                or self.last_frame[1] != self.preview.generation
                or time.monotonic() - self.last_frame[2] > 2):
            raise ValueError(_t('Bitte zuerst eine laufende Kameravorschau starten.'))
        self.end_manual_drag()
        return self.last_frame[0]

    def toggle_fullscreen(self):
        window = self.detached_window
        if window:
            window.unfullscreen() if window.is_fullscreen() else window.fullscreen()

    def preview_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape and self.detached_window:
            self.g13.disable()
            self.disable_manual()
            self.detached_window.unfullscreen(); return True
        if keyval == Gdk.KEY_F11:
            self.toggle_fullscreen(); return True
        return False

    def refresh_manual_controls(self):
        available = self.controller is not None and self.preview.pipeline is not None and not self.g13.active
        self.syncing_manual_controls = True
        buttons = [self.manual_button]
        if self.gwen_window is not None: buttons.append(self.gwen_window.manual_button)
        for button in buttons:
            if button is not None:
                button.set_sensitive(available and (self.manual_enabled or not self.busy))
                button.set_active(self.manual_enabled)
        self.syncing_manual_controls = False
        if self.manual_hint is not None:
            self.manual_hint.set_visible(self.manual_enabled)
            self.manual_hint.set_text(_t('Linke Maustaste halten und ziehen') if self.manual_ready else _t('Manuell wird aktiviert …'))
        if hasattr(self, 'overlay'):
            self.overlay.set_cursor_from_name("grabbing" if self.manual_drag.active else "grab" if self.manual_ready else None)
        if self.gwen_window is not None:
            self.gwen_window.overlay.set_cursor_from_name("grabbing" if self.manual_drag.active else "grab" if self.manual_ready else None)
            self.gwen_window.camera_stop_button.set_sensitive(self.controller is not None and not self.stop_pending)

    def toggle_manual(self, button, *, surface='detached'):
        if self.syncing_manual_controls: return
        if not button.get_active():
            self.disable_manual(); return
        if self.g13.active or self.busy or not self.controller or not self.mouse_surface_available(surface) or not self.preview.pipeline:
            self.disable_manual(); return
        self.manual_enabled = True; self.manual_ready = False
        self.manual_epoch += 1
        epoch = self.manual_epoch
        controller = self.controller
        controller.cancel.clear()
        self.cancel_wheel_zoom()
        self.camera_input_started(surface)
        def done(result):
            if result.snapshot: self.update_state(result.snapshot)
            if self.manual_enabled and self.manual_epoch == epoch:
                self.manual_ready = True
                self.notify(_t('Manuell aktiv: linke Maustaste im Kamerabild halten und ziehen. Mausrad = Zoom.'))
            self.refresh_manual_controls()
        self.background(lambda: controller.mode("Aus"), done)

    def disable_manual(self):
        self.manual_enabled = self.manual_ready = False
        self.manual_epoch += 1
        self.end_manual_drag()
        self.refresh_manual_controls()

    def end_manual_drag(self, surface=None):
        if surface is not None and self.manual_surface != surface: return
        self.manual_drag.end()
        self.manual_surface = None
        if self.manual_timer is not None:
            GLib.source_remove(self.manual_timer); self.manual_timer = None
        self.refresh_manual_controls()

    def manual_focus_changed(self, window, _property):
        if not window.is_active():
            self.end_manual_drag()
            surface = 'gwen' if window is self.gwen_window else 'detached'
            if self.wheel_zoom_surface == surface: self.cancel_wheel_zoom()

    def manual_drag_begin(self, gesture, _x, _y, *, surface='detached'):
        if (self.g13.active or not self.manual_ready or not self.mouse_surface_available(surface) or not self.controller
                or not self.preview.pipeline or self.closed or self.stop_pending):
            gesture.set_state(Gtk.EventSequenceState.DENIED); return
        overlay = self.gwen_window.overlay if surface == 'gwen' else self.overlay
        if self.manual_drag.begin(overlay.get_width(), overlay.get_height()):
            self.manual_surface = surface
            self.camera_input_started(surface)
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.refresh_manual_controls()

    def manual_drag_update(self, _gesture, dx, dy):
        if self.manual_drag.update(dx, dy) and self.manual_timer is None:
            self.manual_timer = GLib.timeout_add(40, self.flush_manual_drag)

    def flush_manual_drag(self):
        if (not self.manual_ready or not self.manual_drag.active or not self.mouse_surface_available(self.manual_surface)
                or not self.controller or not self.preview.pipeline or self.closed or self.stop_pending):
            self.manual_timer = None; self.manual_drag.end(); return False
        # Zoom gets a turn between bounded movement pulses. Stale mouse input expires.
        if self.busy or self.wheel_zoom_timer is not None:
            return True
        self.manual_timer = None
        request = self.manual_drag.take()
        if request is None: return False
        controller = self.controller
        controller.cancel.clear()
        self.background(lambda: controller.manual_step(*request), lambda _result: None, quiet=True)
        return False

    def refresh_wheel_zoom_label(self):
        current = self.wheel_zoom.current
        text = _t('Zoom: {v0:g} %', v0=current) if current is not None else _t('Zoom: —')
        target = self.wheel_zoom.pending
        if target is None:
            target = self.wheel_zoom.inflight
        if target is not None:
            text += f" → {target:g} %"
        text += _t(' · G13 · Maus aus') if self.g13.active else _t(' · Mausrad')
        if self.detached_zoom_state is not None: self.detached_zoom_state.set_text(text)
        if self.gwen_window is not None: self.gwen_window.camera_zoom_state.set_text(text)

    def cancel_wheel_zoom(self, *, reset=False):
        if self.wheel_zoom_timer is not None:
            GLib.source_remove(self.wheel_zoom_timer)
            self.wheel_zoom_timer = None
        self.wheel_zoom.clear(reset=reset)
        self.wheel_zoom_surface = None
        self.refresh_wheel_zoom_label()

    def scroll_camera_zoom(self, _controller, _dx, dy, *, surface='detached'):
        if not self.mouse_surface_available(surface) or self.closed:
            return False
        if self.g13.active: return True
        if not self.controller or not self.preview.pipeline or self.stop_pending:
            return True
        if self.wheel_zoom_surface is not None and self.wheel_zoom_surface != surface:
            self.cancel_wheel_zoom()
        if self.wheel_zoom.scroll(dy):
            self.wheel_zoom_surface = surface
            self.camera_input_started(surface)
            self.zoom.set_value(self.wheel_zoom.pending)
            self.refresh_wheel_zoom_label()
            if self.wheel_zoom_timer is not None:
                GLib.source_remove(self.wheel_zoom_timer)
            self.wheel_zoom_timer = GLib.timeout_add(120, self.flush_wheel_zoom)
        elif self.wheel_zoom.current is None:
            self.notify(_t('Mausrad-Zoom wartet auf eine aktuelle Zoom-Rückmeldung der wachen Kamera.'), True)
        return True

    def flush_wheel_zoom(self):
        if (self.g13.active or self.closed or not self.mouse_surface_available(self.wheel_zoom_surface) or not self.controller
                or not self.preview.pipeline or self.stop_pending):
            self.wheel_zoom_timer = None
            self.wheel_zoom.clear()
            self.refresh_wheel_zoom_label()
            return False
        if self.busy:
            return True
        self.wheel_zoom_timer = None
        target = self.wheel_zoom.take()
        if target is None:
            return False
        controller = self.controller
        controller.cancel.clear()
        def done(result):
            if result.snapshot:
                self.update_state(result.snapshot)
            self.notify(result.message, not result.confirmed)
        def settled(error):
            self.wheel_zoom.complete(error is None)
            if error is not None:
                self.cancel_wheel_zoom(reset=True)
            elif self.wheel_zoom.pending is None and self.wheel_zoom.current is not None:
                self.zoom.set_value(self.wheel_zoom.current)
            self.refresh_wheel_zoom_label()
        self.background(lambda: controller.zoom(target), done, settled=settled)
        return False

    def overlay_update(self, kind, key, value):
        self.overlay_settings[kind][key] = value
        self.overlay_view.queue_draw()

    def overlay_toggle(self, kind, title):
        widget = Gtk.CheckButton(label=title)
        widget.set_active(self.overlay_settings[kind]["enabled"])
        widget.connect("toggled", lambda w: self.overlay_update(kind, "enabled", w.get_active()))
        return widget

    def overlays_ui(self):
        page = box(True, 12)
        page.append(label(_t('Einblendungen erscheinen in der Vorschau und im ausgelagerten Kamerafenster.'), "subtitle", True))
        card = self.card(_t('Text'))
        self.text_toggle = self.overlay_toggle("text", _t('Text einblenden')); card.append(self.text_toggle)
        self.overlay_text = Gtk.Entry(text=self.overlay_settings["text"]["text"], max_length=200)
        self.overlay_text.set_placeholder_text(_t('Dein Text …'))
        self.overlay_text.connect("changed", lambda w: self.overlay_update("text", "text", w.get_text()))
        card.append(self.overlay_text); page.append(card)
        card = self.card(_t('Uhrzeit'))
        self.clock_toggle = self.overlay_toggle("clock", _t('Uhrzeit einblenden')); card.append(self.clock_toggle)
        seconds = Gtk.CheckButton(label=_t('Mit Sekunden'), active=self.overlay_settings["clock"]["seconds"])
        seconds.connect("toggled", lambda w: self.overlay_update("clock", "seconds", w.get_active()))
        card.append(seconds); page.append(card)
        card = self.card(_t('Bild oder Logo'))
        self.image_toggle = self.overlay_toggle("image", _t('Bild einblenden')); card.append(self.image_toggle)
        self.image_name = label(Path(self.overlay_settings["image"]["path"]).name or _t('Kein Bild ausgewählt'), "subtitle", True)
        self.image_name.set_max_width_chars(32); card.append(self.image_name)
        row = box()
        row.append(self.button(_t('Bild auswählen …'), self.choose_overlay_image, controlled=False))
        row.append(self.button(_t('Entfernen'), self.clear_overlay_image, controlled=False)); card.append(row)
        card.append(label(_t('PNG mit Transparenz oder JPEG'), "subtitle")); page.append(card)
        card = self.card(_t('Position und Größe'))
        self.overlay_kind = Gtk.DropDown.new_from_strings([_t('Text'), _t('Uhrzeit'), _t('Bild / Logo')])
        self.overlay_kind.connect("notify::selected", lambda *_: self.load_overlay_controls())
        card.append(self.overlay_kind)
        self.overlay_spins = {}
        for key, title, minimum, maximum in [("x", _t('Waagerecht'), 0, 100), ("y", _t('Senkrecht'), 0, 100),
                                            ("size", _t('Größe'), 1, 50), ("opacity", _t('Deckkraft'), 0, 100)]:
            row = box(); title_widget = label(title + " (%)"); title_widget.set_hexpand(True); row.append(title_widget)
            control = spin(minimum, maximum, 1)
            control.set_hexpand(False); control.set_width_chars(4)
            control.connect("value-changed", lambda w, k=key: self.change_overlay_control(k, w.get_value()))
            self.overlay_spins[key] = control; row.append(control); card.append(row)
        card.append(label(_t('0 = links / oben · 100 = rechts / unten. Größe bezieht sich auf die Bildbreite.'), "subtitle", True))
        page.append(card); self.load_overlay_controls()
        page.append(self.button(_t('Overlays speichern'), self.save_overlays, controlled=False))
        page.append(label(_t('Die Einblendungen werden noch nicht an andere Kamera-Apps weitergegeben.'), "subtitle", True))
        return page

    def selected_overlay_kind(self):
        return ("text", "clock", "image")[self.overlay_kind.get_selected()]

    def load_overlay_controls(self):
        self.loading_overlay_controls = True
        try:
            layer = self.overlay_settings[self.selected_overlay_kind()]
            for key, control in self.overlay_spins.items(): control.set_value(layer[key])
        finally: self.loading_overlay_controls = False

    def change_overlay_control(self, key, value):
        if not self.loading_overlay_controls: self.overlay_update(self.selected_overlay_kind(), key, value)

    def choose_overlay_image(self):
        if self.image_chooser: self.image_chooser.show(); return
        chooser = Gtk.FileChooserNative.new(_t('Bild oder Logo auswählen'), self.window, Gtk.FileChooserAction.OPEN, _t('Auswählen'), _t('Abbrechen'))
        image_filter = Gtk.FileFilter(); image_filter.set_name(_t('PNG- und JPEG-Bilder'))
        image_filter.add_mime_type("image/png"); image_filter.add_mime_type("image/jpeg")
        chooser.add_filter(image_filter)
        chooser.connect("response", self.overlay_image_selected)
        self.image_chooser = chooser; chooser.show()

    def overlay_image_selected(self, chooser, response):
        try:
            if response == Gtk.ResponseType.ACCEPT:
                selected = chooser.get_file()
                path = selected.get_path() if selected else None
                if not path: raise ValueError(_t('Bitte ein Bild auf diesem Rechner auswählen.'))
                self.set_overlay_image(path)
        except (OSError, ValueError, GLib.Error) as exc: self.notify(str(exc), True)
        finally:
            chooser.destroy(); self.image_chooser = None

    def set_overlay_image(self, path):
        self.overlay_view.load_image(path)
        self.overlay_settings["image"]["path"] = str(Path(path).absolute())
        self.image_name.set_text(Path(path).name)
        self.image_toggle.set_active(True)
        self.overlay_kind.set_selected(2)

    def clear_overlay_image(self):
        self.overlay_view.load_image("")
        self.overlay_settings["image"]["path"] = ""
        self.image_toggle.set_active(False); self.image_name.set_text(_t('Kein Bild ausgewählt'))

    def save_overlays(self):
        try:
            self.overlay_store.save(self.overlay_settings)
            self.notify(_t('Overlays auf diesem PC gespeichert.'))
        except (OSError, ValueError) as exc: self.notify(str(exc), True)

    def load_image_controls(self, infos):
        self.actions = [w for w in self.actions if w not in self.image_actions]
        self.image_actions = []
        child=self.image_box.get_first_child()
        while child:
            following=child.get_next_sibling();self.image_box.remove(child);child=following
        self.image_box.append(label(_t('Bildeinstellungen'),"card-title"))
        names={"brightness":_t('Helligkeit'),"contrast":_t('Kontrast'),"saturation":_t('Sättigung'),"sharpness":_t('Schärfe'),"focus_auto":_t('Autofokus'),"white_balance_auto":_t('Automatischer Weißabgleich')}
        for key,(info,value) in infos.items():
            if key not in names: continue
            self.image_box.append(label(names[key],"subtitle"))
            row=box();value_spin=spin(info['min'],info['max'],info['step'],value)
            row.append(value_spin)
            button=self.button(_t('Setzen'),lambda k=key,w=value_spin:self.set_image(k,w.get_value()))
            button._can_write=info['writable'];self.image_actions.append(button)
            button.set_sensitive(info['writable'] and not self.busy)
            row.append(button);self.image_box.append(row)

    def presets_ui(self):
        card=self.card(_t('Positionen auf diesem PC'))
        row=box()
        for slot in (1,2,3):
            column=box(True,5);column.set_hexpand(True)
            column.append(self.button(_t('Position {v0}', v0=slot),lambda s=slot:self.recall(s)))
            column.append(self.button(_t('Ziel speichern'),lambda s=slot:self.save_preset(s),controlled=False))
            row.append(column)
        card.append(row);card.append(label(_t('Speichert die eingestellten Zielwinkel und den Zoomregler.'),"subtitle",True))
        return card

    def notify(self, message, error=False):
        if self.closed:return
        self.notice.set_text(message)
        self.notice.remove_css_class("warning")
        if error:self.notice.add_css_class("warning")
        self.log_lines.append(datetime.now().strftime("%H:%M:%S")+"  "+message)
        self.log_lines=self.log_lines[-150:]

    def refresh_actions(self):
        for widget in self.actions:
            widget.set_sensitive(self.controller is not None and not self.busy and getattr(widget,'_can_write',True))
        self.resolution.set_sensitive(not self.busy and not self.preview.pipeline)
        if not self.preview.pipeline:self.resolution.observed_label.set_text("")
        self.connect_button.set_sensitive(not self.busy)
        self.stop_button.set_sensitive(self.controller is not None and not self.stop_pending)
        self.refresh_manual_controls()

    def background(self, function, done, *, quiet=False, settled=None):
        if self.busy or self.closed:return
        self.busy=True;self.refresh_actions()
        if not quiet:self.notify(_t('Wird ausgeführt …'))
        future=self.executor.submit(function)
        def finished(future):
            try:value,error=future.result(),None
            except Exception as exc:value,error=None,exc
            GLib.idle_add(deliver,value,error)
        def deliver(value,error):
            if self.closed:return False
            self.busy=False;self.refresh_actions()
            if error:
                self.g13.disable()
                self.disable_manual()
                self.cancel_wheel_zoom(reset=True)
                if isinstance(error,OSError) and error.errno in (errno.ENODEV,errno.ENXIO,errno.EBADF,errno.ENOENT):
                    self.preview.stop()
                    if self.camera:self.camera.close()
                    self.camera=self.controller=None
                    self.connection.set_text(_t('Verbindung getrennt'))
                    self.mode_state.set_text(_t('Tracking: —'));self.zoom_state.set_text(_t('Zoom: —'))
                    self.detail_state.set_text(_t('Keine aktuelle Kamerarückmeldung.'))
                    self.empty.set_text(_t('Kamera getrennt'));self.empty.set_visible(True)
                    self.preview_button.set_label(_t('Vorschau starten'))
                    self.refresh_actions()
                self.notify(str(error),True)
            else:done(value)
            if settled is not None: settled(error)
            if self.stop_pending and self.controller:
                self.stop_pending=False
                self.run_action(self.controller.stop)
            return False
        future.add_done_callback(finished)

    def connect_camera(self):
        if self.busy:return False
        self.g13.disable()
        self.disable_manual()
        self.cancel_wheel_zoom(reset=True)
        self.stop_pending=False
        self.preview.stop();self.preview_button.set_label(_t('Vorschau starten'))
        previous=self.camera;self.camera=self.controller=None
        self.connection.set_text(_t('Verbinde …'))
        def work():
            if previous:previous.close()
            camera=device.connect(self.args.device)
            try:
                state=camera.status();infos={}
                for key in device.CONTROLS:
                    try:infos[key]=(camera.control_info(key),camera.get_control(key))
                    except OSError:pass
                return camera,state,infos,video_modes.available(camera.candidate.path)
            except BaseException:camera.close();raise
        def done(result):
            self.camera,state,infos,modes=result;self.controller=Controller(self.camera)
            self.resolution.set_catalog(modes)
            self.connection.set_text(_t('Tiny 2 verbunden'));self.connect_button.set_label(_t('Neu verbinden'))
            self.update_state(state);self.load_image_controls(infos);self.refresh_actions()
            self.notify(_t('Verbunden. Kameraeinstellungen wurden gelesen.'))
            self.empty.set_text(_t('Vorschau starten, um das Kamerabild zu sehen.'))
        def wrapped():
            try:return work()
            except Exception:
                GLib.idle_add(self.connection.set_text,_t('Nicht verbunden'))
                raise
        self.background(wrapped,done)
        return False

    def run_action(self, function):
        if not self.controller or self.busy:return
        self.g13.suspend_motion()
        self.disable_manual()
        self.cancel_wheel_zoom()
        self.controller.cancel.clear()
        def done(result):
            self.notify(result.message,not result.confirmed)
            if result.snapshot:self.update_state(result.snapshot)
        self.background(function,done)

    def update_state(self, state):
        self.g13.observe(state)
        if self.manual_ready and (not state['awake'] or state['mode'] != 'Aus'):
            self.disable_manual()
        self.wheel_zoom.observe(state['zoom_percent'] if state['awake'] else None)
        self.refresh_wheel_zoom_label()
        self.mode_state.set_text(_t('Tracking: ')+_t(state['mode']))
        self.zoom_state.set_text(_t('Zoom: ')+(str(state['zoom_percent'])+" %" if state['zoom_percent'] is not None else "—"))
        self.detail_state.set_text((_t('Wach') if state['awake'] else _t('Ruhemodus · Werte können veraltet sein'))+
            f"  ·  {_t(state['fov'])}  ·  {_t(state['speed'])}  ·  HDR {_t('an') if state['hdr'] else _t('aus')}")

    def poll(self):
        if self.closed:return False
        if self.camera and not self.busy and self.wheel_zoom_timer is None and self.manual_timer is None:
            self.background(self.camera.status,self.update_state,quiet=True)
        return True

    def move_target(self):
        pan,tilt=self.pan.get_value(),self.tilt.get_value()
        self.run_action(lambda:self.controller.move(pan,tilt))

    def apply_zoom(self):
        value=self.zoom.get_value()
        self.run_action(lambda:self.controller.zoom(value))

    def set_image(self,key,value):
        self.run_action(lambda:self.controller.image_control(key,value))

    def step_move(self, dp, dt):
        self.pan.set_value(self.pan.get_value()+dp*self.step.get_value())
        self.tilt.set_value(self.tilt.get_value()+dt*self.step.get_value())
        self.move_target()

    def center(self):
        self.pan.set_value(0);self.tilt.set_value(0);self.move_target()

    def stop(self):
        self.g13.disable()
        self.disable_manual()
        self.cancel_wheel_zoom()
        if not self.controller:return
        if self.busy:
            self.controller.cancel.set();self.stop_pending=True
            self.notify(_t('Stop angefordert …'));self.refresh_actions();return
        self.run_action(self.controller.stop)

    def save_preset(self, slot):
        try:
            self.preset_store.save(slot,self.pan.get_value(),self.tilt.get_value(),self.zoom.get_value())
            self.notify(_t('Zielwerte als Position {v0} auf diesem PC gespeichert.', v0=slot))
        except Exception as error:self.notify(str(error),True)

    def recall(self, slot):
        try:values=self.preset_store.get(slot)
        except Exception as error:self.notify(str(error),True);return
        self.pan.set_value(values['pan']);self.tilt.set_value(values['tilt']);self.zoom.set_value(values['zoom'])
        def work():
            result=self.controller.move(values['pan'],values['tilt'])
            self.controller.zoom(values['zoom'])
            return result
        self.run_action(work)

    def toggle_preview(self):
        if self.preview.pipeline:
            self.g13.disable()
            self.disable_manual()
            self.cancel_wheel_zoom()
            self.preview.stop();self.preview_button.set_label(_t('Vorschau starten'))
            self.empty.set_text(_t('Vorschau pausiert'));self.empty.set_visible(True);self.refresh_actions();return
        if not self.camera:return
        try:
            resolution=self.resolution.selected_mode()
            self.preview.start(self.camera.candidate.path,mode=resolution)
            self.preview_button.set_label(_t('Vorschau stoppen'))
            self.refresh_actions()
        except Exception as error:self.preview_error(str(error))

    def on_frame(self, texture):
        self.resolution.observed(texture,self.preview.negotiated)
        self.last_frame = (texture, self.preview.generation, time.monotonic())
        self.frames_seen+=1;self.picture.set_paintable(texture)
        self.overlay_view.set_frame_size(texture.get_width(), texture.get_height())
        self.empty.set_visible(self.args.smoke_test)
        if self.gwen_window is not None: self.gwen_window.on_camera_frame(texture)
        if self.book_window is not None: self.book_window.on_camera_frame(texture)

    def preview_error(self, error):
        self.refresh_actions()
        self.g13.disable()
        self.disable_manual()
        self.cancel_wheel_zoom()
        self.preview_button.set_label(_t('Vorschau starten'))
        self.empty.set_visible(True);self.empty.set_text(_t('Kein Kamerabild'))
        self.notify(_t('Vorschau: ')+error+_t(' · Gegebenenfalls andere Auflösung wählen oder andere Kamera-App schließen.'),True)

    def read_angles(self):
        def done(result):
            self.notify(_t('SDK-Rohwinkel: ')+", ".join(f"{x:.2f}°" for x in result['sdk_angles'])+
                        _t('. Achszuordnung und Genauigkeit sind noch nicht am Gerät bestätigt.'))
        self.background(self.controller.diagnostic_angles,done)

    def show_log(self):
        window=Gtk.Window(title=_t('Tiny 2 · Protokoll'),transient_for=self.window,default_width=760,default_height=420)
        view=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text("\n".join(self.log_lines) or _t('Noch keine Einträge.'))
        scroll=Gtk.ScrolledWindow();scroll.set_child(view);window.set_child(scroll);window.present()

    def smoke_finish(self):
        self.smoke_ok=self.window.get_realized() and self.frames_seen>0
        print(json.dumps({"gtk_window":self.window.get_realized(),"preview_frames":self.frames_seen,
                          "controls":len(self.actions),"camera_access":False}))
        try:
            if self.args.screenshot:
                # Use GTK's own render tree; no screen capture of other applications.
                paintable=Gtk.WidgetPaintable.new(self.window)
                snapshot=Gtk.Snapshot();paintable.snapshot(snapshot,self.window.get_width(),self.window.get_height())
                node=snapshot.to_node()
                texture=self.window.get_renderer().render_texture(node,None)
                if not texture.save_to_png(self.args.screenshot):
                    raise OSError(_t('Anwendungsbild konnte nicht gespeichert werden'))
        except Exception as error:
            self.smoke_ok=False
            print(_t('Screenshot fehlgeschlagen:'),error)
        self.close();self.quit();return False

    def close(self,*_):
        if self.closed: return False
        self.g13.close()
        self.disable_manual()
        if self.controller: self.controller.cancel.set()
        self.cancel_wheel_zoom(reset=True)
        self.closed=True;self.preview.stop()
        self.last_frame = None
        if self.gwen_window is not None: self.gwen_window.close()
        if self.book_window is not None: self.book_window.close()
        if self.scope_controls is not None: self.scope_controls.close()
        for window in list(self.drawing_windows): window.close()
        for window in list(self.share_windows): window.close()
        if self.cover_share is not None: self.cover_share.close(); self.cover_share = None
        self.overlay_view.stop()
        if self.image_chooser:
            self.image_chooser.destroy(); self.image_chooser = None
        if self.detached_window:
            window = self.detached_window; self.detached_window = None; window.destroy()
        camera, self.camera, self.controller = self.camera, None, None
        # Keep the descriptor open until an in-flight pulse has sent its final Stop.
        if camera: self.executor.submit(camera.close)
        self.executor.shutdown(wait=False,cancel_futures=False)
        return False


def run(args):
    Gtk.init()
    if Gdk.Display.get_default() is None:
        raise RuntimeError(_t('Keine Verbindung zum Desktop möglich'))
    application=Studio(args)
    result=application.run([])
    return (0 if application.smoke_ok else 2) if args.smoke_test else result
