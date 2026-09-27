#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת "חזון איש חושן משפט, נזיקין" של ים החכמה משורות דפוס לפסקאות.

בעיית המקור
-----------
בניגוד לשאר ספרי המאגר, הקובץ הזה (57 אלף שורות) הוא OCR גולמי: כל שורה היא שורת
דפוס (40–60 תווים), למעט "מסכת בבא בתרא" שכבר מחולקת לפסקאות. בחלק הליקוטים יש גם
שרידי עימוד: `── עמוד N ──`, כותרת רצה אחריו ("מסכת ב"מ, ליקוטים סימן כ"), ומילת
קישור (custos) לפניו — המילה הראשונה של העמוד הבא. וכן כותרות שנשברו לשתי שורות
(`<h4>א)` / `</h4>`) וכמה טעויות OCR בכותרות.

מה הסקריפט עושה
---------------
1. מאחה כותרות שנשברו לשתי שורות.
2. מוחק סימני עמוד, כותרות רצות ומילות קישור (אלה בלבד — השוואה למילה הראשונה בעמוד).
3. מחבר שורות דפוס לפסקה. פסקה נסגרת בכותרת, בשורה ריקה, בקו מפריד, או בשורה
   שמסתיימת ב־`.`/`:` והיא קצרה (<42 תווים — שארית שורה בדפוס) או שהבאה אחריה פותחת
   ב־`<b>` (דיבור המתחיל). פסקה לא נסגרת כשתג `<b>`/`<small>` עדיין פתוח.
4. תיקוני OCR בכותרות (עו→טו, כ→ה בין ד ל־ו, "ס י מ ן כא").
5. בדיקת שימור: הטקסט בלי רווחים זהה למקור בניכוי השורות שנמחקו — אחרת יוצא עם שגיאה.

אחריו: `split_inline_headings.py` (כותרת אחת שנדבקה לסוף פסקה בבבא בתרא).

שימוש
-----
    python3 -X utf8 chazon_ish_nezikin_reflow.py SRC.txt OUT.txt
"""
import re,sys,json
def mask(s): return re.sub(r'[֐-׿]+',lambda m:'*'+str(len(m.group()))+'*',s)
SRC,OUT=sys.argv[1],sys.argv[2]; TITLE='חזון איש, חושן משפט נזיקין'; AUTHOR='אברהם ישעיהו קרליץ'
L=open(SRC,encoding='utf-8').read().split('\n')
if L[-1]=='': L=L[:-1]
isH=lambda l: bool(re.match(r'^\s*<h[1-6]',l))
plain=lambda l: re.sub(r'<[^>]+>','',l).strip()
w0=lambda l: re.sub(r'[^א-ת"\']','',(plain(l).split() or [''])[0]).strip('"\'')
report={'split_headings':0,'markers':0,'running_headers':0,'catchwords':0,'catch_unmatched':[]}
# a. split headings
A=[];i=0
while i<len(L):
    l=L[i]; m=re.match(r'^<h([1-6])>([^<]*)$',l.strip())
    if m and i+1<len(L) and L[i+1].strip()==f'</h{m.group(1)}>':
        A.append(f'<h{m.group(1)}>{m.group(2).strip()}</h{m.group(1)}>'); i+=2; report['split_headings']+=1; continue
    A.append(l); i+=1
# b. page artifacts
drop=set()
MK=re.compile(r'^──\s*עמוד\s*\d+\s*──$')
RH=lambda l: (not isH(l) and len(l.strip())<45 and bool(re.search(r"ליקוטים( סימן( [א-ת]+'?)?)?$",l.strip())))
for i,l in enumerate(A):
    if not MK.match(l.strip()): continue
    drop.add(i); report['markers']+=1
    j=i+1
    # misplaced catchword right after marker, then header
    if j+1<len(A) and len(plain(A[j]).split())==1 and RH(A[j+1]):
        drop.add(j); report['catchwords']+=1; j+=1
    if j<len(A) and RH(A[j]):
        drop.add(j); report['running_headers']+=1; j+=1
        if A[j-1].strip()=='ליקוטים' and re.fullmatch(r"סימן [א-ת]+'?",A[j].strip()): drop.add(j); j+=1
    else: report.setdefault('no_header',[]).append((A[i],A[j][:40]))
    # next real text line
    k=j
    while k<len(A) and (isH(A[k]) or not A[k].strip()): k+=1
    p=i-1
    if p>=0 and not isH(A[p]) and len(plain(A[p]).split())<=2 and plain(A[p]) and not re.search(r'[.:]$',plain(A[p])):
        import difflib
        if w0(A[p])==w0(A[k]) or difflib.SequenceMatcher(None,w0(A[p]),w0(A[k])).ratio()>=0.5: drop.add(p); report['catchwords']+=1
        else: report['catch_unmatched'].append((p+1,A[p],A[i+1][:30],plain(A[k])[:25]))
B=[l for i,l in enumerate(A) if i not in drop]
# c. reflow
out=[f'<h1>{TITLE}</h1>',AUTHOR]; sec=None; buf=[]
SEP=lambda l: bool(re.match(r'^\s*-{3,}\s*$',l)) or bool(re.match(r'^\s*-\s.*\s-\s*$',l))
def flush():
    global buf
    if buf:
        s=buf[0]
        for x in buf[1:]:
            s = s+x if re.search(r'\S-$',s) else s+' '+x
        out.append(s); buf=[]
for i,l in enumerate(B[1:],1):
    if l.startswith('<h2'): sec=plain(l)
    if isH(l): flush(); out.append(l.strip()); continue
    if not l.strip(): flush(); continue
    if sec=='מסכת בבא בתרא': flush(); out.append(l.strip()); continue
    if SEP(l): flush(); out.append(l.strip()); continue
    buf.append(l.strip())
    nxt=B[i+1] if i+1<len(B) else ''
    pl=plain(l)
    j=' '.join(buf); openb=any(len(re.findall(f'<{t}\\b',j))!=len(re.findall(f'</{t}>',j)) for t in ('b','small','i'))
    if openb: continue
    if re.search(r'[.:]$',pl) and (len(pl)<42 or nxt.lstrip().startswith('<b>')): flush()
    elif SEP(nxt): flush()
flush()
# d. preservation QA (before the intentional heading fixes)
kept=''.join(''.join(B[1:]).split()); got=''.join(''.join(out[2:]).split())
# heading OCR fixes (by sequence context, not line numbers)
prev4=None
for i,l in enumerate(out):
    if l.startswith('<h3>'):
        if l=='<h3>ס י מ ן כא</h3>': out[i]='<h3>סימן כא</h3>'
        prev4=None
    elif l.startswith('<h4>'):
        if l=='<h4>עו)</h4>' and prev4=='<h4>יד)</h4>': out[i]='<h4>טו)</h4>'
        if l=='<h4>כ</h4>' and prev4=='<h4>ד</h4>': out[i]='<h4>ה</h4>'
        prev4=out[i]
open(OUT,'w',encoding='utf-8').write('\n'.join(out)+'\n')
for x in report.get("no_header",[]): print("  no header:",x)
print(json.dumps({k:(v if not isinstance(v,list) else len(v)) for k,v in report.items()}))
for u in report['catch_unmatched']: print('  unmatched catch?',u)
print('in lines',len(L),'out lines',len(out),'text preserved (minus dropped):',kept==got)
if kept!=got: sys.exit(1)
