import re,json
from pypdf import PdfReader
from pypdf.generic import ContentStream
from fontTools.encodings.StandardEncoding import StandardEncoding
STD={n:i for i,n in enumerate(StandardEncoding) if n!='.notdef'}
STDPUNCT={'parenright':')','parenleft':'(','zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9','quotedbl':'"','comma':',','period':'.','colon':':','semicolon':';','hyphen':'-','bracketleft':'[','bracketright':']','question':'?','asterisk':'*','quoteright':"'",'space':' ','exclam':'!','slash':'/'}
def glyph2char(n):
    if n in STDPUNCT: return STDPUNCT[n]
    mm=re.fullmatch(r'C(\d+)',n)
    code=int(mm.group(1)) if mm else STD.get(n)
    if code is not None and 0xE0<=code<=0xFA:
        return bytes([code]).decode('cp1255')
    return '{'+n+'}'
def fontmap(f):
    enc=f.get('/Encoding'); enc=enc.get_object() if enc is not None else None
    mp={}
    if hasattr(enc,'get') and '/Differences' in enc:
        c=0
        for x in enc['/Differences']:
            if isinstance(x,int) or str(x).lstrip('-').isdigit(): c=int(x)
            else: mp[c]=glyph2char(str(x)[1:]); c+=1
    return mp
def page_lines(reader,pi):
    pg=reader.pages[pi]
    fonts={k:fontmap(v.get_object()) for k,v in pg['/Resources']['/Font'].items()}
    cs=ContentStream(pg.get_contents(),reader)
    cur=None; out=[]; y=None; line=[]
    tm=[1,0,0,1,0,0]; lm=[0,0]
    def emit(s):
        line.append(s)
    for ops,op in cs.operations:
        if op==b'Tf': cur=fonts.get(ops[0],{})
        elif op in (b'Td',b'TD'):
            if float(ops[1])!=0: out.append(''.join(line)); line.clear()
        elif op==b'Tm':
            if y is not None and abs(float(ops[5])-y)>1: out.append(''.join(line)); line.clear()
            y=float(ops[5])
        elif op in (b'T*',b"'",b'"'): out.append(''.join(line)); line.clear()
        if op in (b'Tj',b"'",b'"'):
            s=ops[-1]; b=bytes(s.original_bytes if hasattr(s,'original_bytes') else s)
            emit(''.join(cur.get(c,chr(c)) for c in b))
        elif op==b'TJ':
            for s in ops[0]:
                if isinstance(s,(int,float)) or type(s).__name__ in('FloatObject','NumberObject'):
                    if float(s)<-150: emit(' ')
                    continue
                b=bytes(s.original_bytes if hasattr(s,'original_bytes') else s)
                emit(''.join(cur.get(c,chr(c)) for c in b))
    out.append(''.join(line))
    return out

import pymupdf
def tounicode_inv(f):
    tu=f.get('/ToUnicode'); inv={}
    if not tu: return inv
    data=tu.get_object().get_data().decode('latin1')
    for blk in re.findall(r'beginbfchar(.*?)endbfchar',data,re.S):
        for a,b in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>',blk):
            inv[chr(int(b,16))]=int(a,16)
    for blk in re.findall(r'beginbfrange(.*?)endbfrange',data,re.S):
        for a,b,c in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>',blk):
            for i in range(int(a,16),int(b,16)+1): inv[chr(int(c,16)+i-int(a,16))]=i
    return inv
def page_maps(pg):
    maps={}
    res=pg['/Resources']
    fonts=res.get('/Font',{})
    for k,v in fonts.items():
        f=v.get_object(); bf=str(f.get('/BaseFont'))[1:]
        fm=fontmap(f); inv=tounicode_inv(f)
        mp=maps.setdefault(bf,{}); mp.update({chr(c):v for c,v in fm.items() if c<0x20 and chr(c) not in inv}); mp.update({u:fm.get(c,u) for u,c in inv.items()})
    return maps
def decode(path,pages=None):
    r=PdfReader(path); doc=pymupdf.open(path)
    res=[]
    for pi in (pages if pages is not None else range(len(doc))):
        maps=page_maps(r.pages[pi])
        byname={}
        for bf,mp in maps.items(): byname.setdefault(bf.split('+')[-1],{}).update(mp)
        d=doc[pi].get_text('rawdict')
        chars=[]
        for b in d['blocks']:
            for l in b.get('lines',[]):
                for sp in l['spans']:
                    mp=byname.get(sp['font'].split('+')[-1],{})
                    for ch in sp['chars']:
                        x0,y0,x1,y1=ch['bbox']
                        chars.append((round(ch['origin'][1],1),x0,x1,mp.get(ch['c'],ch['c']),sp['size'],sp['font']))
        chars.sort(key=lambda c:(c[0],-c[2]))
        lines=[];cur=[];cy=None
        for c in chars:
            if cy is None or abs(c[0]-cy)>2:
                if cur: lines.append(cur)
                cur=[c];cy=c[0]
            else: cur.append(c)
        if cur: lines.append(cur)
        segs=[]
        for ln in lines:
            ln.sort(key=lambda c:-c[2])
            cur=[ln[0]]
            for c in ln[1:]:
                if cur[-1][1]-c[2]>max(12,c[4]*1.2):
                    segs.append(cur); cur=[c]
                else: cur.append(c)
            segs.append(cur)
        def mk(sg,col):
            s='';prev=None
            for c in sg:
                if prev is not None and prev[1]-c[2]>c[4]*0.18: s+=' '
                s+=c[3];prev=c
            return dict(col=col,x0=round(min(c[1] for c in sg)),x1=round(max(c[2] for c in sg)),y=sg[0][0],size=max(c[4] for c in sg),fonts=sorted({c[5] for c in sg}),text=s)
        W=doc[pi].rect.width; mid=W/2
        items=[]
        for sg in segs:
            x0=min(c[1] for c in sg); x1=max(c[2] for c in sg)
            col='F' if (x0<mid-15 and x1>mid+15) else ('R' if x0>=mid-15 else 'L')
            items.append(mk(sg,col))
        items.sort(key=lambda d:d['y'])
        out=[];buf={'R':[],'L':[]}
        def flush():
            out.extend(buf['R']);out.extend(buf['L']);buf['R']=[];buf['L']=[]
        for it in items:
            if it['col']=='F': flush(); out.append(it)
            else: buf[it['col']].append(it)
        flush()
        res.append(out)
    return res
