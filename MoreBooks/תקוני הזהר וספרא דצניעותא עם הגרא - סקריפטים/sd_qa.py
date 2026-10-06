import sys,re,json,html,os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from docxfmt import W,Styles,segments
from lxml import etree
old=open(sys.argv[1]).read().split('\n'); out=sys.argv[2]; dd=sys.argv[3]
T='ספרא דצניעותא עם ביאור הגרא'
new=open(f'{out}/{T}.txt').read().split('\n')
notes=open(f'{out}/הערות על {T}.txt').read().split('\n')
links=json.load(open(f'{out}/{T}_links.json'))
assert len(old)==len(new)
# 1. שימור: בלי הסמנים ובלי רווחים — זהה, חוץ מ"התוהו"
diff=[]
for i,(a,b) in enumerate(zip(old,new)):
    b2=re.sub(r'<sup>\d+</sup>','',b)
    if re.sub(r'\s','',a)!=re.sub(r'\s','',b2): diff.append(i+1)
    if re.sub(r'\s','',a)==re.sub(r'\s','',b2) and a!=b2:
        # שינוי רווחים בלבד — רק סביב סמן
        pass
print('lines changed (non-ws):',diff,[new[i-1][:60] for i in diff])
# שינויי רווחים: כמה שורות, והאם כולם בשורות עם סמן
ws=[i+1 for i,(a,b) in enumerate(zip(old,new)) if a!=re.sub(r'<sup>\d+</sup>','',b) and '<sup>' not in b and i+1 not in diff]
print('ws-only changes in lines without markers:',ws)
# 2. סמנים רציפים
nums=[int(x) for l in new for x in re.findall(r'<sup>(\d+)</sup>',l)]
print('markers',len(nums),'sequential',nums==list(range(1,len(nums)+1)))
# 3. קישורים
assert all(l['Conection Type']=='footnotes' and 'ref_2' not in l for l in links)
lk={l['line_index_2']:l['line_index_1'] for l in links}
bad=[]
for k,l in enumerate(notes[:-1],1):
    if k==1: continue
    if not l.strip() or re.match(r'<h[1-6]>',l):
        if k in lk: bad.append(('linked blank/heading',k))
        continue
    if k not in lk: bad.append(('unlinked',k)); continue
    m=re.match(r'<sup>(\d+)</sup> ',l)
    bl=new[lk[k]-1]
    if not m or f'<sup>{m.group(1)}</sup>' not in bl: bad.append(('marker mismatch',k))
    if '<i' in l: bad.append(('<i>',k))
print('note line 2 empty:',notes[1]=='', 'bad',bad[:10],len(bad))
print('class=footnote in base:',sum('class="footnote' in l for l in new))
# 4. גוף ההערות מול docx (טקסט בלבד)
st=Styles(dd); fx=etree.parse(dd+'/word/footnotes.xml').getroot()
src={}
for f in fx.iter(W+'footnote'):
    if int(f.get(W+'id'))<=1: continue
    src[f.get(W+'id')]=' '.join(''.join(s[1] for s in segments(p,st) if s[0]=='t' and not s[2]['sup']) for p in f.iter(W+'p'))
order=[]
body=etree.parse(dd+'/word/document.xml').getroot().find(W+'body')
for p in body.iter(W+'p'):
    for s in segments(p,st):
        if s[0]=='fn': order.append(s[1])
nl=[l for l in notes if l.startswith('<sup>')]
mism=0
for fid,l in zip(order,nl):
    a=re.sub(r'\s','',html.unescape(re.sub(r'<[^>]+>','',re.sub(r'^<sup>\d+</sup> ','',l))))
    b=re.sub(r'\s','',src[fid]).replace('’',"'").replace('‘',"'")
    if a!=b: mism+=1; print('MISMATCH',fid,a[:60],'|',b[:60])
print('notes compared',len(nl),'mismatch',mism)
