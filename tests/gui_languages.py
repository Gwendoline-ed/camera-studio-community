"""Six-language GTK integration with synthetic video; never uses live cameras."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from tiny2 import i18n
lang=sys.argv[1];out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
i18n.configure(None,lang)
from gui_integration import SyntheticCamera,pump
from gui_gwen_share import capture
from tiny2.app import Studio
from tiny2 import integrations
from gi.repository import Gtk


def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from children(child);child=child.get_next_sibling()


with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'XDG_DATA_HOME':tmp+'/data'}),patch('tiny2.app.device.connect',return_value=SyntheticCamera()) as connect:
    app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None));app.register(None);app.activate(app)
    try:
        pump(lambda:app.controller is not None and not app.busy)
        assert not connect.return_value.writes
        assert app.language_dropdown.get_model().get_n_items()==6
        assert app.language_dropdown.get_selected()==i18n.LANGUAGES.index(lang)
        next(w for w in app.actions if w.get_label()==i18n.tr('Oberkörper')).emit('clicked');pump(lambda:not app.busy)
        assert connect.return_value.state['mode']=='Oberkörper'
        assert i18n.tr('Oberkörper') in app.mode_state.get_text()
        app.preview.start(None,test=True);pump(lambda:app.frames_seen>3)
        capture(app.window,out/'main.png')
        app.open_gwen();pump(lambda:app.gwen_window.get_realized());capture(app.gwen_window,out/'ai.png')
        assert app.gwen_window.send_button.get_label()==i18n.tr('Senden')
        app.open_book();pump(lambda:app.book_window.get_realized());capture(app.book_window,out/'book.png')
        assert not app.book_window.use_gwen.get_active()
        assert app.book_window.project.meta()['title']==i18n.tr('Mein Buch')
        app.open_drawing();pump(lambda:app.drawing_windows[-1].get_realized());capture(app.drawing_windows[-1],out/'draw.png')
        settings=integrations.open_settings(app,provider='openai');pump(lambda:settings.get_realized());capture(settings,out/'settings.png');settings.close()
        # Switching the persisted preference must not interrupt or move a running camera.
        before=len(connect.return_value.writes)
        app.language_dropdown.set_selected((i18n.LANGUAGES.index(lang)+1)%6)
        assert i18n.language()==lang
        assert app.preview.pipeline is not None
        assert len(connect.return_value.writes)==before
        assert (Path(tmp)/'language.json').is_file()
        print(json.dumps({'language':lang,'windows':5,'tracking_command':'Oberkörper','restart_preference':True,'camera_access':False}))
    finally:app.close();app.window.destroy()
