"""GTK integration for the existing G13 daemon and serialized camera worker."""
from .i18n import tr as _t
import time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from .controller import Result
from .g13_input import Input, Subscription, request, verify_profile, PROFILE_ID


class G13Controls:
    def __init__(self, app):
        self.app = app
        self.input = Input()
        self.enabled = self.pending = False
        self.epoch = 0
        self.client = None
        self.timer = None
        self.buttons = []
        self.labels = []
        self.updating = False
        self.camera_awake = False
        self.camera_mode = None
        self.last_zoom = 0
        self.input_target = None

    @property
    def active(self): return self.enabled or self.pending

    def make_toggle(self, short=False):
        widget = Gtk.ToggleButton()
        widget.connect('toggled', self.toggled)
        self.buttons.append((widget, short)); self.refresh()
        return widget

    def page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card = self.app.card(_t('G13 · Kamerasteuerung'))
        card.append(self.make_toggle())
        status = Gtk.Label(label=_t('G13 ist aus.'), xalign=0, wrap=True)
        status.add_css_class('subtitle'); self.labels.append(status); card.append(status)
        hint = Gtk.Label(label=_t('M2: Tiny 2 Studio · Steuerung für das aktive Kamera-, KI- oder Scope-Fenster. G13 an sperrt Maussteuerung und Mausrad-Zoom.'), xalign=0, wrap=True)
        card.append(hint)
        card.append(Gtk.Label(label=_t('Bewegungstempo'), xalign=0))
        speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2, 25, 1)
        speed.set_value(self.input.speed); speed.set_digits(0)
        speed.connect('value-changed', lambda w: setattr(self.input, 'speed', w.get_value()))
        card.append(speed); page.append(card)
        mapping = self.app.card(_t('Belegung auf M2'))
        for line in (_t('Stick: Schwenken und Neigen'), _t('G15 halten: fein bewegen'),
                     _t('G1 / G22 / Stick drücken: Stop, G13 aus'), _t('G2 / G3: weiter / näher zoomen'),
                     _t('G4: Mitte · G5 / G6 / G7: Position 1 / 2 / 3'),
                     _t('G8: Tracking aus · G9: Hand · G10: Person'),
                     _t('G11: Bild auslagern / andocken'), _t('G12: KI-Chat · G13: Bild teilen'),
                     _t('G14: Vollbild im Kamerafenster'), _t('G16: Buchscan / Seite aufnehmen'),
                     _t('G17: geprüfte Buchseite übernehmen'),
                     _t('Andonstar-Fenster oder dessen KI-Chat: G2/G3 Bildzoom · G4 Zoom zurücksetzen'),
                     _t('Scope: G12 eigener KI-Chat · G13 eigenes Bild teilen · keine Tiny-Bewegung')):
            mapping.append(Gtk.Label(label=line, xalign=0, wrap=True))
        page.append(mapping)
        note = Gtk.Label(label=_t('Nach Fokus- oder Profilwechsel den Stick zunächst loslassen. Bei aktivem Tracking mit G8 zurück zur Sticksteuerung. Die gespeicherten Positionen sind die bisherigen Zielwerte.'), xalign=0, wrap=True)
        note.add_css_class('subtitle'); page.append(note)
        return page

    def status(self, text):
        for label in self.labels: label.set_text(text)

    def refresh(self):
        self.updating = True
        for button, short in self.buttons:
            button.set_active(self.active)
            button.set_label((_t('G13 ✓') if self.active else 'G13') if short
                             else (_t('G13 ausschalten') if self.active else _t('G13 aktivieren')))
        self.updating = False
        self.app.refresh_manual_controls()
        self.app.refresh_wheel_zoom_label()

    def toggled(self, button):
        if self.updating: return
        self.enable() if button.get_active() else self.disable()

    def enable(self):
        app = self.app
        if self.active: return
        controls=getattr(app,'scope_controls',None)
        scope_ready=bool(controls and any(c.ready() for c in controls.channels.values()))
        use_scope=bool(self.scope_target() or (scope_ready and controls.is_active()))
        tiny_ready=bool(app.controller and app.preview.pipeline)
        if app.closed or app.busy or not (scope_ready or tiny_ready):
            self.refresh(); self.status(_t('Bitte Kamera- oder Scope-Vorschau starten.')); return
        use_scope=use_scope or not tiny_ready
        app.disable_manual(); app.cancel_wheel_zoom()
        self.pending = True; self.epoch += 1; epoch = self.epoch
        self.input.suspend(); self.refresh(); self.status(_t('G13 wird aktiviert …'))
        controller = app.controller
        if controller and not use_scope:controller.cancel.clear()
        def prepare():
            profile = request({'cmd': 'get_profile', 'id': PROFILE_ID}).get('profile')
            verify_profile(profile)
            if not self.pending or epoch != self.epoch: return Result(_t('G13-Aktivierung abgebrochen'))
            request({'cmd': 'switch_profile', 'id': PROFILE_ID})
            if not self.pending or epoch != self.epoch: return Result(_t('G13-Aktivierung abgebrochen'))
            return Result(_t('G13 für Scope bereit')) if use_scope else controller.mode('Aus')
        def done(result):
            if not self.pending or epoch != self.epoch: return
            if result.snapshot: app.update_state(result.snapshot)
            self.pending = False; self.enabled = True
            self.client = Subscription(); self.client.start()
            self.timer = GLib.timeout_add(40, self.tick)
            self.refresh(); self.status(_t('M2 aktiv · Stick loslassen, dann steuern.'))
            app.notify(_t('G13 aktiv. Maussteuerung und Mausrad-Zoom sind gesperrt.'))
        def settled(error):
            if error is not None:
                self.disable(); self.status(_t('G13 konnte nicht aktiviert werden: ') + str(error))
        app.background(prepare, done, settled=settled)

    def suspend_motion(self): self.input.suspend()

    def focus_changed(self, *_):
        if self.active and not self.focused(): self.suspend_motion()

    def scope_target(self):
        controls=getattr(self.app,'scope_controls',None)
        return controls.focused_channel() if controls else None

    def focused(self):
        return self.scope_target() is not None or any(w is not None and w.is_active() for w in
                   (getattr(self.app, 'window', None), self.app.detached_window, self.app.gwen_window, self.app.book_window))

    def observe(self, state):
        self.camera_awake = bool(state['awake']); self.camera_mode = state['mode']
        if not self.camera_awake or self.camera_mode != 'Aus': self.input.stop_motion()

    def tick(self):
        app = self.app
        if not self.enabled or app.closed: self.timer = None; return False
        state, error = self.client.latest()
        scope=self.scope_target()
        target=scope if scope is not None else 'tiny' if self.focused() else None
        if target!=self.input_target:
            self.suspend_motion();self.input_target=target
        available = scope.ready() if scope else bool(app.controller and app.preview.pipeline and self.camera_awake and not app.stop_pending)
        result = self.input.evaluate(state, available and self.focused())
        self.status(error or result['note'])
        if not available: self.status(_t('Bitte eine laufende Kamera- oder Scope-Vorschau starten.'))
        if scope is not None:return self.tick_scope(scope,result)
        if 'stop' in result['actions']:
            self.disable(); app.stop(); return False
        if app.busy or app.wheel_zoom_timer is not None:
            if result['actions']: self.status(_t('Kamera arbeitet noch · Taste danach erneut drücken.'))
            return True
        if result['actions']:
            self.suspend_motion(); self.action(result['actions'][0]); return True
        if result['zoom'] and time.monotonic() - self.last_zoom >= .22:
            current = app.wheel_zoom.current
            if current is not None:
                target = min(100, max(0, current + 5 * result['zoom']))
                if target != current:
                    app.camera_input_started()
                    controller = app.controller; controller.cancel.clear(); self.last_zoom = time.monotonic()
                    def done(response):
                        if response.snapshot: app.update_state(response.snapshot)
                        app.zoom.set_value(app.wheel_zoom.current)
                    app.background(lambda: controller.zoom(target), done, quiet=True)
            return True
        if result['motion']:
            if self.camera_mode != 'Aus':
                self.input.stop_motion(); self.status(_t('Tracking aktiv · G8 schaltet zurück zur Sticksteuerung.'))
            else:
                app.camera_input_started()
                controller = app.controller; controller.cancel.clear()
                motion = result['motion']
                app.background(lambda: controller.manual_step(*motion), lambda _: None, quiet=True)
        return True

    def tick_scope(self,scope,result):
        # Consume microscope input here, even for unsupported actions. Never fall
        # through to Tiny PTZ, tracking, presets or book capture.
        if 'stop' in result['actions']:
            self.disable();return False
        if result['actions']:
            self.suspend_motion();name=result['actions'][0]
            if name=='gwen':scope.open_gwen()
            elif name=='share':
                if scope.chat and scope.chat.is_active():scope.chat.share_image()
                else:scope.share()
            elif name=='center':scope.reset_zoom()
            elif name=='fullscreen':scope.toggle_fullscreen()
            elif name=='detach':scope.show()
            else:self.status(_t('Diese Taste steuert nur die Tiny-Kamera. Fokus und Vergrößerung am Scope einstellen.'))
        elif result['zoom'] and time.monotonic()-self.last_zoom>=.22:
            scope.zoom_by(result['zoom']);self.last_zoom=time.monotonic()
            self.status(scope.source.name+' · '+scope.zoom_label() if scope.source.backend=='andonstar'
                        else _t('Vergrößerung am Mikroskop einstellen.'))
        elif result['motion']:
            self.input.stop_motion();self.status(_t('Scope: G2/G3 für Andonstar-Bildzoom. Position am Mikroskop einstellen.'))
        return True

    def action(self, name):
        app = self.app
        if name == 'center' or name.startswith(('position', 'tracking_')): app.camera_input_started()
        if name == 'center': app.center()
        elif name.startswith('position'): app.recall(int(name[-1]))
        elif name.startswith('tracking_'):
            mode = {'tracking_off': 'Aus', 'tracking_hand': 'Hand', 'tracking_normal': 'Normal'}[name]
            controller = app.controller; app.run_action(lambda: controller.mode(mode))
        elif name == 'detach': app.toggle_detached()
        elif name == 'gwen': app.open_gwen()
        elif name == 'book_capture':
            if app.book_window is not None and app.book_window.is_active(): app.book_window.capture_page()
            else: app.open_book()
        elif name == 'book_accept':
            if app.book_window is not None and app.book_window.is_active(): app.book_window.accept_pending()
        elif name == 'share':
            if app.gwen_window is not None and app.gwen_window.is_active(): app.gwen_window.share_image()
            else: app.open_share()
        elif name == 'fullscreen':
            if app.detached_window is None: app.toggle_detached()
            app.toggle_fullscreen()

    def disable(self):
        self.enabled = self.pending = False; self.epoch += 1
        self.input_target=None
        self.input.suspend()
        if self.timer is not None: GLib.source_remove(self.timer); self.timer = None
        if self.client is not None: self.client.close(); self.client = None
        self.refresh(); self.status(_t('G13 ist aus · Mausrad-Zoom wieder verfügbar.'))

    def remove_button(self, widget):
        self.buttons = [(button, short) for button, short in self.buttons if button is not widget]

    def close(self):
        self.disable(); self.buttons.clear(); self.labels.clear()
