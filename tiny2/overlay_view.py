"""GTK/Cairo overlay plane aligned to the contained video, including letterboxing."""
from .i18n import tr as _t
from datetime import datetime
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_foreign("cairo")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango, PangoCairo
from .overlays import fitted_rect, positioned


class OverlayView(Gtk.DrawingArea):
    def __init__(self, settings, on_error):
        super().__init__()
        self.settings = settings
        self.on_error = on_error
        self.source_size = (1280, 720)
        self.has_frame = False
        self.image = None
        self.image_path = None
        self.draw_error_reported = False
        self.set_can_target(False)
        self.set_draw_func(self.draw)
        self.timer = GLib.timeout_add_seconds(1, self.tick)

    def tick(self):
        if self.settings["clock"]["enabled"]: self.queue_draw()
        return True

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer); self.timer = None

    def set_frame_size(self, width, height):
        if not self.has_frame or self.source_size != (width, height):
            self.source_size = (width, height)
            self.has_frame = True
            self.queue_draw()

    def load_image(self, path):
        if not path:
            self.image = None; self.image_path = None; self.queue_draw(); return
        p = Path(path)
        if not p.is_file() or p.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(_t('Bitte eine PNG- oder JPEG-Datei bis 16 MB auswählen.'))
        info, width, height = GdkPixbuf.Pixbuf.get_file_info(str(p))
        if not info or info.get_name() not in ("png", "jpeg") or width <= 0 or height <= 0 or width * height > 32_000_000:
            raise ValueError(_t('Unterstützt werden PNG/JPEG bis 32 Megapixel.'))
        image = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(p), 2048, 2048, True)
        self.image = image; self.image_path = str(p); self.queue_draw()

    def draw(self, _area, cr, width, height):
        if not self.has_frame: return
        rect = fitted_rect(width, height, *self.source_size)
        if not rect[2] or not rect[3]: return
        cr.save()
        try:
            cr.rectangle(*rect); cr.clip()
            layer = self.settings["image"]
            if layer["enabled"] and self.image is not None:
                w = rect[2] * layer["size"] / 100
                h = w * self.image.get_height() / self.image.get_width()
                if h > rect[3] * .95:
                    w *= rect[3] * .95 / h; h = rect[3] * .95
                x, y = positioned(rect, w, h, layer["x"], layer["y"])
                cr.save(); cr.translate(x, y)
                cr.scale(w / self.image.get_width(), h / self.image.get_height())
                Gdk.cairo_set_source_pixbuf(cr, self.image, 0, 0)
                cr.paint_with_alpha(layer["opacity"] / 100); cr.restore()
            for kind in ("text", "clock"):
                layer = self.settings[kind]
                if not layer["enabled"]: continue
                value = layer["text"] if kind == "text" else datetime.now().strftime("%H:%M:%S" if layer["seconds"] else "%H:%M")
                if not value: continue
                layout = PangoCairo.create_layout(cr)
                font = Pango.FontDescription("Sans Bold")
                font.set_absolute_size(max(1, rect[2] * layer["size"] / 100) * Pango.SCALE)
                layout.set_font_description(font)
                layout.set_width(int(rect[2] * .9 * Pango.SCALE))
                layout.set_wrap(Pango.WrapMode.WORD_CHAR)
                layout.set_height(-3); layout.set_ellipsize(Pango.EllipsizeMode.END)
                layout.set_text(value, -1)  # Plain text, never Pango markup.
                ink, logical = layout.get_pixel_extents()
                w, h = logical.width, logical.height
                # Fit tall text at extreme aspect ratios without crossing the image.
                scale = min(1, rect[3] * .9 / max(1, h))
                x, y = positioned(rect, w * scale, h * scale, layer["x"], layer["y"])
                cr.save(); cr.translate(x, y); cr.scale(scale, scale)
                alpha = layer["opacity"] / 100
                cr.move_to(1, 2); cr.set_source_rgba(0, 0, 0, alpha * .9)
                PangoCairo.show_layout(cr, layout)
                cr.move_to(0, 0); cr.set_source_rgba(1, 1, 1, alpha)
                PangoCairo.show_layout(cr, layout); cr.restore()
        except Exception as exc:
            if not self.draw_error_reported:
                self.draw_error_reported = True
                GLib.idle_add(self.on_error, _t('Overlay konnte nicht gezeichnet werden: ') + str(exc))
        finally:
            cr.restore()
