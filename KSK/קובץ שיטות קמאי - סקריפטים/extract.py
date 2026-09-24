import json,re,sys,html as H,hashlib
from collections import Counter
from docparse import Doc
import os
for _d in ('txt','html','paras'): os.makedirs(_d,exist_ok=True)
m=json.load(open('manifest.json'))
k=sys.argv[1]
d=Doc(m[k]['path'])
ps=list(d.paragraphs())
def cls(pr):
    b=pr.get('bb',pr.get('b',False)) or pr.get('b',False)
    sz=pr.get('szb',pr.get('sz',24))
    col=pr.get('cv') or (('ico%d'%pr['ico']) if pr.get('ico') else '')
    return f"b{int(bool(b))}-s{sz}"+(f"-c{col}" if col else '')+(f"-f{pr.get('ftcb',pr.get('ftc',''))}")+(f"-sup{pr['iss']}" if pr.get('iss') else '')
with open(f'txt/{k}.txt','w',encoding='utf-8') as ft, open(f'html/{k}.html','w',encoding='utf-8') as fh, open(f'paras/{k}.jsonl','w',encoding='utf-8') as fj:
    fh.write('<html dir="rtl"><meta charset="utf-8"><body>\n')
    for i,p in enumerate(ps):
        ft.write(p['text'].replace('\x0b','\n')+'\n')
        runs=[(t,cls(pr)) for t,pr in p['runs'] if t]
        fh.write(f'<p data-i="{i}" data-style="{H.escape(p["style"] or "")}" data-jc="{p["pap"].get("jc","")}">'+''.join(f'<span class="{c}">{H.escape(t)}</span>' for t,c in runs)+'</p>\n')
        fj.write(json.dumps(dict(i=i,istd=p['istd'],style=p['style'],pap=p['pap'],runs=runs),ensure_ascii=False)+'\n')
    fh.write('</body></html>\n')
print(k,len(ps))
