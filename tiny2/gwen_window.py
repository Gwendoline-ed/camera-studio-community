"""Explicit snapshot chat, image-anchored suggestions and push-to-record dictation."""
from .i18n import tr as _t
from datetime import datetime
import threading
import uuid
import gi
gi.require_version('Gtk', '4.0')
gi.require_foreign('cairo')
from gi.repository import Gtk, GLib, Gdk, Pango, PangoCairo
from .overlays import fitted_rect
from .gwen import GwenClient, MAX_IMAGE
from .ai_picker import AIPicker
from .ai_providers import LABELS
from .dictation import Recorder, Transcriber, whisper_paths


class Markers(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.source_size = (1280, 720)
        self.markers = []
        self.set_can_target(False)
        self.set_draw_func(self.draw)

    def draw(self, _area, cr, width, height):
        x, y, w, h = fitted_rect(width, height, *self.source_size)
        if not w or not h: return
        cr.save(); cr.rectangle(x, y, w, h); cr.clip()
        for index, marker in enumerate(self.markers):
            cr.new_path()  # Pango leaves a current point; never connect separate markers.
            px, py = x + marker['x'] * w / 1000, y + marker['y'] * h / 1000
            color = (0.2, 1, .75) if index % 2 == 0 else (1, .75, .2)
            cr.set_source_rgba(0, 0, 0, .8); cr.set_line_width(5)
            cr.arc(px, py, 8, 0, 6.283185307); cr.stroke()
            cr.set_source_rgb(*color); cr.set_line_width(2)
            cr.arc(px, py, 8, 0, 6.283185307); cr.stroke()
            cr.move_to(px - 13, py); cr.line_to(px + 13, py)
            cr.move_to(px, py - 13); cr.line_to(px, py + 13); cr.stroke()
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(Pango.FontDescription('Sans Bold 12'))
            layout.set_text(marker['label'], -1)
            layout.set_width(int(max(1, w - 12) * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            tw, th = layout.get_pixel_size()
            tx = max(x + 4, min(px + 16, x + w - tw - 6))
            ty = max(y + 4, min(py - th - 10, y + h - th - 6))
            cr.set_source_rgba(0, 0, 0, .85); cr.rectangle(tx - 3, ty - 2, tw + 6, th + 4); cr.fill()
            cr.set_source_rgb(*color); cr.move_to(tx, ty); PangoCairo.show_layout(cr, layout)
        cr.new_path()
        cr.restore()


def button(title, callback):
    result = Gtk.Button(label=_t(title))
    result.connect('clicked', lambda _: callback())
    return result


class GwenWindow(Gtk.ApplicationWindow):
    def __init__(self, application, capture, on_close, *, scope=None):
        super().__init__(application=application, title=_t('KI · ')+(scope.source.name if scope else _t('Kamerachat')))
        self.scope=scope
        self.source_name=scope.source.name if scope else 'Tiny 2'
        self.capture = capture
        self.on_close = on_close
        self.closed = self.busy = False
        self.client = self.transcriber = None
        self.frame = None
        self.frame_texture = None
        self.frame_caption = _t('Noch kein Standbild')
        self.history = []
        self.transcript = ''
        self.provider_sessions = {}
        self.cancelled = False
        self.recorder = Recorder(self.recorded, self.recording_error)
        self.set_default_size(1140, 720)
        self.connect('close-request', self.close_chat)
        if scope is None:self.connect('notify::is-active', application.manual_focus_changed)
        self.connect('notify::is-active', application.g13.focus_changed)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.camera_key)
        self.add_controller(keys)
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label=_t('KI · ')+self.source_name+_t(' · Kamera und Diktat')))
        self.set_titlebar(header)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top', 'bottom', 'start', 'end'): getattr(outer, 'set_margin_' + side)(14)
        self.set_child(outer)
        body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True); body.set_position(660); outer.append(body)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.caption = Gtk.Label(label=_t('Noch kein Kamerabild'), xalign=0)
        left.append(self.caption)
        overlay = self.overlay = Gtk.Overlay(); overlay.set_vexpand(True); overlay.add_css_class('preview')
        self.picture = Gtk.Picture(); self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_can_shrink(True); self.picture.set_size_request(320, 180)
        overlay.set_child(self.picture)
        self.markers = Markers(); overlay.add_overlay(self.markers); left.append(overlay)
        self.wheel_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        self.wheel_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.wheel_controller.connect('scroll', scope.scroll if scope else
            lambda c, x, y: application.scroll_camera_zoom(c, x, y, surface='gwen'))
        overlay.add_controller(self.wheel_controller)
        if scope is None:
            self.drag_controller = Gtk.GestureDrag.new(); self.drag_controller.set_button(1)
            self.drag_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.drag_controller.connect('drag-begin', lambda g, x, y: application.manual_drag_begin(g, x, y, surface='gwen'))
            self.drag_controller.connect('drag-update', application.manual_drag_update)
            for event in ('drag-end', 'cancel'):
                self.drag_controller.connect(event, lambda *_: application.end_manual_drag('gwen'))
            overlay.add_controller(self.drag_controller)
            motion = Gtk.EventControllerMotion.new()
            motion.connect('leave', lambda *_: application.end_manual_drag('gwen'))
            overlay.add_controller(motion)
        camera_controls = Gtk.Box(spacing=8)
        self.live_button = Gtk.ToggleButton(label=_t('Livebild'))
        self.live_button.connect('toggled', self.live_changed); camera_controls.append(self.live_button)
        self.manual_button=None
        if scope is None:
            self.manual_button = Gtk.ToggleButton(label=_t('Maus'))
            self.manual_button.set_tooltip_text(_t('Linke Maustaste im Bild halten und ziehen · Mausrad zoomt die Kamera'))
            self.manual_button.connect('toggled', lambda b: application.toggle_manual(b, surface='gwen'))
            camera_controls.append(self.manual_button)
        self.g13_button = application.g13.make_toggle(short=True); camera_controls.append(self.g13_button)
        self.camera_stop_button = button(_t('■ Stop'), application.g13.disable if scope else application.stop)
        self.camera_stop_button.add_css_class('destructive-action'); camera_controls.append(self.camera_stop_button)
        left.append(camera_controls)
        self.camera_zoom_state = Gtk.Label(xalign=0, label=scope.zoom_label() if scope and scope.source.backend=='andonstar' else '')
        left.append(self.camera_zoom_state)
        hint = Gtk.Label(label=(_t('Andonstar: Mausrad / G2/G3 Bildzoom · G4 zurücksetzen') if scope.source.backend=='andonstar'
            else _t('Vergrößerung und Fokus am Mikroskop einstellen.')) if scope else
            _t('Maus: im Bild ziehen · Mausrad: Zoom · G13: G2/G3 Zoom'), xalign=0, wrap=True)
        hint.add_css_class('subtitle'); left.append(hint)
        self.g13_status = Gtk.Label(xalign=0, wrap=True)
        self.g13_status.add_css_class('subtitle'); left.append(self.g13_status)
        application.g13.labels.append(self.g13_status)
        self.mark_note = Gtk.Label(label=_t('Markierungen bleiben an diesem Standbild.'), xalign=0, wrap=True)
        self.mark_note.add_css_class('subtitle'); left.append(self.mark_note)
        image_actions = Gtk.Box(spacing=8)
        self.image_button = button(_t('Bild aktualisieren'), self.capture_image); image_actions.append(self.image_button)
        self.share_button = button(_t('Bild teilen …'), self.share_image); image_actions.append(self.share_button)
        self.draw_button = button(_t('Zeichnen …'), self.draw_image); image_actions.append(self.draw_button)
        left.append(image_actions)
        self.fresh_image = Gtk.CheckButton(label=_t('Beim Senden aktuelles Kamerabild holen'), active=True)
        left.append(self.fresh_image)
        body.set_start_child(left); body.set_shrink_start_child(True)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_margin_start(12)
        self.ai_picker=AIPicker(application,self.provider_changed);right.append(self.ai_picker)
        self.active_provider=self.ai_picker.provider
        self.chat_view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.chat_view.set_left_margin(10); self.chat_view.set_right_margin(10)
        self.chat_scroll = Gtk.ScrolledWindow(); self.chat_scroll.set_vexpand(True)
        self.chat_scroll.set_min_content_width(300); self.chat_scroll.set_child(self.chat_view)
        right.append(self.chat_scroll)
        self.entry = Gtk.Entry(max_length=4000, placeholder_text=_t('Z. B.: Markiere Pin 1 und 30 dieses ICs …'))
        self.entry.connect('activate', lambda _: self.send()); right.append(self.entry)
        row = Gtk.Box(spacing=8)
        self.mic_button = button(_t('Diktieren'), self.dictate); row.append(self.mic_button)
        self.send_button = button(_t('Senden'), self.send)
        self.send_button.add_css_class('suggested-action'); row.append(self.send_button)
        self.cancel_button = button(_t('Abbrechen'), self.cancel_job); row.append(self.cancel_button)
        right.append(row)
        self.clear_button = button(_t('Chat leeren'), self.clear_chat); right.append(self.clear_button)
        body.set_end_child(right); body.set_shrink_end_child(True)
        self.status = Gtk.Label(label=_t('Bereit. Ein Bild wird erst beim Senden an KI übergeben.'), xalign=0, wrap=True)
        self.status.add_css_class('notice'); outer.append(self.status)
        self.append_chat('KI', _t('Stelle eine Frage zum Kamerabild. Beim Senden wird ein Standbild analysiert. Für Details oder Markierungen möglichst scharf aufnehmen.'))
        self.refresh(); self.capture_image()

    def provider_changed(self,provider):
        self.provider_sessions[self.active_provider]=(list(self.history),self.transcript)
        self.active_provider=provider
        self.history,self.transcript=self.provider_sessions.get(provider,([],''))
        self.history=list(self.history);self.chat_view.get_buffer().set_text(self.transcript)
        self.markers.markers=[];self.markers.queue_draw()
        self.mark_note.set_text(_t('Anbieter gewechselt. Neue Antwort gehört zum ausgewählten Anbieter.'))
        self.status.set_text(_t(LABELS[provider])+_t(' ausgewählt · separater Verlauf · Wechsel sendet kein Bild.'))

    def camera_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            if self.scope:self.get_application().g13.disable()
            else:self.get_application().stop()
            return True
        return False

    def live_changed(self, _button):
        live = self.live_button.get_active()
        self.markers.set_visible(not live)
        if live:
            self.caption.set_text(_t('Livebild · KI erhält nur das Standbild beim Senden'))
            self.mark_note.set_visible(False)
            app = self.get_application()
            if self.scope:
                try:self.on_camera_frame(self.capture())
                except Exception as error:self.status.set_text(str(error))
            elif app.last_frame is not None:self.on_camera_frame(app.last_frame[0])
        else:
            app = self.get_application()
            app.g13.suspend_motion()
            if self.scope is None:
                app.end_manual_drag('gwen')
                if app.wheel_zoom_surface == 'gwen': app.cancel_wheel_zoom()
            self.picture.set_paintable(self.frame_texture)
            self.caption.set_text(self.frame_caption)
            self.mark_note.set_visible(True)

    def on_camera_frame(self, texture):
        if not self.closed and self.live_button.get_active(): self.picture.set_paintable(texture)

    def refresh(self):
        recording = self.recorder.pipeline is not None
        self.ai_picker.set_sensitive(not self.closed and not self.busy and not recording)
        ready = not self.closed and not self.busy and not recording
        for widget in (self.send_button, self.image_button, self.clear_button, self.fresh_image):
            widget.set_sensitive(ready)
        self.share_button.set_sensitive(ready and self.frame is not None)
        self.draw_button.set_sensitive(ready and self.frame is not None)
        self.mic_button.set_sensitive(not self.closed and not self.busy)
        self.mic_button.set_label(_t('■ Diktat beenden') if recording else _t('Diktieren'))
        self.cancel_button.set_sensitive(self.busy or recording)

    def append_chat(self, who, text):
        self.transcript = (self.transcript + f'{who}:\n{text}\n\n')[-60000:]
        buffer = self.chat_view.get_buffer(); buffer.set_text(self.transcript)
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.chat_view.scroll_mark_onscreen(mark); buffer.delete_mark(mark)

    def capture_image(self):
        if self.busy or self.closed: return False
        try:
            texture = self.capture()
            png = bytes(texture.save_to_png_bytes().get_data())
            if len(png) > MAX_IMAGE: raise ValueError(_t('Bild zu groß. Bitte eine kleinere Vorschauauflösung wählen.'))
            frame_id = uuid.uuid4().hex
            self.frame = (png, frame_id)
            self.frame_texture = texture
            self.frame_caption = _t('Standbild · ') + datetime.now().strftime('%H:%M:%S')
            self.get_application().g13.suspend_motion()
            self.live_button.set_active(False)
            self.picture.set_paintable(texture)
            self.markers.source_size = (texture.get_width(), texture.get_height())
            self.markers.markers = []; self.markers.queue_draw()
            self.caption.set_text(self.frame_caption)
            self.mark_note.set_text(_t('Dieses Bild wird mit deiner nächsten Nachricht an KI gesendet.'))
            self.status.set_text(_t('Bild bereit.')); self.refresh(); return True
        except Exception as error:
            self.status.set_text(str(error)); return False

    def share_image(self):
        if self.frame is not None and not self.busy:
            try:self.get_application().open_share(self.action_texture(),self,source_name=self.source_name)
            except Exception as error:self.status.set_text(str(error))

    def draw_image(self):
        if self.frame is not None and not self.busy:
            try:self.get_application().open_drawing(self.action_texture(),self.accept_drawing,self,source_name=self.source_name)
            except Exception as error:self.status.set_text(str(error))

    def action_texture(self):
        return self.capture() if self.live_button.get_active() else self.frame_texture

    def accept_drawing(self, texture):
        if self.closed or self.busy: raise RuntimeError(_t('KI-Chat ist gerade nicht bereit.'))
        png = bytes(texture.save_to_png_bytes().get_data())
        if len(png)>MAX_IMAGE: raise ValueError(_t('Bearbeitetes Bild ist zu groß für KI.'))
        self.frame = (png, uuid.uuid4().hex); self.frame_texture = texture
        self.frame_caption = _t('Bearbeitetes Standbild · ') + datetime.now().strftime('%H:%M:%S')
        self.live_button.set_active(False); self.picture.set_paintable(texture)
        self.caption.set_text(self.frame_caption); self.markers.markers = []; self.markers.queue_draw()
        self.markers.source_size = (texture.get_width(), texture.get_height())
        self.fresh_image.set_active(False)
        self.mark_note.set_text(_t('Dieses bearbeitete Standbild wird mit deiner nächsten Nachricht gesendet.'))
        self.status.set_text(_t('Zeichnung übernommen. Frage eingeben oder diktieren und senden.')); self.refresh()

    def work(self, function, done):
        self.busy = True; self.cancelled = False; self.refresh()
        def worker():
            try: value, error = function(), None
            except Exception as exc: value, error = None, exc
            GLib.idle_add(deliver, value, error)
        def deliver(value, error):
            if self.closed: return False
            self.busy = False
            self.client = self.transcriber = None
            self.refresh()
            if self.cancelled: self.status.set_text(_t('Abgebrochen.'))
            elif error: self.status.set_text(str(error))
            else: done(value)
            return False
        threading.Thread(target=worker, name='tiny2-gwen', daemon=True).start()

    def send(self):
        if self.busy or self.closed or self.recorder.pipeline is not None: return
        prompt = self.entry.get_text().strip()
        if not prompt: self.status.set_text(_t('Bitte eine Frage eingeben oder diktieren.')); return
        try:
            client=GwenClient(self.ai_picker.provider);client.configured()
        except (OSError,ValueError,RuntimeError) as error:self.status.set_text(str(error));return
        self.ai_picker.update_notice()
        if (self.fresh_image.get_active() or self.frame is None) and not self.capture_image(): return
        self.live_button.set_active(False)
        png, frame_id = self.frame
        self.markers.markers = []; self.markers.queue_draw()
        history = list(self.history)
        self.append_chat(_t('Du'), prompt); self.entry.set_text('')
        self.client=client;provider_label=self.ai_picker.label
        self.status.set_text(provider_label+_t(' betrachtet das Standbild …'))
        def done(reply):
            if self.frame is None or self.frame[1] != frame_id: return
            self.history.extend([{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': reply['answer']}])
            self.history = self.history[-8:]
            self.append_chat(provider_label, reply['answer'])
            self.markers.markers = reply['markers']; self.markers.queue_draw()
            self.mark_note.set_text(reply['note'])
            self.status.set_text(_t('Antwort zum Standbild erhalten · Livebild ausschalten, um die Markierungen zu sehen.')
                                 if self.live_button.get_active() else _t('Antwort erhalten.'))
        self.work(lambda: client.chat(prompt, png, frame_id, history), done)

    def dictate(self):
        if self.closed or self.busy: return
        if self.recorder.pipeline is not None:
            self.recorder.finish(); return
        try:
            whisper_paths()  # Check availability before opening the microphone.
            self.recorder.start()
            self.status.set_text(_t('Mikrofon nimmt auf · zum Beenden erneut klicken · höchstens 60 Sekunden.'))
            self.refresh()
        except Exception as error: self.recording_error(str(error))

    def recording_error(self, error):
        self.recorder.stop(); self.refresh(); self.status.set_text(error)

    def recorded(self, pcm):
        if self.closed: return
        self.transcriber = Transcriber(); transcriber = self.transcriber
        self.status.set_text(_t('Diktat wird lokal in Text umgewandelt …'))
        def done(text):
            if not text.strip(): self.status.set_text(_t('Keine Sprache erkannt.')); return
            previous = self.entry.get_text().strip()
            combined = (previous + ' ' + text).strip()
            self.entry.set_text(combined[:4000])
            self.status.set_text(_t('Diktat eingefügt. Bitte prüfen und mit Senden abschicken.')
                                 if len(combined) <= 4000 else _t('Diktat auf 4000 Zeichen gekürzt. Bitte vor dem Senden prüfen.'))
        self.work(lambda: transcriber.transcribe(pcm), done)

    def cancel_job(self):
        self.cancelled = True
        self.recorder.stop()
        if self.client is not None: self.client.cancel()
        if self.transcriber is not None: self.transcriber.cancel()
        self.status.set_text(_t('Abgebrochen.')); self.refresh()

    def clear_chat(self):
        if self.busy or self.recorder.pipeline is not None: return
        self.history = []; self.transcript = ''
        self.chat_view.get_buffer().set_text('')
        self.markers.markers = []; self.markers.queue_draw()
        self.mark_note.set_text(_t('Markierungen gelöscht.')); self.status.set_text(_t('Chat geleert.'))

    def close_chat(self, *_):
        if not self.closed:
            self.closed = True; self.cancel_job()
            app = self.get_application()
            app.g13.remove_button(self.g13_button)
            if self.g13_status in app.g13.labels: app.g13.labels.remove(self.g13_status)
            self.frame = self.frame_texture = None; self.history = [];self.provider_sessions={}
            self.on_close()
        return False
