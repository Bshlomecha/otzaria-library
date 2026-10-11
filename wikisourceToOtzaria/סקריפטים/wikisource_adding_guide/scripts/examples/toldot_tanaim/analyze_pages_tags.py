# -*- coding: utf-8 -*-
"""analyze_pages_tags.py (toldot_tanaim) - סטטיסטיקה על תגי <pages> בדפי הערכים: אילו תכונות, אילו index-ים, טווחי עמודים, ומה יש בדף מלבד התג.

ב-2026: כל 2,217 הערכים הם <pages index from to onlysection/>; 3 קבצי סריקה (חלק I: 1,374 ערכים, עמודים 32-445; חלק II: 369, 2-257;
חלק III: 474, 7-411) - סה"כ כ-690 עמודי סריקה ייחודיים. מריצים בתיקיית העבודה עם pages.json.
"""
import json,re
from collections import Counter
c=json.load(open('pages.json',encoding='utf-8'))
tags=Counter(); idx=Counter(); attrs=Counter(); nopages=[]
mx={}
for k,v in c.items():
    if k.count('/')!=2: continue
    t=v['text']
    ms=re.findall(r"<pages\b[^>]*?/>",t,re.S)
    if not ms: nopages.append(k); continue
    for m in ms:
        for a in re.findall(r"(\w+)\s*=",m): attrs[a]+=1
        i=re.search(r'index="([^"]*)"',m); idx[i.group(1) if i else None]+=1
        f=re.search(r'from=(\d+)',m); to=re.search(r'to=(\d+)',m)
        if i and f and to: mx.setdefault(i.group(1),[]).append((int(f.group(1)),int(to.group(1))))
print(attrs); print(idx); print(len(nopages), nopages[:20])
for i,l in mx.items(): print(i, min(a for a,b in l), max(b for a,b in l), sum(b-a+1 for a,b in l))
# examples of other-kind: non-pages lines in entry pages
ex=Counter()
for k,v in c.items():
    if k.count('/')!=2: continue
    t=re.sub(r"\{\{ספר חול.*?\n\}\}","",v['text'],flags=re.S)
    t=re.sub(r"<pages\b[^>]*?/>","",t,flags=re.S)
    t=re.sub(r"\{\{חול\|\s*\}\}","",t)
    t=t.strip()
    if t: ex[t[:80]]+=1
print(ex.most_common(25))
