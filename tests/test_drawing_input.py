"""Regression tests for competing GTK mouse/stylus pointer sequences."""
import io
from types import SimpleNamespace as NS
import unittest
from PIL import Image
from tiny2.drawing import Ink
from tiny2.drawing_window import DrawingWindow
from gi.repository import Gtk,Gdk


class Surface:
    """Drawing callbacks with real ink and deterministic widget values."""
    def __init__(self):
        self.ink=Ink();self.active_input=None;self.mouse_start=None
        self.canvas=NS(queue_draw=lambda:None);self.status=NS(set_text=lambda _:None)
        self.color=NS(get_rgba=lambda:NS(red=1,green=0,blue=0))
        self.tool=NS(get_selected=lambda:0);self.width=NS(get_value=lambda:12)
        self.pressure=NS(get_active=lambda:True)
    def position(self,x,y):return (x,y) if 0<=x<200 and 0<=y<200 else None
    begin=DrawingWindow.begin
    update=DrawingWindow.update
    finish=DrawingWindow.finish
    pen_pressure=DrawingWindow.pen_pressure
    stylus_down=DrawingWindow.stylus_down
    stylus_move=DrawingWindow.stylus_move
    stylus_up=DrawingWindow.stylus_up
    stylus_cancel=DrawingWindow.stylus_cancel
    mouse_down=DrawingWindow.mouse_down
    mouse_move=DrawingWindow.mouse_move
    mouse_up=DrawingWindow.mouse_up
    mouse_cancel=DrawingWindow.mouse_cancel


class Gesture:
    def __init__(self,on_claim=lambda:None,tool=None):
        self.on_claim=on_claim;self.tool=tool;self.pressure=.3;self.state=None
    def get_device_tool(self):return self.tool
    def get_current_event(self):return NS(get_device_tool=lambda:self.tool)
    def get_axis(self,_):return True,self.pressure
    def set_state(self,state):
        self.state=state
        if state==Gtk.EventSequenceState.CLAIMED:self.on_claim()


class DrawingInputTests(unittest.TestCase):
    def test_pen_claim_cancelling_mouse_keeps_continuous_pressure_stroke(self):
        surface=Surface();pen=Gesture(surface.mouse_cancel)
        surface.stylus_down(pen,20,50)
        surface.mouse_up(Gesture(),0,0)  # A late drag-end from the losing gesture.
        pen.pressure=.9;surface.stylus_move(pen,100,50);surface.stylus_up(pen,180,50)
        stroke=surface.ink.strokes[0]
        self.assertEqual(len(stroke['points']),3)
        self.assertEqual([p[2] for p in stroke['points']],[.3,.9,.9])
        original=io.BytesIO();Image.new('RGB',(200,200),'white').save(original,format='PNG')
        rendered=Image.open(io.BytesIO(surface.ink.render(original.getvalue())))
        self.assertEqual(rendered.getpixel((140,50))[:3],(255,0,0))
        surface.ink.undo();self.assertEqual(surface.ink.strokes,[])
        surface.ink.redo();self.assertEqual(len(surface.ink.strokes),1)

    def test_mouse_claim_cancelling_pen_keeps_drag_and_release_position(self):
        surface=Surface();mouse=Gesture(surface.stylus_cancel)
        surface.mouse_down(mouse,20,70);surface.stylus_up(Gesture(),0,0)
        surface.mouse_move(mouse,80,0);surface.mouse_up(mouse,160,0)
        self.assertEqual([p[:2] for p in surface.ink.strokes[0]['points']],[(20,70),(100,70),(180,70)])
        self.assertIsNone(surface.mouse_start)

    def test_real_cancel_or_focus_loss_stops_further_ink(self):
        for kind in ('mouse','stylus'):
            surface=Surface();gesture=Gesture()
            getattr(surface,kind+'_down')(gesture,20,20)
            getattr(surface,kind+'_cancel')()
            getattr(surface,kind+'_move')(gesture,80,80)
            self.assertIsNone(surface.ink.current)
            self.assertEqual(len(surface.ink.strokes[0]['points']),1)
        surface=Surface();surface.mouse_down(Gesture(),20,20);surface.finish()
        surface.mouse_move(Gesture(),80,80)
        self.assertEqual(len(surface.ink.strokes[0]['points']),1)

    def test_pen_mouse_events_do_not_start_a_second_stroke(self):
        surface=Surface();pen=Gesture(tool=NS(get_tool_type=lambda:Gdk.DeviceToolType.PEN))
        surface.mouse_down(pen,20,20);self.assertFalse(surface.ink.strokes)
        surface.stylus_down(pen,20,20);surface.mouse_down(pen,30,30)
        surface.stylus_move(pen,100,20);surface.stylus_up(pen,180,20)
        self.assertEqual(len(surface.ink.strokes),1)
        self.assertEqual(len(surface.ink.strokes[0]['points']),3)

    def test_mouse_emulation_without_pressure_and_outside_release(self):
        surface=Surface();mouse=Gesture()
        surface.mouse_down(mouse,20,20);surface.mouse_move(mouse,80,0)
        surface.mouse_up(mouse,300,0)
        self.assertEqual([p[2] for p in surface.ink.strokes[0]['points']],[1,1])
        self.assertIsNone(surface.active_input)
        surface.mouse_down(mouse,-20,-20);surface.mouse_move(mouse,100,100)
        self.assertEqual(len(surface.ink.strokes),1)


if __name__=='__main__':unittest.main()
