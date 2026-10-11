#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_vs_rendered.py - QA שימור טקסט: משווה את הטוקנים העבריים של ה-HTML המרונדר בוויקיטקסט לפלט של ws_book (קובץ הספר + הערות).

למה: "בדיקת השימור" המובנית ב-ws_book משווה מול ה-wikitext (אחרי הסרת שמות תבניות/יעדי קישור) - ולכן אינה רואה טקסט שמגיע מתבניות,
מ-<pages> או מ-transclusion. ההשוואה מול מה שוויקיטקסט *מציג* תופסת זאת. (ההשוואה היחידה שמוכיחה שלא אבד טקסט - ADDING_BOOKS.md סעיף 0.)

שימוש:
    python -X utf8 qa_vs_rendered.py --main "ספר זכרון (ריק\"ם)" --book out/ספר\\ זכרון.txt [--notes "out/הערות על ספר זכרון.txt"] \\
        [--exclude-page שלם] [--delay 1] [--drop-selector ".navbox"] [--show 40]
  --main            כותרת הדף הראשי; הכלי מוריד את HTML של הדף הראשי ושל כל תתי-הדפים (allpages) מלבד --exclude-page
                    (בלי "שלם"/"הכול" - ברירת מחדל מוחרגים אוטומטית, כמו ב-ws_book). אפשר גם --pages "כותרת1" "כותרת2" לרשימה ידנית.
  --include-main-page   לכלול גם את HTML של הדף הראשי (ברירת מחדל: לא - לרוב הוא רק תוכן עניינים)
קריאות: action=parse (כמו parse_rendered.py); חסימה/קוד חריג -> עצירה ללא עקיפה. 429 -> המתנה וניסיון חוזר (הלוגיקה של ws_book.WikiClient).

פרשנות: "חסרים" = טוקנים שבמקור ואינם בפלט; "עודפים" = בפלט ולא במקור (כותרות שהכלי הוסיף וכד'). ארטיפקטים צפויים:
  * {{נ|תיקון|ד"ו=...}} - רק הנוסח המתוקן מוצג; * צבעים/טבלאות; * קידומות+קישור ("ב[[...]]"); * מספרי הערות; * שורת הזכויות (מוסרת מהפלט).
חשוב: אין חסרים של מילים שלמות בכמות (מעבר לכמה עשרות), ואין עודפים משמעותיים. הפרש גדול -> לבדוק לפי המילים הנפוצות שמודפסות.
"""
from __future__ import annotations

import argparse
import html as htmllib
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_book as W  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def toks(text: str) -> list[str]:
    out = []
    for w in re.split(r"[\s|<>\-־‎‏ -⁯͏]+", text):
        w = re.sub(r"[^א-תְ-ׇ֑-֯]", "", w)
        w = re.sub(r"[֑-ׇ]", "", w)  # בלי ניקוד וטעמים
        if w:
            out.append(w)
    return out


def rendered_html(client: "W.WikiClient", title: str) -> str:
    d = client._request({"action": "parse", "page": title, "prop": "text", "format": "json", "formatversion": 2,
                         "disablelimitreport": 1, "redirects": 1}, title)
    if "parse" not in d:
        raise SystemExit(f"אין parse לדף {title}: {str(d)[:200]}")
    return d["parse"]["text"]


def split_html(html: str, drop: list[str]) -> tuple[Counter, Counter]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for sel in [".mw-editsection", "sup.reference", "style", "script", ".noprint", ".mw-empty-elt", *drop]:
        for t in soup.select(sel):
            t.decompose()
    notes = Counter()
    for r in soup.select("ol.references"):
        for li in r.select("li"):
            for bl in li.select(".mw-cite-backlink"):
                bl.decompose()
            notes.update(toks(li.get_text(" ")))
        r.decompose()
    for hd in soup.select(".mw-heading, h1, h2, h3, h4, h5, h6"):
        hd.decompose()
    return Counter(toks(soup.get_text(" "))), notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--main", help="כותרת הדף הראשי (כל תתי-הדפים נכללים)")
    ap.add_argument("--pages", nargs="+", help="רשימת כותרות ידנית (במקום --main)")
    ap.add_argument("--exclude-page", action="append", default=[], help="תת-דף להחרגה (שם יחסי); חוזר")
    ap.add_argument("--include-main-page", action="store_true")
    ap.add_argument("--book", required=True, help="קובץ הספר שהכלי יצר")
    ap.add_argument("--notes", help="קובץ 'הערות על ...' (אם יש)")
    ap.add_argument("--drop-selector", action="append", default=[], help="CSS selector להסרה מה-HTML (חוזר)")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--show", type=int, default=30, help="כמה טוקנים נפוצים להדפיס")
    a = ap.parse_args()
    if not a.main and not a.pages:
        ap.error("נדרש --main או --pages")
    client = W.WikiClient(a.delay)
    titles = list(a.pages or [])
    if a.main:
        main_t = W.norm_title(a.main)
        sub = client.allpages(main_t + "/")
        excl = {W.norm_title(main_t + "/" + e.lstrip("/")) for e in a.exclude_page}
        for s in sub:
            seg = s[len(main_t) + 1:]
            if s in excl or seg in W.FULL_NAMES or seg in W.TOC_NAMES:
                continue
            titles.append(s)
        if a.include_main_page or not sub:
            titles.insert(0, main_t)
    print(f"[{len(titles)} דפים]", file=sys.stderr)
    src, srcn = Counter(), Counter()
    for t in titles:
        try:
            html = rendered_html(client, t)
        except W.Blocked as b:
            print(f"נחסם בנטפרי: {t} ({b.reason}) - עצירה, אין לעקוף", file=sys.stderr)
            return 3
        c, n = split_html(html, a.drop_selector)
        src += c
        srcn += n
    base = Path(a.book).read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n")
    out, outn = Counter(), Counter()
    for ln in base[3:]:
        out.update(toks(re.sub(r"<[^>]*>", " ", htmllib.unescape(ln))))
    if a.notes:
        for ln in Path(a.notes).read_bytes().decode("utf-8").replace("\r\n", "\n").split("\n")[1:]:
            outn.update(toks(re.sub(r"<[^>]*>", " ", htmllib.unescape(ln))))

    def diff(x: Counter, y: Counter, name: str) -> None:
        miss, extra = x - y, y - x
        print(f"{name}: מקור {sum(x.values())} | פלט {sum(y.values())} | חסרים {sum(miss.values())} | עודפים {sum(extra.values())}")
        print("  חסרים:", dict(miss.most_common(a.show)))
        print("  עודפים:", dict(extra.most_common(a.show)))

    diff(src, out, "גוף הספר")
    if a.notes or srcn:
        diff(srcn, outn, "הערות")
    return 0


if __name__ == "__main__":
    sys.exit(main())
