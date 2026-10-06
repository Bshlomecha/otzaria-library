import sys,os,re,html,json,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from docxfmt import *
from lxml import etree
d,out=sys.argv[1],sys.argv[2]; st=Styles(d)
B='תקוני הזהר מסודר על פי הגרא'; C='ביאור הגרא על תקוני הזהר'
base=open(f'{out}/{B}.txt').read().split('\n')[:-1]
comm=open(f'{out}/{C}.txt').read().split('\n')[:-1]
links=json.load(open(f'{out}/{B}_links.json'))
def pl(s): return re.sub(r'\s','',html.unescape(re.sub(r'<[^>]+>','',s)))
# 1. בסיס מול גוף docx
ps=list(etree.parse(d+'/word/document.xml').getroot().find(W+'body').iter(W+'p'))
src=''.join(pl(esc(''.join(s[1] for s in segments(p,st) if s[0]=='t'))) for p in ps[1:])
got=''.join(pl(l) for l in base[2:])
src2=src.replace(pl('תם ונשלם – שבח לאל בורא עולם:'),'',0)
print('base text equal:',src==got, len(src),len(got))
if src!=got:
    import difflib
    sm=difflib.SequenceMatcher(None,src,got,autojunk=False)
    for t,a,b,c,e in sm.get_opcodes():
        if t!='equal': print(t,src[max(0,a-20):a],'[',src[a:b][:80],'→',got[c:e][:80],']')
# 2. ביאור מול הערות
fx=etree.parse(d+'/word/footnotes.xml').getroot()
fnt={f.get(W+'id'):''.join(pl(esc(''.join(s[1] for s in segments(p,st) if s[0]=='t'))) for p in f.iter(W+'p')) for f in fx.iter(W+'footnote') if int(f.get(W+'id'))>1}
order=[s[1] for p in ps for s in segments(p,st) if s[0]=='fn']
srcn=''.join(fnt[i] for i in order)
gotn=''.join(pl(l) for l in comm[2:] if not re.match(r'<h[1-6]>',l))
print('comm text equal:',srcn==gotn,len(srcn),len(gotn))
# 3. קישורים
bad=[l for l in links if not (1<=l['line_index_1']<=len(base) and 1<=l['line_index_2']<=len(comm))]
hd=[l for l in links if re.match(r'<h[1-6]>',base[l['line_index_1']-1]) or re.match(r'<h[1-6]>',comm[l['line_index_2']-1]) or not comm[l['line_index_2']-1].strip()]
lk=set(l['line_index_2'] for l in links)
unl=[k for k,l in enumerate(comm,1) if k>2 and l.strip() and not re.match(r'<h[1-6]>',l) and k not in lk]
print('links',len(links),'out of range',len(bad),'to heading/blank',len(hd),'unlinked comm lines',unl[:5],len(unl))
mono=all(links[i]['line_index_2']<links[i+1]['line_index_2'] for i in range(len(links)-1))
print('comm lines monotonic',mono)
# 4. תמונות ותיבות
print('lines with >1 img', [i+1 for i,l in enumerate(base+comm) if l.count('<img')>1])
# 5. כותרות: ההורה של כל h3
lv=[int(m.group(1)) for l in base for m in [re.match(r'<h([1-6])>',l)] if m]
print('heading levels',collections.Counter(lv), 'skip', any(b-a>1 for a,b in zip(lv,lv[1:])))
# 6. טקסט לבן
print('white runs', sum(1 for p in ps for s in segments(p,st) if s[0]=='t' and (s[2]['color'] or '').upper()=='FFFFFF' and s[1].strip()))
