# -*- coding: utf-8 -*-
"""convert_demo.py (tur_bareket) - דוגמה לשימוש ב-ws_book כספרייה: המרת קבצי wikitext גולמיים (raw/) ישירות עם convert_page, בלי הורדה.

שימושי לבדיקת "איך ייראה הפלט?" ולמציאת תבניות לא ממופות לפני ריצה מלאה: load_libs(None) טוען את mediawikitootzaria מהריפו,
convert_page(wt, start, note_start) מחזיר PageResult(lines, notes, unmapped, warnings, stats). כאן: סטטיסטיקת שורות/הערות/תגי HTML/תבניות לא
ממופות על כל הדפים ב-raw/, ודגימת פלט לשלושה סימנים. תוצאת 2026 על טור ברקת: תבנית לא ממופה אחת בעיקרה - "גמט דגש" (~266 מופעים) -
לכן צריך --template-map עם {"גמט דגש": "keep_last"}.
שימוש:  python -X utf8 convert_demo.py <WORK>   (WORK מכיל raw/ ; כותב <WORK>/conv_demo.txt)
"""
import collections, glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.dont_write_bytecode = True
import ws_book as w

w.load_libs(None)
B = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
out = open(os.path.join(B, "conv_demo.txt"), "w", encoding="utf-8")
tags = collections.Counter(); nlines = nnotes = 0; unm = collections.Counter(); warn = []
for fn in ["תל", "תלב", "תקכ"]:
    p = os.path.join(B, "raw", "טור ברקת__" + fn + ".wiki")
    if not os.path.exists(p):
        continue
    res = w.convert_page(open(p, encoding="utf-8").read(), 2, 0)
    out.write(f"===== {fn}: lines={len(res.lines)} notes={len(res.notes)} unmapped={dict(res.unmapped)} warn={res.warnings[:3]}\n")
    for l in res.lines[:25]:
        out.write(l[:400] + "\n")
    out.write("-- notes:\n")
    for n in res.notes[:5]:
        out.write(n[:300] + "\n")
for fn in glob.glob(os.path.join(B, "raw", "טור ברקת__*.wiki")):
    nm = os.path.basename(fn)
    try:
        res = w.convert_page(open(fn, encoding="utf-8").read(), 2, 0)
    except Exception as e:
        warn.append((nm, str(e)[:80])); continue
    nlines += len(res.lines); nnotes += len(res.notes); unm.update(res.unmapped)
    for l in res.lines:
        for t in re.findall(r"<(/?[a-z0-9]+)", l):
            tags[t] += 1
out.write(f"\nALL: lines={nlines} notes={nnotes} unmapped={dict(unm)} errors={warn[:5]}\ntags={dict(tags)}\n")
print("done; see", os.path.join(B, "conv_demo.txt"))
