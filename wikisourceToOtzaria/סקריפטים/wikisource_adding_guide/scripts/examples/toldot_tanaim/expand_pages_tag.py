# -*- coding: utf-8 -*-
"""expand_pages_tag.py (toldot_tanaim) - הרחבת תג <pages index=".." from=N to=M onlysection=".."/> של ProofreadPage לטקסט. טיוטה - נבדקה על מדגם בלבד.

הבעיה: ב"תולדות תנאים ואמוראים" (אהרן היימן) כל אחד מ-2,217 דפי הערכים הוא רק תבנית ניווט + <pages .../> (index = קובץ הסריקה,
from/to = טווח עמודי סריקה, onlysection = שם הקטע בתוך העמודים). הטקסט עצמו יושב בדפי מרחב "עמוד:" ("עמוד:<index>/<n>"), ובכל
אחד מהם הקטעים מסומנים <קטע התחלה=שם/> ... <קטע סוף=שם/>. ‏ws_book.py אינו תומך ב-<pages> ("תג <pages> ... לא נתמך, הטקסט לא נטען").

מה הקוד עושה (בדומה ל-selichot_baer/compose.py שעשה זאת לספר אחר):
  1. לכל <pages ...> קורא את עמודי הסריקה from..to (ע"י הפונקציה get_scan_page(index, n) שמקבלים מבחוץ - cache או רשת);
  2. מסיר מכל עמוד את <noinclude>...</noinclude> (כותרת העמוד, pagequality, כותרת תחתונה) ואת תגי includeonly (כמו transclusion);
  3. אם יש onlysection (או fromsection/tosection) - חותך מכל עמוד את הקטע(ים) לפי label, ומדלג על עמודים שאין בהם את הקטע;
  4. מחבר את העמודים ב-"\n" (אין טיפול בהיפוך מילה שנחתכה בין עמודים - לבדוק בדוגמאות); מחזיר את הטקסט במקום התג.
מגבלות ידועות (לבדוק מול ה-HTML המרונדר, ראה qa_vs_rendered.py): הצמדת מילים בין עמודים, <קטע> עם תחילת/סוף בעמודים שונים (נתמך:
הקטע נאסף מכל עמוד ומחובר), תבניות עמוד ({{עמוד|..}} כבר מוסרת ע"י ws_book), include=/exclude= (לא נתמכים - נרשמים באזהרה).

שימוש עצמאי (בדיקה):
    python -X utf8 expand_pages_tag.py --entries pages.json --scans pagens.json "תולדות תנאים ואמוראים/א/אבא אומנא"
    (קבצי ה-cache: prefetch.py -> pages.json, prefetch2.py -> pagens.json)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.dont_write_bytecode = True

PAGES_RE = re.compile(r"<pages\b([^>]*?)/?>", re.S | re.I)
ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'/>]+))""", re.S)
HOL_WRAPPER_RE = re.compile(r"\{\{\s*חול\s*\|\s*(<pages\b[^>]*?/>)\s*\}\}", re.S | re.I)


def parse_attrs(s: str) -> dict:
    out = {}
    for m in ATTR_RE.finditer(s):
        out[m.group(1).lower()] = next(g for g in m.groups()[1:] if g is not None)
    return out


def extract_section(text: str, label: str):
    lab = re.escape(label.strip())
    pb = re.compile(r'<\s*(?:קטע|section)\s+(?:התחלה|begin)\s*=\s*["\']?\s*' + lab + r'\s*["\']?\s*/?\s*>', re.I)
    pe = re.compile(r'<\s*(?:קטע|section)\s+(?:סוף|end)\s*=\s*["\']?\s*' + lab + r'\s*["\']?\s*/?\s*>', re.I)
    out, pos, found = [], 0, False
    while True:
        mb = pb.search(text, pos)
        if not mb:
            break
        found = True
        me = pe.search(text, mb.end())
        out.append(text[mb.end(): me.start() if me else len(text)])
        pos = me.end() if me else len(text)
    return "".join(out) if found else None


def as_transcluded(text: str) -> str:
    fl = re.S | re.I
    text = re.sub(r"<noinclude>.*?</noinclude>", "", text, flags=fl)
    return re.sub(r"</?includeonly>", "", text, flags=re.I)


def expand_pages(text: str, get_scan_page, warnings: list[str] | None = None) -> str:
    """מחליף כל <pages .../> בטקסט העמודים. get_scan_page(index, n) -> wikitext של 'עמוד:<index>/<n>' או None אם חסר."""
    warnings = warnings if warnings is not None else []
    text = HOL_WRAPPER_RE.sub(r"\1", text)  # {{חול|<pages/>}} -> <pages/>: הטקסט המורחב עלול להכיל = או | שיפרקו פרמטר תבנית

    def one(m):
        a = parse_attrs(m.group(1))
        index = a.get("index")
        if not index or "from" not in a or "to" not in a:
            warnings.append(f"<pages> לא שלם: {m.group(0)[:100]}")
            return ""
        for unsupported in ("include", "exclude", "step"):
            if unsupported in a:
                warnings.append(f"<pages {unsupported}=...> לא נתמך ({index}): {m.group(0)[:100]}")
        lo, hi = int(a["from"]), int(a["to"])
        parts = []
        label = a.get("onlysection")
        for n in range(lo, hi + 1):
            raw = get_scan_page(index, n)
            if raw is None:
                warnings.append(f"עמוד סריקה חסר: {index}/{n}")
                continue
            body = as_transcluded(raw)
            if label is not None:
                sec = extract_section(raw, label)  # הקטע מחולץ מהטקסט הגולמי (תגי הקטע עשויים להיות בתוך noinclude בדפים מסוימים)
                if sec is None:
                    continue
                body = as_transcluded(sec)
            parts.append(body.strip("\n"))
        if not parts:
            warnings.append(f"<pages> שלא החזיר טקסט: {m.group(0)[:100]}")
        return "\n".join(parts)

    return PAGES_RE.sub(one, text)


def cache_getter(scans: dict):
    """get_scan_page מתוך מילון {'עמוד:<index>/<n>': {'text': ...} | None} (פורמט prefetch2.py)."""
    def get(index: str, n: int):
        v = scans.get(f"עמוד:{index}/{n}")
        return v["text"] if v else None
    return get


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entries", default="pages.json", help="cache של דפי הערכים (prefetch.py)")
    ap.add_argument("--scans", default="pagens.json", help="cache של עמודי הסריקה (prefetch2.py)")
    ap.add_argument("titles", nargs="+")
    a = ap.parse_args()
    entries = json.load(open(a.entries, encoding="utf-8"))
    scans = json.load(open(a.scans, encoding="utf-8"))
    get = cache_getter(scans)
    for t in a.titles:
        e = entries.get(t)
        if not e:
            print(f"== {t}: לא ב-cache")
            continue
        warns: list[str] = []
        res = expand_pages(e["text"], get, warns)
        print(f"== {t}\n{res[:1500]}\n-- אזהרות: {warns}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
