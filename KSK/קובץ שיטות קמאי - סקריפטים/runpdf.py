import json,sys
sys.path.insert(0,'.')
from pdfdecode import decode
import os
os.makedirs('pdfdec',exist_ok=True)
m=json.load(open('manifest.json'))
k=sys.argv[1]
res=decode(m[k]['path'])
with open(f'pdfdec/{k}.jsonl','w',encoding='utf-8') as f:
    for i,pg in enumerate(res): f.write(json.dumps(dict(page=i+1,lines=pg),ensure_ascii=False)+'\n')
with open(f'pdfdec/{k}.txt','w',encoding='utf-8') as f:
    for i,pg in enumerate(res): f.write('\n'.join(l['text'] for l in pg)+'\n\f')
print(k,len(res))
