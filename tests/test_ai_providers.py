import base64
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from tiny2 import integrations,api_keys
from tiny2.ai_providers import cloud_request,cloud_text,HOSTS,ENV_KEYS,MODEL_KEYS
from tiny2.gwen import GwenClient,make_request

PNG=b'\x89PNG\r\n\x1a\nartificial-test-image'
ANSWER=json.dumps({'frame_id':'frame1','answer':'Testantwort','uncertain':False,'markers':[]})


def complete(text=ANSWER):return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}
def gemini(text=ANSWER):return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}]}


class CredentialsCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();integrations.configure(self.temp.name)
        self.env=patch.dict(os.environ,{k:'' for k in [*ENV_KEYS.values(),'GOOGLE_API_KEY']});self.env.start()
    def tearDown(self):
        self.env.stop();integrations.configure(None);api_keys._sessions.clear();self.temp.cleanup()



class Credentials(CredentialsCase):
    def test_session_key_not_written_and_persisted_key_is_owner_only(self):
        api_keys.set_key('openai','session-test-key');self.assertEqual(api_keys.get('openai'),'session-test-key')
        self.assertFalse((Path(self.temp.name)/'api-keys.json').exists())
        api_keys.set_key('xai','saved-test-key',persist=True)
        path=Path(self.temp.name)/'api-keys.json';self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        api_keys._sessions.clear();self.assertEqual(api_keys.get('xai'),'saved-test-key')
        self.assertEqual(api_keys.get('openai'),'')
        api_keys.forget('xai');api_keys._sessions.clear();self.assertEqual(api_keys.get('xai'),'')

    def test_keys_never_go_to_integrations_and_env_is_provider_scoped(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'env-openai','GEMINI_API_KEY':'env-gemini'}):
            self.assertEqual(api_keys.get('openai'),'env-openai');self.assertEqual(api_keys.get('gemini'),'env-gemini')
            self.assertEqual(api_keys.get('xai'),'');self.assertEqual(api_keys.get('local'),'')
            api_keys.forget('openai');self.assertEqual(api_keys.get('openai'),'')
        integrations.save({'provider':'openai','openai_model':'test-model'})
        self.assertNotIn('key',(Path(self.temp.name)/'integrations.json').read_text())
        with self.assertRaises(ValueError):integrations.save({'api_key':'not-allowed'})

    def test_reject_header_injection_and_broad_file_permissions(self):
        for key in ['test\r\nHeader:value','x y','a'*4097]:
            with self.assertRaises(ValueError):api_keys.set_key('openai',key)
        api_keys.set_key('openai','dummy-key',persist=True);api_keys._sessions.clear()
        (Path(self.temp.name)/'api-keys.json').chmod(0o644)
        with self.assertRaisesRegex(ValueError,'0600'):api_keys.get('openai')

    def test_existing_local_settings_upgrade_without_losing_values(self):
        old={'model':'existing-local:7b','port':11436,'whisper_model':'/local/model'}
        path=Path(self.temp.name)/'integrations.json';path.write_text(json.dumps(old))
        result=integrations.load();self.assertEqual(result['model'],old['model']);self.assertEqual(result['port'],11436)
        self.assertEqual(result['provider'],'local');self.assertEqual(result['openai_model'],'')
        with self.assertRaises(ValueError):integrations.save({'provider':'unknown'})
        with self.assertRaises(ValueError):integrations.save({'gemini_model':'foo\nbar'})


class WireFormats(unittest.TestCase):
    def payload(self):return make_request('chosen-model','Wo ist Pin 1?',PNG,'frame1',[
        {'role':'user','content':'old text','images':['must-not-be-sent']},
        {'role':'assistant','content':'old answer'}])

    def test_responses_image_history_and_strict_schema(self):
        for provider in ('openai','xai'):
            path,body=cloud_request(provider,self.payload())
            self.assertEqual(path,'/v1/responses');self.assertFalse(body['store']);self.assertNotIn('tools',body)
            self.assertEqual(body['text']['format']['type'],'json_schema');self.assertTrue(body['text']['format']['strict'])
            self.assertEqual(body['input'][-1]['content'][1]['type'],'input_image')
            self.assertEqual(base64.b64decode(body['input'][-1]['content'][1]['image_url'].split(',')[1]),PNG)
            self.assertNotIn('must-not-be-sent',json.dumps(body));self.assertEqual(cloud_text(provider,complete()),ANSWER)

    def test_gemini_inline_image_roles_and_schema(self):
        path,body=cloud_request('gemini',self.payload())
        self.assertEqual(path,'/v1beta/models/chosen-model:generateContent')
        self.assertEqual(body['contents'][1]['role'],'model')
        self.assertEqual(base64.b64decode(body['contents'][-1]['parts'][1]['inlineData']['data']),PNG)
        self.assertEqual(body['generationConfig']['responseMimeType'],'application/json')
        self.assertIn('responseJsonSchema',body['generationConfig']);self.assertEqual(cloud_text('gemini',gemini()),ANSWER)
        self.assertNotIn('must-not-be-sent',json.dumps(body))

    def test_incomplete_refused_blocked_and_missing_replies_are_not_success(self):
        for value in [{'status':'incomplete','output':[]}, {'status':'completed','output':[]},
                      {'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]}]:
            with self.assertRaises(ValueError):cloud_text('openai',value)
        for value in [{},{'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':ANSWER}]}}]},
                      {'promptFeedback':{'blockReason':'SAFETY'}}]:
            with self.assertRaises(ValueError):cloud_text('gemini',value)
        reply=gemini();reply['candidates'][0]['content']['parts'].insert(0,{'text':'hidden thinking','thought':True})
        self.assertEqual(cloud_text('gemini',reply),ANSWER)

    def test_malformed_response_parts_are_rejected(self):
        for provider,value in [('openai',{'status':'completed','output':[{'type':'message','content':None}]}),('gemini',{'candidates':[{'finishReason':'STOP','content':None}]})]:
            with self.assertRaises(ValueError):cloud_text(provider,value)


class Transport(CredentialsCase):
    def client(self,provider):
        integrations.save({'provider':'local',MODEL_KEYS[provider]:'test-vision'})
        api_keys.set_key(provider,'dummy-'+provider) if provider!='local' else None
        return GwenClient(provider)

    def test_https_hosts_auth_and_schema_roundtrip(self):
        for provider in ('openai','xai','gemini'):
            client=self.client(provider)
            with patch('tiny2.gwen.http.client.HTTPSConnection') as factory,patch('tiny2.gwen.http.client.HTTPConnection') as local:
                connection=factory.return_value;connection.getresponse.return_value.status=200
                connection.getresponse.return_value.read.return_value=json.dumps(gemini() if provider=='gemini' else complete()).encode()
                reply=client.chat('Frage',PNG,'frame1');self.assertEqual(reply['answer'],'Testantwort')
                factory.assert_called_once_with(HOSTS[provider],timeout=10);local.assert_not_called()
                args=connection.request.call_args.args;headers=args[3]
                self.assertNotIn('dummy-',args[1]);self.assertNotIn('dummy-',args[2].decode())
                if provider=='gemini':self.assertEqual(headers['x-goog-api-key'],'dummy-gemini');self.assertNotIn('Authorization',headers)
                else:self.assertEqual(headers['Authorization'],'Bearer dummy-'+provider)
                connection.close.assert_called_once()

    def test_unconfigured_or_cancelled_does_not_connect(self):
        integrations.save({'provider':'openai','openai_model':'test-vision'})
        with patch('tiny2.gwen.http.client.HTTPSConnection') as factory:
            with self.assertRaisesRegex(RuntimeError,'API-Schlüssel'):GwenClient('openai').chat('Frage',PNG,'frame1')
            factory.assert_not_called()
            client=self.client('openai');client.cancel()
            with self.assertRaises(InterruptedError):client.chat('Frage',PNG,'frame1')
            factory.assert_not_called()

    def test_http_errors_redact_response_body_and_never_fallback(self):
        client=self.client('openai')
        with patch('tiny2.gwen.http.client.HTTPSConnection') as factory,patch('tiny2.gwen.http.client.HTTPConnection') as local:
            connection=factory.return_value;connection.getresponse.return_value.status=401
            connection.getresponse.return_value.read.return_value=b'{"error":"reflected-secret"}'
            with self.assertRaises(RuntimeError) as error:client.chat('Frage',PNG,'frame1')
            self.assertIn('401',str(error.exception));self.assertNotIn('reflected',str(error.exception))
            factory.assert_called_once();local.assert_not_called()

    def test_cancel_during_response_closes_connection_and_discards_reply(self):
        client=self.client('xai')
        with patch('tiny2.gwen.http.client.HTTPSConnection') as factory:
            connection=factory.return_value;connection.getresponse.return_value.status=200
            def read(_):client.cancel();return json.dumps(complete()).encode()
            connection.getresponse.return_value.read.side_effect=read
            with self.assertRaises(InterruptedError):client.chat('Frage',PNG,'frame1')
            connection.sock.shutdown.assert_called_once()

    def test_page_corners_supported_for_all_cloud_providers(self):
        corners=[[0,0],[1000,0],[1000,1000],[0,1000]]
        answer=json.dumps({'frame_id':'page1','uncertain':False,'corners':corners})
        for provider in ('openai','xai','gemini'):
            client=self.client(provider)
            with patch.object(client,'request',return_value=gemini(answer) if provider=='gemini' else complete(answer)) as request:
                self.assertEqual(client.page_corners(PNG,'page1'),corners)
                payload=request.call_args.args[1]
                schema=payload['generationConfig']['responseJsonSchema'] if provider=='gemini' else payload['text']['format']['schema']
                self.assertFalse(schema['additionalProperties']);self.assertIn('corners',schema['required'])


if __name__=='__main__':unittest.main()
