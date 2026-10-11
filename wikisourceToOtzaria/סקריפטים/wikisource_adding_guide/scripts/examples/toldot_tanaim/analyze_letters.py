# -*- coding: utf-8 -*-
"""analyze_letters.py (toldot_tanaim) - ניתוח דפי האותיות: קישורים אדומים (ערך שמופיע בתוכן העניינים של האות אך הדף לא קיים) ודפים לא רשומים.

ws_book מדווח קישורים אדומים רק בדף הראשי, לא בדפי תוכן-עניינים של פרקים/אותיות. כאן, לכל דף אות (תולדות תנאים ואמוראים/<אות>)
נקראים הקישורים [[/ערך/]] ומשווים לדפים הקיימים (pages.json). תוצאה ב-2026: 3,433 קישורים, 1,227 אדומים (36%), 2,217 ערכים קיימים,
11 קיימים שאינם רשומים בתוכן. פלט: an2.txt. אותיות מ, ע, פ ריקות לגמרי; ח,י,ל,נ,ש חלקיות. מריצים בתיקיית העבודה.
"""
import json,re
c=json.load(open('pages.json',encoding='utf-8'))
P="תולדות תנאים ואמוראים/"
letters=[k for k in c if k.count('/')==1 and len(k.split('/')[1])==1]
exist=set(c)
tot_red=0; tot_links=0; notin=0
out=[]
for L in sorted(letters):
    t=c[L]['text']
    links=[]
    for m in re.finditer(r"\[\[\s*(/[^\]|]*?)/?\s*(?:\|[^\]]*)?\]\]",t):
        links.append(L+m.group(1).rstrip('/'))
    links=list(dict.fromkeys(links))
    red=[l for l in links if l not in exist]
    ent=[k for k in c if k.startswith(L+'/')]
    notlisted=[k for k in ent if k not in links]
    tot_red+=len(red); tot_links+=len(links); notin+=len(notlisted)
    out.append(f"{L[-1]}: links={len(links)} entries={len(ent)} red={len(red)} notlisted={len(notlisted)}")
    for r in red: out.append("   RED "+r)
    for r in notlisted: out.append("   NOTLISTED "+r)
out.append(f"TOTAL links={tot_links} red={tot_red} notlisted={notin} entries={sum(1 for k in c if k.count('/')==2)}")
open('an2.txt','w',encoding='utf-8').write("\n".join(out))
# 'ו' page and sample entry
print(open('an2.txt',encoding='utf-8').read()[-400:])
