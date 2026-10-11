# -*- coding: utf-8 -*-
"""qa_tokens.py (selichot_baer) - בדיקת שימור טקסט: השוואת טוקנים עבריים בין ה-HTML המרונדר של ויקיטקסט לפלט הכלי.

המקור לבדיקה הוא ה-HTML כפי שוויקיטקסט מציג (parse_rendered.py שומר html_<דף>.html לכל דף), ולא ה-wikitext - כך שגם טקסט שמגיע
מ-<pages>/תבניות נספר. מורידים הערות/כותרות/מספרי הערה מה-HTML, ומשווים multiset של טוקנים (בלי ניקוד) מול out/<ספר>.txt ו-
out/הערות על <ספר>.txt. תוצאה ל"הסליחות לכל השנה": 11,569 מול 11,572 (חסר 'ששי' אחד; עודף: כותרות שנוספו), הערות 103/103.
מריצים מתוך תיקייה ובה html_*.html ו-out/. שנה את NAME. "חסרים" שהם ארטיפקט (קידומות+קישור, {{נ|תיקון|..}} שמציג רק נוסח מתוקן,
צבעים) הם צפויים - מה שחשוב: אין חסרים גדולים/מילים שלמות.
"""
import re, glob, sys, html
from collections import Counter
from bs4 import BeautifulSoup

HEB = re.compile(r"[֐-׿\"'׳״]+")


def toks(text):
    out = []
    for w in re.split(r"[\s|<>\-־‎‏͏]+", text):
        w = re.sub(r"[^א-תְ-ׇ֑-֯]", "", w)
        if w:
            out.append(w)
    return out


src = Counter()
srcn = Counter()
for f in sorted(glob.glob("html_*.html")):
    h = open(f, encoding="utf-8").read()
    soup = BeautifulSoup(h, "html.parser")
    for t in soup.select(".mw-editsection"):
        t.decompose()
    for t in soup.select("sup.reference"):
        t.decompose()
    refs = soup.select("ol.references")
    for r in refs:
        for li in r.select("li"):
            for bl in li.select(".mw-cite-backlink"):
                bl.decompose()
            srcn.update(toks(li.get_text(" ")))
        r.decompose()
    for hd in soup.select(".mw-heading"):
        hd.decompose()
    src.update(toks(soup.get_text(" ")))

out = Counter()
outn = Counter()
base = open("out/הסליחות לכל השנה - זליגמן בער.txt", encoding="utf-8").read().split("\n")
notes = open("out/הערות על הסליחות לכל השנה - זליגמן בער.txt", encoding="utf-8").read().split("\n")
for l in base[3:]:
    out.update(toks(re.sub(r"<[^>]*>", " ", html.unescape(l))))
for l in notes[1:]:
    outn.update(toks(re.sub(r"<[^>]*>", " ", html.unescape(l))))

def diff(a, b, name):
    miss = a - b
    extra = b - a
    print(name, "src", sum(a.values()), "out", sum(b.values()), "missing", sum(miss.values()), "extra", sum(extra.values()))
    print("  missing:", dict(list(miss.most_common(40))))
    print("  extra:", dict(list(extra.most_common(40))))

diff(src, out, "BASE")
diff(srcn, outn, "NOTES")
