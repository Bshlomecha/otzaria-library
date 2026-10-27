#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת "שו"ת ושב הכהן" של ים החכמה משורות דפוס לפסקאות.

בעיית המקור
-----------
הקובץ (נמשך באוקטובר 2026, 40,174 שורות) כבר מתויג (`<h1>`, `<h2>סימן …</h2>`, מילה
ראשונה של כל פסקה ב־`<b>`), אבל שבור לשורות דפוס של כ־50 תווים: פסקה אחת היא עשרות שורות.

מה הסקריפט עושה
---------------
1. שורה 1 = `<h1>` של המקור, שורה 2 ריקה (המקור אינו מציין מחבר), אחריה כל השאר.
2. פסקה חדשה נפתחת בכל שורה שמתחילה ב־`<b>` (כך המקור מסמן תחילת פסקה — גם כשהשורה
   שלפניה נגמרת בלי נקודה), ובכל כותרת `<h…>`. שורות אחרות מחוברות לפסקה ברווח.
3. כותרת שנקטעה בשורה (`<h2>סימן פא` ואחריה `</h2>` לבדה, פעם אחת במקור) מאוחדת לשורה אחת.
4. אין מחיקה ואין תיקון: בדיקת שימור — הטקסט (כולל התגיות) בלי רווחים זהה למקור,
   ובכל שורת פלט התגיות `<b>`/`</b>` מאוזנות.

שימוש
-----
    python3 -X utf8 vesheiv_hakohen_reflow.py SRC.txt OUT.txt
"""
import re, sys

SRC, OUT = sys.argv[1:3]
L = [l.strip() for l in open(SRC, encoding='utf-8').read().split('\n')]
L = [l for l in L if l]
fixed = []
for i, l in enumerate(L):
    if l.startswith('<h') and '</h' not in l:
        fixed.append(l)
        L[i] = l + L[i + 1]
        L[i + 1] = ''
L = [l for l in L if l]
assert L[0].startswith('<h1>'), L[0]

out = [L[0], '']
cur = []


def flush():
    if cur:
        out.append(' '.join(cur))
        cur.clear()


for line in L[1:]:
    if line.startswith(('<b>', '<h', '<small>')):
        flush()
    cur.append(line)
    if line.startswith('<h'):
        flush()
flush()

open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')

strip = lambda s: re.sub(r'\s+', '', s)
assert strip(''.join(L)) == strip(''.join(out)), 'הטקסט השתנה'
bad = [i for i, l in enumerate(out, 1) if l.count('<b>') != l.count('</b>')]
print('כותרות שאוחדו:', fixed)
print(f'{len(L)} שורות → {len(out)}; כותרות h2: {sum(l.startswith("<h2>") for l in out)};',
      f'שורות עם <b> לא מאוזן: {len(bad)}', bad[:10])
