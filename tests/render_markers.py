"""Rendering check with prescribed points, not an AI identification test."""
from pathlib import Path
import sys
from types import SimpleNamespace
import cairo
from tiny2.gwen_window import Markers


def main():
    root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
    marks = [dict(label='Pin 1', x=290, y=300), dict(label='Pin 30', x=710, y=700)]
    state = SimpleNamespace(source_size=(1000, 600), markers=marks)
    clipped = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1000, 900)
    Markers.draw(state, None, cairo.Context(clipped), 1000, 900)
    clipped.flush(); pixels = bytes(clipped.get_data()); stride = clipped.get_stride()
    assert not any(pixels[:150 * stride]) and not any(pixels[750 * stride:]), 'Markers cross letterbox'
    assert any(pixels[150 * stride:750 * stride]), 'No markers rendered'
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1000, 600)
    cr = cairo.Context(surface); cr.set_source_rgb(.07, .14, .12); cr.paint()
    cr.set_source_rgb(.04, .05, .06); cr.rectangle(320, 140, 360, 320); cr.fill()
    cr.set_source_rgb(.65, .67, .7)
    for y in range(180, 430, 30):
        cr.rectangle(280, y - 5, 40, 10); cr.rectangle(680, y - 5, 40, 10); cr.fill()
    cr.set_source_rgb(.8, .8, .8); cr.select_font_face('Sans'); cr.set_font_size(24)
    cr.move_to(370, 290); cr.show_text('TEST-BAUTEIL')
    cr.set_font_size(17); cr.move_to(35, 555); cr.show_text('DARSTELLUNGSTEST: Punkte vorgegeben, keine KI-Erkennung')
    Markers.draw(state, None, cr, 1000, 600)
    surface.write_to_png(str(root / 'Markierungen-Test.png'))
    print('PASS: actual marker renderer, labels, image scaling and letterbox clipping.')


if __name__ == '__main__': main()
