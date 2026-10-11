# -*- coding: utf-8 -*-
"""chk_pres.py (shlosha_dikduk) - בדיקת שימור טוקנים עבריים בין קובצי wikitext של המקור לקובץ הפלט (עם טיפול ב-{{נ|תיקון|...}}).

שימוש:  python -X utf8 chk_pres.py <קובץ פלט .txt> <מקור1.wiki> [<מקור2.wiki> ...]
מדפיס "missing" (טוקנים מהמקור שלא בפלט) ו-"extra" (בפלט ולא במקור) - הנפוצים. חותך את שורת הזכויות. {{נ|a|b}} מוחלף ב-a
(הכלי מציג רק את הנוסח הראשי, כמו ויקיטקסט), ולכן "חסרים" של הנוסח החלופי הם צפויים. דוגמה לבדיקה מדויקת יותר מ"בדיקת שימור" של
ws_book (שמסירה שמות תבניות ויעדי קישור אך אינה מכירה את {{נ}}).
"""
import re, sys, collections, glob
def reduce_n(s):
    # replace {{נ|a|...}} (non-nested in a) with a
    pat = re.compile(r'\{\{נ\|((?:(?!\{\{|\}\}).)*?)(?:\|(?:(?!\{\{|\}\}).)*?)?\}\}', re.S)
    prev=None
    while prev!=s:
        prev=s
        s=pat.sub(lambda m:m.group(1), s)
    return s
def toks(s):
    s=re.sub(r'[\u0591-\u05C7]','',s)
    return re.findall(r'[\u05D0-\u05EA]+', s)
def src_tokens(wt):
    wt=reduce_n(wt)
    wt=re.sub(r'\{\{(עמוד|בעבודה|ש|קישור חיוג\'|קישור רמבג|חיפוש2)[^{}]*\}\}','',wt)
    wt=re.sub(r'\{\{[^{}|]*\|','',wt)   # template name + pipe
    wt=re.sub(r'\[\[([^\]|]*)\|([^\]]*)\]\]',r'\2',wt)
    wt=re.sub(r'\[\[([^\]]*)\]\]',r'\1',wt)
    wt=re.sub(r'<[^>]+>','',wt)
    return collections.Counter(toks(wt))
srcs=sys.argv[2:]
out=open(sys.argv[1],encoding='utf-8').read()
out=re.sub(r'<p style="color: gray;">.*?</p>','',out)
out=re.sub(r'<[^>]+>',' ',out)
oc=collections.Counter(toks(out))
sc=collections.Counter()
for f in srcs: sc+=src_tokens(open(f,encoding='utf-8').read())
miss=sc-oc; extra=oc-sc
print('missing',sum(miss.values()),dict(list(miss.most_common(40))))
print('extra',sum(extra.values()),dict(list(extra.most_common(40))))
