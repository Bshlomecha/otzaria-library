#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""עיצוב מערכת של "שדי חמד כללים" שהגיעה מים החכמה כטקסט גולמי, בלי תגים.

בעיית המקור
-----------
מערכת ע (נמשכה באוקטובר 2026) הגיעה בלי `<h1>`/`<h2>`/`<h3>`: שורה ראשונה
"מערכת ע", וכל כלל פותח שורה ב־`כלל X) `. מספרי הכללים כתובים לפעמים בכינוי
(`ז"ך`, `נו"ן`, `יו"ד`, `ב"ן`, `ז"ן`, `ס'`). שלושה כללים (פז, פט, צ) נדבקו לסוף הפסקה של
קודמם, אחרי `: `.

מה הסקריפט עושה
---------------
1. שורה 1 = `<h1>שדי חמד כללים מערכת X</h1>`, שורה 2 = המחבר, שורה 3 = `<h2>` משורת
   המקור הראשונה — כמו במערכות נ ו־ס.
2. `כלל X) טקסט` (או `[כלל X)] טקסט`, כמו כלל צה במערכת ש) → `<h3>כלל X</h3>` ובשורה הבאה הטקסט. המספר בכותרת מנורמל לאותיות
   רגילות בלי גרשיים (`ז"ך` → `כז`), כמו בשאר המערכות; גוף הכלל לא משתנה.
   `: כלל X) ` באמצע שורה מפוצל לשורה משלו — רק כש־X הוא הכלל הבא ברצף.
3. רווחים בסוף שורה נמחקים.
4. בדיקת שימור: הטקסט בלי רווחים זהה למקור בניכוי `כלל X)` שעבר לכותרות.

שימוש
-----
    python3 -X utf8 shdei_chemed_raw_kelalim.py SRC.txt OUT.txt "שדי חמד כללים מערכת ע"
"""
import re, sys

AUTHOR = 'חיים חזקיהו מדיני'
VAL = dict(zip('אבגדהוזחטיכךלמםנןסעפףצץקרשת',
               [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 20, 30, 40, 40, 50, 50, 60, 70, 80, 80, 90, 90, 100, 200, 300, 400]))
ONES = ' אבגדהוזחט'
TENS = ' יכלמנסעפצ'
SPELLED = {'נון': 50, 'יוד': 10}


def value(token):
    letters = re.sub(r'[^א-ת]', '', token)
    if letters in SPELLED:
        return SPELLED[letters]
    return sum(VAL[c] for c in letters)


def letters(n):
    assert 0 < n < 200, n
    if n >= 100:
        return ('ק' + letters(n - 100)) if n > 100 else 'ק'
    if n in (15, 16):
        return 'ט' + ONES[n - 9]
    return (TENS[n // 10] + ONES[n % 10]).strip()


SRC, OUT, TITLE = sys.argv[1:4]
L = open(SRC, encoding='utf-8').read().split('\n')
while L and not L[-1].strip():
    L.pop()
while L and not L[0].startswith('מערכת'):   # הערת עורך שלפני הכותרת (ק)
    print('שורה שלפני "מערכת" הושמטה:', L.pop(0))
KELAL = re.compile(r'^\[?כלל ([א-ת"\'׳״]+)\)\]? ?')
INLINE = re.compile(r'(?<=[:.]) (?=כלל ([א-ת"\'׳״]+)\) )')

# כלל שנדבק לסוף הפסקה הקודמת: מפצלים רק כשהמספר ממשיך את הרצף
lines, last = [], 0
for line in L[1:]:
    m = KELAL.match(line)
    if m:
        last = value(m.group(1))
    pos = 0
    for im in INLINE.finditer(line):
        if value(im.group(1)) == last + 1:
            lines.append(line[pos:im.start()])
            pos = im.end()
            last += 1
    lines.append(line[pos:])
out = [f'<h1>{TITLE}</h1>', AUTHOR, f'<h2>{L[0].strip()}</h2>']
moved = []
numbers = []
for line in lines:
    line = line.rstrip()
    m = KELAL.match(line)
    if m:
        n = value(m.group(1))
        numbers.append(n)
        out.append(f'<h3>כלל {letters(n)}</h3>')
        moved.append(m.group(0))
        line = line[m.end():]
    if line:
        out.append(line)
open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')

strip = lambda s: re.sub(r'\s+', '', s)
src = strip(''.join(L[1:]))
for marker in moved:
    src = src.replace(strip(marker), '', 1)
dst = strip(''.join(l for l in out[3:] if not l.startswith('<h3>')))
if src != dst:
    sys.exit('שימור טקסט נכשל')
missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
print(f'{len(numbers)} כללים, {len(out)} שורות; חסרים: {" ".join(letters(n) for n in missing) or "-"}')
