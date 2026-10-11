# -*- coding: utf-8 -*-
"""cmp2.py (tur_bareket) - ניתוח מעמיק על בסיס cmp.py: יישור לפי קבוצות סימנים ("יחידות"), סיווג ההבדלים וספירת טעויות הקלדה.

מיישר יחידות (ידנית, ב-groups: איפה שמספור/גבולות הסימנים שונים בין דיקטה לוויקיטקסט: תנו-תנט, תצ-תצא, תקסט-תקפ, תרז-תריד, תריט-תרכד),
מחשב ratio לכל יחידה, ויחידה עם ratio<0.8 נחשבת "לא מיושרת" ומדווחת בנפרד. לשאר מסווג כל הבדל: typo_variant (הבדל אות; שני הצדדים
נפוצים), typo_wiki_err / typo_dicta_err (הצד השני נפוץ בהרבה - טעות הקלדה), word_variant, wiki_expands (ראשי תיבות שנפתחו), wiki_contracts,
dicta_only/wiki_only. פלט: cmp2_result.json + הדפסת סיכום. תוצאת הריצה ב-2026: על 239 אלף טוקנים, 223,517 זהים (93.5%); ~1.1 שגיאות הקלדה
לאלף בוויקיטקסט, ~0.7 לאלף בדיקטה. היתרון של ויקיטקסט הוא עריכה/פתיחת ראשי תיבות/עיצוב/הערות עורך/טווח, לא איות.
דורש cmp.py באותה תיקייה, וזהות משתני הסביבה (TUR_WORK, OTZARIA_REPO).
"""
import re, glob, os, json, difflib, collections, sys, random
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmp as C
B = C.B
dic = C.dicta_sections()
wiki = {}
for fn in glob.glob(os.path.join(B, "raw", "טור ברקת__*.wiki")):
    n = os.path.basename(fn)[len("טור ברקת__"):-5]
    wiki[n] = C.toks(C.wiki_text(open(fn, encoding="utf-8").read()))
dtok = {n: C.toks(C.clean_dicta(b)) for n, b in dic.items()}
# hakdama in Dicta is inside תכט; add hakdama text of wiki fully (no ==טור ברקת== header)
hk = open(os.path.join(B, "raw", "טור ברקת__הקדמת המחבר.wiki"), encoding="utf-8").read()
wiki["הקדמת המחבר"] = C.toks(C.wiki_text(hk, only_tur=False))
lex = collections.Counter()
for v in dtok.values(): lex.update(v)
for v in wiki.values(): lex.update(v)

groups = [
 ("הקדמה+תכט", ["תכט"], ["הקדמת המחבר", "תכט"]),
 ("תנו-תנט", ["תנו","תנז","תנח","תנט"], ["תנו","תנז","תנח","תנט"]),
 ("תצ-תצא", ["תצ"], ["תצ","תצא"]),
 ("תקסט-תקפ", ["תקסט","תקע","תקעא","תקעב","תקעג","תקעד","תקעט","תקפ"], ["תקסט","תקע","תקעא","תקעב","תקעג","תקעד","תקעה","תקעו","תקעז","תקעח","תקעט","תקפ"]),
 ("תרז-תריד", ["תרז","תרח","תרט","תרי","תריא","תריב","תריג","תריד"], ["תרז","תרח","תרט","תרי","תריא","תריב","תריג","תריד","תרטו","תרטז"]),
 ("תריט-תרכד", ["תריט","תרכ","תרכא","תרכב","תרכד"], ["תריט","תרכ","תרכא","תרכב","תרכג","תרכד"]),
]
grouped = set()
units = []
for g, dn, wn in groups:
    if any(n not in wiki for n in wn): print("missing", g); continue
    units.append((g, sum((dtok[n] for n in dn), []), sum((wiki[n] for n in wn), [])))
    grouped.update(dn)
for n in dtok:
    if n in grouped or n not in wiki: continue
    # skip pointer/misaligned (decided by ratio later)
    units.append((n, dtok[n], wiki[n]))

stats = collections.Counter(); out = []
rows = []
for name, dt, wt in units:
    sm = difflib.SequenceMatcher(None, dt, wt, autojunk=False)
    ratio = sm.ratio()
    rows.append((name, len(dt), len(wt), round(ratio, 4)))
    if ratio < 0.8:  # misaligned: report separately
        continue
    stats["tokens_d"] += len(dt); stats["tokens_w"] += len(wt); stats["units"] += 1
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            stats["equal"] += i2 - i1; continue
        a, b = dt[i1:i2], wt[j1:j2]
        ctx = (" ".join(dt[max(0,i1-3):i1]), " ".join(dt[i2:i2+3]))
        if tag == "replace" and len(a) == len(b):
            for x, y in zip(a, b):
                d = C.lev(x, y)
                if d <= 2:
                    fx, fy = lex[x], lex[y]
                    if fx <= 2 and fy >= 6: k = "typo_dicta_err"
                    elif fy <= 2 and fx >= 6: k = "typo_wiki_err"
                    else: k = "typo_variant"
                else: k = "word_variant"
                stats[k] += 1
                out.append((k, name, ctx[0], x, y, ctx[1]))
        elif tag == "replace":
            if len(a) == 1 and len(b) >= 2: k = "wiki_expands"
            elif len(b) == 1 and len(a) >= 2: k = "wiki_contracts"
            else: k = "replace_other"
            stats[k] += 1
            out.append((k, name, ctx[0], " ".join(a), " ".join(b), ctx[1]))
        elif tag == "delete":
            k = "dicta_only"; stats[k] += 1; stats["dicta_only_tokens"] += len(a)
            out.append((k, name, ctx[0], " ".join(a), "", ctx[1]))
        else:
            k = "wiki_only"; stats[k] += 1; stats["wiki_only_tokens"] += len(b)
            out.append((k, name, ctx[0], "", " ".join(b), ctx[1]))
json.dump(dict(stats=stats, rows=rows, out=out), open(os.path.join(B, "cmp2_result.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(dict(stats))
print("misaligned (<0.8):", [r for r in rows if r[3] < 0.8])
