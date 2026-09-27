import json,os,re,sys,collections
from common import SRC, mask
from build import SPEC, SUFFIX, FOLDER, NOTE_RE, HEAD_RE, split_heading
out=sys.argv[1]
src={}
for x in os.listdir(SRC):
    if len(x)>9: src['A' if x.endswith('ראשון.txt') else 'B']=open(os.path.join(SRC,x),encoding='utf-8').read()[:-1].split('\n')
bad=collections.Counter(); ok=0; notes_total=0
srcnotes={k:sum(len(NOTE_RE.findall(l)) for l in v) for k,v in src.items()}
for vol,specs in SPEC.items():
    fol=os.path.join(out,FOLDER[vol])
    for title,sub,segs,extra in specs:
        bt=title+SUFFIX
        base=open(os.path.join(fol,bt+'.txt'),encoding='utf-8').read()[:-1].split('\n')
        origin=json.load(open(os.path.join(fol,'.'+bt+'.origin.json'),encoding='utf-8'))['origin']
        assert len(origin)==len(base)
        lk=os.path.join(out,'links',bt+'_links.json')
        recs=json.load(open(lk,encoding='utf-8')) if os.path.exists(lk) else []
        comps={}
        per=collections.defaultdict(list)
        for r in recs:
            p=r['path_2']
            if p not in comps: comps[p]=open(os.path.join(fol,p),encoding='utf-8').read()[:-1].split('\n')
            per[r['line_index_1']].append(comps[p][r['line_index_2']-1])
        # every companion line linked or heading/h1/blank
        for p,cl in comps.items():
            linked={r['line_index_2'] for r in recs if r['path_2']==p}
            for j,l in enumerate(cl):
                if j+1 not in linked and l.strip() and not re.match(r'<h\d',l): bad['unlinked comp line']+=1
                if j+1 in linked and ('<i>' in l or '<i ' in l): bad['i in note']+=1
        ren=extra.get('renumber_heb')
        for i,(l,n) in enumerate(zip(base,origin)):
            if n is None: continue
            s=src[vol][n-1]
            hm=HEAD_RE.match(s)
            if hm:
                t,_=split_heading(0,hm.group(2))
                if re.sub(r'<h\d>|</h\d>','',l)!=t: bad['heading']+=1
                continue
            # rebuild: replace k-th bare sup with k-th note from links, in order of markers
            ns=per.get(i+1,[])
            # order notes by position of their marker in line: links sorted by path then line; reorder by matching markers sequentially
            pool=list(ns); rebuilt=''; pos=0
            sups=list(re.finditer(r'<sup>([^<]+)</sup>',l))
            srcn=NOTE_RE.findall(s)
            if len(sups)!=len(srcn): bad['count']+=1; continue
            recon=l
            good=True
            for m,(smk,sbody) in zip(sups,srcn):
                cand=[x for x in pool if x.startswith('<sup>%s</sup> '%m.group(1)) and x.split('</sup> ',1)[1]==sbody]
                if not cand: good=False; break
                pool.remove(cand[0])
                if not (ren and ren[0]<=n<=ren[1]) and m.group(1)!=smk: good=False;break
            if pool: good=False
            # the text outside notes identical
            if NOTE_RE.sub('#',s)!=re.sub(r'<sup>[^<]+</sup>','#',l): good=False
            if good: ok+=1; notes_total+=len(srcn)
            else: bad['line mismatch']+=1
print('lines ok',ok,'notes carried',notes_total,'source notes',srcnotes,'issues',dict(bad))
