#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת "הגהות רבי העשיל על הסמ"ג" של ים החכמה משורות דפוס לפסקאות.

בעיית המקור
-----------
הקובץ (נמשך באוקטובר 2026, 1,188 שורות) הוא טקסט גולמי בלי תגים: שורה לכל שורת דפוס
(כ־50 תווים), בלי סימון סוף פסקה. בתוכו:
  * שתי כותרות חלק (`הגהות על הסמ"ג עשין`, `הגהות על הסמ"ג לאוין`);
  * שורת כותרת עמוד רצה (`קונטרס הגהות של הגאון רבי העשיל על הסמ״ג`) שנדבקה בתוך
    הטקסט כמה פעמים;
  * ארבע שורות ריקות.
ההגהות עצמן אינן מסומנות בכותרות (רק שתי הראשונות נפתחות ב־`מ״ע`), וכל הגהה נפתחת
באמצע שורת דפוס אחרי `.`/`:`.

מה הסקריפט עושה
---------------
1. שורה 1 = `<h1>הגהות רבי העשיל על הסמ"ג</h1>`, שורה 2 = המחבר, ואחריהן שורת השער
   של המקור (שורה 1 במקור).
2. שתי כותרות החלק → `<h2>`.
3. מוחק שורות ריקות ואת שורת כותרת העמוד הרצה (בכל מקום מלבד שורת השער).
4. מחבר שורות דפוס לפסקה. פסקה חדשה נפתחת (א) אחרי שורה קצרה (<45 תווים — שארית שורה
   בדפוס) שנגמרת ב־`.`/`:`, כמו ב־chazon_ish_nezikin_reflow.py, וגם (ב) באמצע שורה,
   בכל `. שם ` / `: שם ` / `. דף ` — כך נפתחת כמעט כל הגהה, וזה הסימן היחיד לגבולן.
   טעות לכאן היא פיצול הגהה באמצע, ולכאן — שתי הגהות בפסקה אחת; בשני המקרים לא
   נמחקת מילה.
5. בדיקת שימור: הטקסט בלי רווחים זהה למקור בניכוי כותרות העמוד הרצות.

שימוש
-----
    python3 -X utf8 heshil_semag_reflow.py SRC.txt OUT.txt
"""
import re, sys

TITLE = 'הגהות רבי העשיל על הסמ"ג'
AUTHOR = 'יהושע העשיל'
RUNNING = 'קונטרס הגהות של הגאון רבי העשיל על הסמ״ג'
SECTIONS = ('הגהות על הסמ"ג עשין', 'הגהות על הסמ"ג לאוין')
SRC, OUT = sys.argv[1:3]
L = [l.strip() for l in open(SRC, encoding='utf-8').read().split('\n')]
title_page = L[0]
assert title_page.startswith(RUNNING), title_page
body = [l for l in L[1:] if l]
running = [l for l in body if l == RUNNING]
body = [l for l in body if l != RUNNING]

out = [f'<h1>{TITLE}</h1>', AUTHOR, title_page]
cur = []
NEW_GLOSS = re.compile(r'(?<=[.:]) (?=(?:שם|דף) )')


def flush():
    if cur:
        out.extend(NEW_GLOSS.split(' '.join(cur)))
        cur.clear()


for line in body:
    if line in SECTIONS:
        flush()
        out.append(f'<h2>{line}</h2>')
        continue
    if cur and re.search(r'[.:][)\]]?$', cur[-1]) and len(cur[-1]) < 45:
        flush()
    cur.append(line)
flush()

open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')

strip = lambda s: re.sub(r'\s+', '', s)
src = strip(''.join(l for l in L if l != RUNNING))
dst = strip(''.join(re.sub(r'</?h2>', '', l) for l in out[2:]))
if src.replace(strip(title_page), '', 1) != dst.replace(strip(title_page), '', 1):
    sys.exit('שימור טקסט נכשל')
print(f'{len(L)} שורות מקור → {len(out)} שורות; הוסרו {len(running)} כותרות עמוד רצות')
