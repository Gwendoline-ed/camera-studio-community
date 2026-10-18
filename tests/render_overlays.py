"""Render the actual overlay drawing function to Cairo; no desktop or camera."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import cairo
from tiny2.overlays import DEFAULTS
from tiny2.overlay_view import OverlayView


def canvas(settings, image=None, size=(1280,720)):
    return SimpleNamespace(settings=settings, image=image, source_size=size, has_frame=True,
                           draw_error_reported=False, on_error=lambda message: print(message))


def render(state, width, height):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    OverlayView.draw(state, None, cr, width, height)
    assert not state.draw_error_reported, 'Overlay drawing failed'
    surface.flush()
    return surface


def main():
    from gi.repository import GdkPixbuf, GLib
    root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
    settings = deepcopy(DEFAULTS)
    empty = render(canvas(settings), 800, 450)
    assert not any(empty.get_data()), 'Disabled layers changed the image'
    # A partly transparent sample logo, generated only for the rendering test.
    logo = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 100)
    cr = cairo.Context(logo); cr.set_source_rgba(.12,.72,.62,.85); cr.rectangle(0,0,240,100); cr.fill()
    cr.set_source_rgb(1,1,1); cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(38); cr.move_to(20,64); cr.show_text('LOGO')
    logo_path = root/'test-logo.png'; logo.write_to_png(str(logo_path))
    # Use our generated pixels directly: this test needs neither the desktop
    # image-loader service nor permission to connect to the user's session bus.
    logo.flush(); source = bytes(logo.get_data()); rgba = bytearray()
    for i in range(0,len(source),4):
        b,g,r,a = source[i:i+4]
        rgba.extend((min(255,round(r*255/a)) if a else 0,
                     min(255,round(g*255/a)) if a else 0,
                     min(255,round(b*255/a)) if a else 0,a))
    image = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(rgba)),GdkPixbuf.Colorspace.RGB,True,8,240,100,960)
    settings['text'].update(enabled=True, text='Daniel · Werkbank', size=4)
    settings['clock'].update(enabled=True)
    settings['image'].update(enabled=True, path=str(logo_path), size=18)
    layer = render(canvas(settings,image), 1000, 800)
    # 16:9 video in 1000x800: top/bottom letterbox must remain untouched.
    stride = layer.get_stride(); data = bytes(layer.get_data())
    assert not any(data[:100*stride]), 'Overlay leaked into upper letterbox'
    assert not any(data[700*stride:]), 'Overlay leaked into lower letterbox'
    assert any(data[120*stride:680*stride]), 'Visible layers drew nothing'
    # All layers at zero opacity must be completely transparent.
    zero = deepcopy(settings)
    for item in zero.values(): item['opacity'] = 0
    assert not any(render(canvas(zero,image),1000,800).get_data())
    # Extremely small / portrait windows and literal markup must still render.
    long = deepcopy(settings); long['text'].update(text='<b>Das ist Text</b> '+('A'*170),size=50)
    render(canvas(long,image),120,900)
    # A synthetic background identifies this as a test, not a camera photograph.
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32,1000,800); cr = cairo.Context(out)
    cr.set_source_rgb(.035,.045,.065); cr.paint()
    cr.rectangle(0,118.75,1000,562.5); cr.set_source_rgb(.10,.17,.23); cr.fill()
    cr.set_line_width(1); cr.set_source_rgba(.6,.8,.9,.1)
    for x in range(0,1001,50): cr.move_to(x,119); cr.line_to(x,681)
    for y in range(119,682,50): cr.move_to(0,y); cr.line_to(1000,y)
    cr.stroke()
    cr.set_source_rgba(.8,.9,1,.6); cr.select_font_face('Sans'); cr.set_font_size(30)
    cr.move_to(270,400); cr.show_text('TESTBILD · keine Kameraaufnahme')
    cr.set_source_surface(layer,0,0); cr.paint(); out.write_to_png(str(root/'Overlay-Test.png'))
    print('PASS: actual drawing, transparency, video bounds, long text, extreme window sizes.')


if __name__ == '__main__': main()
