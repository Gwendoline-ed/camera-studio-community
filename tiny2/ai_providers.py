"""Provider identities and stateless, image-aware request/response conversion."""
from .i18n import tr as _t
from urllib.parse import quote

PROVIDERS=('local','openai','xai','gemini')
LABELS={'local':'Lokal','openai':'ChatGPT','xai':'Grok','gemini':'Gemini'}
HOSTS={'openai':'api.openai.com','xai':'api.x.ai','gemini':'generativelanguage.googleapis.com'}
ENV_KEYS={'openai':'OPENAI_API_KEY','xai':'XAI_API_KEY','gemini':'GEMINI_API_KEY'}
MODEL_KEYS={'local':'model','openai':'openai_model','xai':'xai_model','gemini':'gemini_model'}


def cloud_request(provider,payload):
    """Convert the bounded neutral/Ollama messages; never forward old images."""
    messages=payload['messages'];schema=payload['format'];model=payload['model']
    if provider in ('openai','xai'):
        converted=[]
        for message in messages:
            images=message.get('images',[])
            content=message['content']
            if images:
                content=[{'type':'input_text','text':content}]+[
                    {'type':'input_image','image_url':'data:image/png;base64,'+image} for image in images]
            converted.append({'role':message['role'],'content':content})
        return '/v1/responses',{'model':model,'input':converted,'store':False,'max_output_tokens':4096,
            'text':{'format':{'type':'json_schema','name':'camera_analysis','strict':True,'schema':schema}}}
    if provider=='gemini':
        contents=[]
        for message in messages[1:]:
            parts=[{'text':message['content']}]+[{'inlineData':{'mimeType':'image/png','data':image}} for image in message.get('images',[])]
            contents.append({'role':'model' if message['role']=='assistant' else 'user','parts':parts})
        return '/v1beta/models/'+quote(model,safe='')+':generateContent',{
            'systemInstruction':{'parts':[{'text':messages[0]['content']}]},'contents':contents,
            'generationConfig':{'responseMimeType':'application/json','responseJsonSchema':schema,'maxOutputTokens':4096}}
    raise ValueError(_t('Unbekannter Cloud-Anbieter.'))


def cloud_text(provider,reply):
    if not isinstance(reply,dict):raise ValueError(_t('Ungültige KI-Antwort.'))
    if reply.get('error'):raise RuntimeError(_t('Der KI-Dienst konnte die Anfrage nicht verarbeiten.'))
    if provider in ('openai','xai'):
        if reply.get('status')!='completed':raise ValueError(_t('KI-Antwort unvollständig. Keine Markierungen übernommen.'))
        output=reply.get('output')
        if not isinstance(output,list):raise ValueError(_t('KI-Antwort ohne Text.'))
        texts=[]
        for message in output:
            if not isinstance(message,dict):raise ValueError(_t('Ungültige KI-Antwort.'))
            if message.get('type')!='message':continue
            parts=message.get('content',[])
            if not isinstance(parts,list):raise ValueError(_t('Ungültige KI-Antwort.'))
            for part in parts:
                if not isinstance(part,dict):raise ValueError(_t('Ungültige KI-Antwort.'))
                if part.get('type')=='refusal':raise ValueError(_t('Der KI-Dienst hat diese Bildanfrage abgelehnt.'))
                if part.get('type')=='output_text' and isinstance(part.get('text'),str):texts.append(part['text'])
        text=''.join(texts)
    elif provider=='gemini':
        candidates=reply.get('candidates')
        if not isinstance(candidates,list) or not candidates or not isinstance(candidates[0],dict):
            raise ValueError(_t('Gemini hat keine Bildanalyse geliefert; die Anfrage wurde möglicherweise abgelehnt.'))
        candidate=candidates[0]
        if candidate.get('finishReason')!='STOP':raise ValueError(_t('Gemini-Antwort unvollständig oder abgelehnt. Keine Markierungen übernommen.'))
        content=candidate.get('content')
        if not isinstance(content,dict):raise ValueError(_t('Ungültige Gemini-Antwort.'))
        parts=content.get('parts')
        if not isinstance(parts,list):raise ValueError(_t('Ungültige Gemini-Antwort.'))
        text=''.join(p['text'] for p in parts if isinstance(p,dict) and not p.get('thought') and isinstance(p.get('text'),str))
    else:raise ValueError(_t('Unbekannter Cloud-Anbieter.'))
    if not text or len(text)>32000:raise ValueError(_t('Keine lesbare KI-Antwort bis 32.000 Zeichen erhalten.'))
    return text
