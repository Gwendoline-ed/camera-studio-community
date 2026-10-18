#!/usr/bin/env python3
"""Build offline HTML from the deliberately small Markdown subset in our guides."""
from html import escape
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def inline(text):
    text=escape(text)
    text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
    return re.sub(r'\[([^\]]+)\]\((guide-[a-z]{2})\.md\)',r'<a href="\2.html">\1</a>',text)


def render(path):
    result=[];paragraph=[];code=[];in_code=False
    def flush():
        if paragraph:result.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph.clear()
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('```'):
            flush()
            if in_code:result.append('<pre><code>'+escape('\n'.join(code))+'</code></pre>');code=[]
            in_code=not in_code;continue
        if in_code:code.append(line);continue
        if not line.strip():flush();continue
        if line.startswith('#'):
            flush();level=len(line)-len(line.lstrip('#'));result.append(f'<h{level}>'+inline(line[level:].strip())+f'</h{level}>')
        else:paragraph.append(line)
    flush()
    if in_code:raise ValueError('Unclosed code fence: '+str(path))
    lang=path.stem[-2:];title=path.read_text().splitlines()[0].lstrip('# ')
    css='body{max-width:56rem;margin:3rem auto;padding:0 1.3rem;font:18px/1.65 system-ui,sans-serif;color:#19263a;background:#f6f8fb}h1,h2{line-height:1.25}h2{margin-top:2.2rem}a{color:#185db5}code{font-size:.87em;overflow-wrap:anywhere}pre{background:#e6edf6;padding:1rem;border-radius:.5rem;white-space:pre-wrap}p{overflow-wrap:anywhere}@media(prefers-color-scheme:dark){body{color:#e8eff9;background:#10151d}a{color:#9bc2ff}pre{background:#1a273b}}'
    return '<!doctype html>\n<html lang="'+lang+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><style>'+css+'</style></head><body><main>'+''.join(result)+'</main></body></html>\n'

if __name__=='__main__':
    for path in sorted((ROOT/'docs').glob('guide-??.md')):path.with_suffix('.html').write_text(render(path),encoding='utf-8')
