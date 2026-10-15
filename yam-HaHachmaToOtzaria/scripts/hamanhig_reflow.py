#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת "ספר המנהיג" של ים החכמה משורות דפוס לפסקאות וכותרות.

בעיית המקור
-----------
הקובץ (נמשך באוקטובר 2026, 8,228 שורות) הוא OCR גולמי בלי תגים: שורה לכל שורת דפוס
(כ־70–79 תווים). בתוכו:
  * סמני עמוד רצים (`[המנהיג] ב 2`) ושורות רעש של הסריקה (`Digitized by Google` ומילים
    משובשות כמו `Digtize`, `Googte`, וכן שורות של פיסוק או ספרה בלבד);
  * סעיפים ממוספרים בראש שורה (`א) …`, `קנז) …`), ובראש כל חלק שורת כותרת קצרה
    (`הלכות שבת`, `הלכות סוכה`, …) ובסופו `בריך רחמנא דסייען`.

מה הסקריפט עושה
---------------
1. שורה 1 = `<h1>ספר המנהיג</h1>`, שורה 2 = המחבר; שורת השער של המקור (זהה לכותרת) נמחקת.
2. מוחק שורות בלי אות עברית אחת (רעש סריקה), את סמני העמוד הרצים, ואת מילות המעבר
   שבתחתית עמוד הדפוס (המילה הראשונה של העמוד הבא, שה־OCR העתיק לשורה משלה — נמחקת
   רק כשהיא זהה בדיוק למילה שאחרי מעבר העמוד). כל שורה שנמחקה מודפסת.
3. כותרות: `דיני תפלה` ושורות `הלכות …` קצרות (עד 40 תווים) שבאות אחרי סוף פסקה ולפני
   סעיף ממוספר או פסקה חדשה → `<h2>`; `הלכות …` ארוכות יותר או כאלה שהשורה שלפניהן נקטעה
   באמצע משפט הן תחילת פסקה רגילה (למשל `הלכות החג בחג, ואילמלא כן…`).
4. מחבר שורות דפוס לפסקה. פסקה חדשה נפתחת (א) בכל שורה שפותחת בסעיף ממוספר, (ב) אחרי
   שורה קצרה (<62 תווים — שארית שורה בדפוס) שנגמרת ב־`.`/`:`/`)`, ו־(ג) לפני וגם אחרי כותרת.
5. בדיקת שימור: הטקסט בלי רווחים זהה למקור בניכוי השורות שנמחקו והשער.

שימוש
-----
    python3 -X utf8 hamanhig_reflow.py SRC.txt OUT.txt
"""
import re, sys

TITLE = 'ספר המנהיג'
AUTHOR = 'רבי אברהם בן נתן הירחי'
SHORT = 62
SRC, OUT = sys.argv[1:3]
L = [l.strip() for l in open(SRC, encoding='utf-8').read().split('\n')]
assert L[0] == TITLE, L[0]

HEB = re.compile('[א-ת]')
RUNNING = re.compile(r'^\[המנהיג\]')
ITEM = re.compile(r'^\(?[א-ת]{1,4}["\'׳״]?[א-ת]?\) ')
END = re.compile(r'[.:)\]]["\']?\s*$|דסייען$|^תמו הלכות החול$')
SECTION = re.compile(r'^(?:הלכות |דיני תפלה$)')

dropped = []
catchwords = []
body = []
junk = lambda l: not l or not HEB.search(l) or RUNNING.match(l)
for i, l in enumerate(L[1:], 2):
    if junk(l):
        if l:
            dropped.append((i, l))
        continue
    body.append((i, l))

# מילת מעבר (קוסטוס): בתחתית עמוד הדפוס מודפסת המילה הראשונה של העמוד הבא, וה־OCR העתיק
# אותה כשורה של מילה אחת. מוחקים רק מילה כזאת כשיש בינה לבין המילה הבאה מעבר עמוד
# (שורה ריקה או רעש סריקה) והמילה הבאה — אותה מילה בדיוק.
first_word = lambda l: re.sub(r'[^א-ת"\']', '', l.split()[0]) if l.split() else ''
kept = []
for n, (i, l) in enumerate(body):
    nxt_i, nxt = body[n + 1] if n + 1 < len(body) else (0, '')
    if (len(l.split()) == 1 and len(l) <= 12 and nxt_i - i > 1
            and first_word(l) == first_word(nxt) and not SECTION.match(l)):
        catchwords.append((i, l))
        continue
    kept.append(l)
body = kept


def is_heading(idx):
    l = body[idx]
    if not SECTION.match(l) or len(l) > 40:
        return False
    if idx == 0 or not END.search(body[idx - 1]):
        return False
    nxt = body[idx + 1] if idx + 1 < len(body) else ''
    return l == 'דיני תפלה' or bool(ITEM.match(nxt)) or len(l) < 20 and not END.search(l)


out = [f'<h1>{TITLE}</h1>', AUTHOR]
cur = []


def flush():
    if cur:
        out.append(' '.join(cur))
        cur.clear()


for idx, line in enumerate(body):
    if is_heading(idx):
        flush()
        out.append(f'<h2>{line}</h2>')
        continue
    if ITEM.match(line):
        flush()
    cur.append(line)
    if len(line) < SHORT and END.search(line):
        flush()
flush()

open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')

strip = lambda s: re.sub(r'\s+', '', s)
want = strip(''.join(body))
got = strip(''.join(re.sub(r'</?h2>', '', l) for l in out[2:]))
assert want == got, 'הטקסט השתנה'
print(f'{len(L)} שורות → {len(out)}; נמחקו {len(dropped)} שורות רעש/סמני עמוד ו־{len(catchwords)} מילות מעבר;',
      f'כותרות h2: {sum(l.startswith("<h2>") for l in out)}')
for i, l in dropped:
    print('  נמחקה', i, repr(l))
for i, l in catchwords:
    print('  מילת מעבר', i, repr(l))
