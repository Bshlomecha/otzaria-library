# -*- coding: utf-8 -*-
"""make_inline.py (selichot_baer) - הופך ספר + "הערות על ..." + links לספר עם הערות inline (<sup class="footnote-marker"> + <i class="footnote">).

שימש כש-wikisourceToOtzaria/links היה absent (אין איפה לשים קובץ links), ולכן ההערות הוכנסו inline. כעת (אחרי הקומיט שהחליף את
השורש ל-present) מומלץ ספר נלווה (הערות על X + links) - ראה ADDING_BOOKS.md §2-4 ו"חוזה המיזוג" - ולא inline. הסקריפט נשאר
כדוגמה לפעולה ההפוכה (ואם נדרש לחזור ל-inline). הוא גם מציב את שם המחבר בשורה 2. NAME ו-out/ בתיקיית העבודה.
"""
import re, os, sys
NAME = "הסליחות לכל השנה - זליגמן בער"
base = open(f"out/{NAME}.txt", encoding="utf-8").read().split("\n")
notes = open(f"out/הערות על {NAME}.txt", encoding="utf-8").read().split("\n")
bodies = {}
for ln in notes[1:]:
    m = re.match(r"<sup>(\d+)</sup> (.*)$", ln)
    assert m, ln
    bodies[int(m.group(1))] = m.group(2)
used = set()
out = []
for ln in base:
    def rep(m):
        n = int(m.group(1))
        used.add(n)
        return f'<sup class="footnote-marker">{n}</sup><i class="footnote">{bodies[n]}</i>'
    if ln.startswith("<h"):
        out.append(ln)
        continue
    out.append(re.sub(r"<sup>(\d+)</sup>", rep, ln))
assert used == set(bodies), (used, set(bodies))
out[1] = "זליגמן בער"
os.makedirs("final", exist_ok=True)
with open(f"final/{NAME}.txt", "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out))
print("inline notes:", len(used))
