"""Image-bound ink strokes. Erasing removes ink, never camera pixels."""
from .i18n import tr as _t
import io
import math
import cairo


class Ink:
    def __init__(self):self.strokes=[];self.redo_strokes=[];self.current=None;self.before=None
    def begin(self,x,y,color,width,pressure=1,erase=False):
        self.end();self.before=list(self.strokes);self.erase=erase;self.radius=width
        if erase:self.erase_at(x,y)
        else:
            if len(self.strokes)>=2000:raise ValueError(_t('Zeichnung ist voll. Bitte speichern oder Striche entfernen.'))
            self.current={'color':tuple(color),'width':width,'points':[(x,y,pressure)]}
            self.strokes.append(self.current)
    def add(self,x,y,pressure=1):
        if self.before is None:return
        if self.erase:self.erase_at(x,y)
        elif self.current and len(self.current['points'])<50000:self.current['points'].append((x,y,pressure))
    def erase_at(self,x,y):
        def hits(stroke):
            radius=self.radius+stroke['width']/2;points=stroke['points']
            if any(math.hypot(x-p[0],y-p[1])<=radius for p in points):return True
            for a,b in zip(points,points[1:]):
                dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
                t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/length)) if length else 0
                if math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)<=radius:return True
            return False
        self.strokes=[s for s in self.strokes if not hits(s)]
    def end(self):
        if self.before is not None:
            if self.strokes!=self.before:self.redo_strokes.clear()
            self.last_before=self.before
            if not hasattr(self,'undo_states'):self.undo_states=[]
            if self.strokes!=self.before:self.undo_states.append(self.before);self.undo_states=self.undo_states[-100:]
        self.current=None;self.before=None
    def undo(self):
        self.end()
        if getattr(self,'undo_states',[]):self.redo_strokes.append(self.strokes);self.strokes=self.undo_states.pop()
    def redo(self):
        self.end()
        if self.redo_strokes:self.undo_states.append(self.strokes);self.strokes=self.redo_strokes.pop()
    def clear(self):
        self.end()
        if self.strokes:
            if not hasattr(self,'undo_states'):self.undo_states=[]
            self.undo_states.append(self.strokes);self.strokes=[];self.redo_strokes=[]
    def draw(self,cr):
        cr.set_line_cap(cairo.LINE_CAP_ROUND);cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for stroke in self.strokes:
            points=stroke['points'];cr.set_source_rgba(*stroke['color'])
            if len(points)==1:
                x,y,p=points[0];cr.arc(x,y,max(.3,stroke['width']*p/2),0,2*math.pi);cr.fill()
            for a,b in zip(points,points[1:]):
                cr.set_line_width(max(.6,stroke['width']*(a[2]+b[2])/2))
                cr.move_to(a[0],a[1]);cr.line_to(b[0],b[1]);cr.stroke()
    def render(self,original):
        surface=cairo.ImageSurface.create_from_png(io.BytesIO(original));cr=cairo.Context(surface);self.draw(cr)
        out=io.BytesIO();surface.write_to_png(out);return out.getvalue()
