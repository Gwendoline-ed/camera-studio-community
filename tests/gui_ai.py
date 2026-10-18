"""GTK provider selection and dispatch with synthetic frames and API replies."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from gui_integration import SyntheticCamera,pump
from gui_gwen_share import capture
from tiny2.app import Studio
from tiny2 import integrations,api_keys
from tiny2.ai_providers import PROVIDERS,LABELS
from gi.repository import Gtk


def children(widget):
    result=[widget];child=widget.get_first_child()
    while child:result+=children(child);child=child.get_next_sibling()
    return result


def main():
    root=Path(sys.argv[1]).resolve();root.mkdir(parents=True,exist_ok=True)
    camera=SyntheticCamera();requests=[]
    def request(client,path,payload,timeout=10):
        requests.append((client.provider,path,payload))
        if path=='/api/show':return {'capabilities':['vision']}
        if client.provider=='local':prompt=payload['messages'][-1]['content']
        elif client.provider in ('openai','xai'):prompt=payload['input'][-1]['content'][0]['text']
        else:prompt=payload['contents'][-1]['parts'][0]['text']
        frame_id=re.search(r'Aktuelle Bild-ID: (\S+)',prompt)[1]
        reply=json.dumps({'frame_id':frame_id,'answer':'Antwort von '+LABELS[client.provider],'uncertain':False,'markers':[{'label':'Testpunkt','x':250,'y':500}]})
        if client.provider=='local':return {'done':True,'message':{'content':reply}}
        if client.provider=='gemini':return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':reply}]}}]}
        return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':reply}]}]}
    with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'XDG_DATA_HOME':str(Path(tmp)/'data')}),\
         patch('tiny2.app.device.connect',return_value=camera),patch('tiny2.gwen.GwenClient.request',autospec=True,side_effect=request):
        integrations.configure(tmp);integrations.save({'model':'test-local','openai_model':'test-openai','xai_model':'test-grok','gemini_model':'test-gemini'})
        for provider in PROVIDERS[1:]:api_keys.set_key(provider,'synthetic-test-key')
        app=Studio(SimpleNamespace(config_dir=tmp,smoke_test=False,screenshot=None,device=None));app.register(None);app.activate(app)
        try:
            pump(lambda:app.controller is not None and not app.busy)
            app.preview.start(None,test=True);pump(lambda:app.frames_seen>3)
            assert any(isinstance(w,Gtk.Button) and w.get_label()=='KI' for w in children(app.window))
            app.open_gwen();chat=app.gwen_window;pump(lambda:chat.get_realized());assert chat.get_title().startswith('KI')
            for index,provider in enumerate(PROVIDERS):
                before=len(requests);chat.ai_picker.dropdown.set_selected(index)
                assert len(requests)==before,'Switching must not send an image'
                assert chat.history==[],'Another provider must not receive prior history'
                chat.entry.set_text('Prüfung '+provider);chat.send()
                assert not chat.ai_picker.get_sensitive()
                pump(lambda:not chat.busy)
                assert chat.history[-1]['content']=='Antwort von '+LABELS[provider]
                assert chat.markers.markers[0]['label']=='Testpunkt'
                sent=requests[-1];assert sent[0]==provider
                if provider=='local':assert len(sent[2]['messages'])==2
                elif provider=='gemini':assert len(sent[2]['contents'])==1
                else:assert len(sent[2]['input'])==2
            chat.ai_picker.dropdown.set_selected(0)
            assert chat.history[0]['content']=='Prüfung local'
            chat.ai_picker.dropdown.set_selected(1)
            assert chat.history[0]['content']=='Prüfung openai'
            chat.clear_chat();chat.ai_picker.dropdown.set_selected(2);chat.ai_picker.dropdown.set_selected(1);assert chat.history==[]
            chat.entry.set_text('Ein Comic-Cover beschreiben …')
            capture(chat,root/'KI-Chat-Fenstertest.png')
            # Changing settings does not contact providers and does not write keys by default.
            before=len(requests);window=integrations.open_settings(app,provider='openai')
            pump(lambda:window.get_realized());capture(window,root/'KI-Einstellungen-Fenstertest.png')
            widgets=children(window)
            key=next(w for w in widgets if isinstance(w,Gtk.PasswordEntry));key.set_text('gui-session-dummy')
            button=next(w for w in widgets if isinstance(w,Gtk.Button) and w.get_label()=='Speichern');button.emit('clicked')
            assert api_keys.get('openai')=='gui-session-dummy'
            assert not (Path(tmp)/'api-keys.json').exists()
            assert len(requests)==before
            app.open_book();book=app.book_window;pump(lambda:book.get_realized())
            assert not book.use_gwen.get_active(),'Opening a book must not enable automatic cloud analysis'
            book.use_gwen.set_active(True);book.ai_picker.dropdown.set_selected(3);assert not book.use_gwen.get_active()
            assert len(requests)==before
            book.close();chat.close()
            print('PASS: KI label; four providers; explicit endpoint dispatch; no requests on selection/settings; isolated histories and clearing; markers; missing automatic cloud book uploads; session-only key entry.')
        finally:
            app.close();app.window.destroy();api_keys._sessions.clear();integrations.configure(None)


if __name__=='__main__':main()
