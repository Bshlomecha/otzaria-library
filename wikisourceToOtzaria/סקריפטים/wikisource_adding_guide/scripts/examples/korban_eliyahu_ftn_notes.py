# -*- coding: utf-8 -*-
"""korban_eliyahu_ftn_notes.py - דוגמה: הערות שוליים בפורמט [[דף#ftnN|[N]]] + [[דף#ftnrefN|[N]]] (ולא <ref>). נכתב עבור: קרבן אליהו.

הבעיה: בדפי "קרבן אליהו/..." ההערות אינן <ref>...</ref> אלא קישורי עוגן ידניים:
    בגוף:    ...טקסט[[קרבן אליהו/מילה#ftn3|[3]]]...
    בסוף:    [[קרבן אליהו/מילה#ftnref3|[3]]] טקסט ההערה
(לעתים אחרי "== הערות שוליים ==" ו-"----"). ‏ws_book.py אינו מכיר זאת: הקישורים נראים כטקסט "[3]" והערות נשארות כפסקאות.
הפתרון: לפני ההמרה להפוך כל דף ל-wikitext עם <ref>טקסט ההערה</ref> במקום הסמן, ולהסיר את בלוק ההערות מהסוף (ftn_to_ref). ‏
ws_book מזהה <ref> ומייצר "הערות על קרבן אליהו" + קובץ links כרגיל.

איך ממומש כאן: עוטף את ws_book.convert_page (monkey-patch) - כל דף עובר ftn_to_ref לפני ההמרה; ובדף הראשי (מזוהה לפי השורה
"א. [[קרבן אליהו/..." של רשימת התוכן) מוסרים בנוסף את רשימת הפרקים, שורת {{קיצור|א"ה...}} ואת "== סריקות ==" (מידע שאינו תוכן הספר).
(בעבר השתמשנו בעותק מקומי של ws_book שבו אותו קוד הוכנס לפני ההמרה - התוצאה זהה.)
אזהרות על stderr: MULTILINE-NOTE (הערה בכמה שורות - נאספת), MISSING-NOTE (סמן בלי הערה), MISSING-NOTE-ALL (יש סמנים ואין אף הערה).

הרצה:
    python -X utf8 examples/korban_eliyahu_ftn_notes.py --page "קרבן אליהו" --include-main --author "אליהו הכהן האיתמרי" --out <תיקייה>
(--include-main כי הדף הראשי עצמו מכיל הקדמה/כותר; אחרת הוא מדולג.) הדגל --marker-style/--note-line-style זהים ל-ws_book.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # scripts/
sys.dont_write_bytecode = True
import ws_book as W

NL = "\n"
FTN_REF_RE = re.compile(r"\[\[[^\[\]|]*#\s*ftnref(\d+)\|(?:\'\'\')?\[\d+\](?:\'\'\')?\]\]")
FTN_IN_RE = re.compile(r"\[\[[^\[\]|]*#\s*ftn(\d+)\|(?:\'\'\')?\[\d+\](?:\'\'\')?\]\]")


def ftn_to_ref(text: str) -> str:
    lines = text.split(NL)
    entries = {}
    first = None
    cur = None
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*(?:-{4,})?\s*" + FTN_REF_RE.pattern + r"\s*(.*)$", ln)
        if m:
            if first is None:
                first = i
            cur = int(m.group(1))
            entries[cur] = [m.group(2)]
            continue
        if first is not None and cur is not None and ln.strip() and not ln.strip().startswith("[[קטגוריה:") and not re.match(r"^=+\s*הערות שוליים\s*=+$", ln.strip()):
            entries[cur].append(ln)
            print("MULTILINE-NOTE", cur, len(ln), file=sys.stderr)
    if first is None:
        if FTN_IN_RE.search(text):
            print("MISSING-NOTE-ALL", file=sys.stderr)
        return FTN_IN_RE.sub("", text)
    keep = lines[:first]
    while keep and (not keep[-1].strip() or re.match(r"^=+\s*הערות שוליים\s*=+$", keep[-1].strip()) or re.match(r"^-{4,}$", keep[-1].strip())):
        keep.pop()
    tail = [l for l in lines[first:] if l.strip().startswith("[[קטגוריה:")]
    body = NL.join(keep)

    def rep(m):
        n = int(m.group(1))
        if n not in entries:
            print("MISSING-NOTE", n, file=sys.stderr)
            return ""
        return "<ref>" + " ".join(x.strip() for x in entries[n]) + "</ref>"

    body = FTN_IN_RE.sub(rep, body)
    return body + NL + NL.join(tail)


def main_page_cleanup(t: str) -> str:
    t = re.sub(r"(?m)^א\. \[\[קרבן אליהו/.*$", "", t)  # רשימת הפרקים (התוכן נבנה מהכותרות)
    t = re.sub(r"(?m)^\{\{קיצור\|א\"ה.*$", "", t)
    t = re.sub(r"(?s)== סריקות ==.*?(?=\[\[קטגוריה:)", "", t)
    return t


_orig_convert = W.convert_page


def convert_page(wt, start, note_start):
    is_main = bool(re.search(r"(?m)^א\. \[\[קרבן אליהו/", wt))
    wt = ftn_to_ref(wt)
    if is_main:
        wt = main_page_cleanup(wt)
    return _orig_convert(wt, start, note_start)


W.convert_page = convert_page
sys.exit(W.main())
