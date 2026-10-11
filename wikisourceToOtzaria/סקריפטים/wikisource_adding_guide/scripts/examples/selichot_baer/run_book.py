# -*- coding: utf-8 -*-
"""run_book.py (selichot_baer) - מריץ את ws_book.main() כשטקסט דפי הסליחות מורכב מעמודי הסריקה (compose.py). נכתב עבור: הסליחות לכל השנה.

מה עושה: בונה TEXTS = {"<ספר>/<דף>": wikitext מורכב} (compose.build לכל מקטע + הפיכת סליחה ממוספרת לכותרת ===...=== + דף שער),
כותב composed_texts.json, ואז מחליף את WikiClient.get_page כך שדפים אלה יוחזרו מ-TEXTS (במקום מהרשת), ואת build_plan כך שהשער
יהיה ראשון. את שאר ההרצה עושה ws_book.main() - עם כל הדגלים (--page "הסליחות לכל השנה - זליגמן בער" --out out ...).
המספור: סליחה שהמספר שלה (א, ב, ג...) בתחילת פסקה הופכת לכותרת; counter מוודא מספור רציף (מדלג עד 2).
שים לב: ההרצה כותבת גם "הערות על ..." + links (8 הערות). ראה BLOCKED_BOOKS.md - ב-2026 הספר הוכנס עם הערות inline
(make_inline.py) כי שורש links של wikisource היה absent באותו שלב; כעת השורש present וניתן להחזיר לספר נלווה.
דרישות: pages.json בתיקיית העבודה; הרצה מתוך תיקייה זו.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SC = os.path.dirname(os.path.dirname(HERE))  # scripts/ (שם יושב ws_book.py)
sys.path.insert(0, SC)
sys.path.insert(0, HERE)
import re, json
import ws_book, compose

MAIN = "הסליחות לכל השנה - זליגמן בער"
SECTIONS = [("סדר סליחות", 10, 16, "סדר הסליחות"), ("סליחות ליום ראשון", 16, 30, "סליחות ליום ראשון"),
            ("סליחות ליום שני", 30, 36, "סליחות ליום שני"), ("סליחות ליום שלישי", 36, 44, "סליחות ליום שלישי"),
            ("סליחות ליום רביעי", 44, 50, "סליחות ליום רביעי"), ("סליחות ליום חמישי", 50, 58, "סליחות ליום חמישי"),
            ("סליחות ליום שישי", 58, 67, "סליחות ליום שישי")]
Q3 = "'" * 3
NUM_RE = re.compile(r"^(?:" + Q3 + r"|<big>)*[א-ת]{1,2}(?:" + Q3 + r"|</big>)*(?=\s)")


def heb(n):
    ones = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט']
    tens = ['', 'י', 'כ', 'ל', 'מ', 'נ']
    if n == 15:
        return 'טו'
    if n == 16:
        return 'טז'
    return tens[n // 10] + ones[n % 10]


counter = [0]
FOUND = []


def to_wikitext(label, a, b, name):
    paras = compose.build(label, a, b)
    out = []
    for i, p in enumerate(paras):
        if i == 0 and re.search(r"סליחות ליום", p) and p.startswith('<div style="text-align: center;">'):
            out.append(f"=={name}==")
            continue
        m = NUM_RE.match(p)
        if m:
            num = re.sub(r"<[^>]*>|" + Q3, "", m.group(0)).strip()
            cand = [k for k in (counter[0] + 1, counter[0] + 2) if num == heb(k)]
            if cand:
                counter[0] = cand[0]
                FOUND.append(cand[0])
                out.append(f"==={p}===")
                continue
        out.append(p)
    return "\n\n".join(out)


def title_page():
    raw = compose.page(3)
    raw = compose.apply_inclusion_transcluded(raw)
    raw = re.sub(r"<div align=left>(.*?)</div>", r"\1", raw, flags=re.S)
    # unclosed bold in the source (MediaWiki auto-closes it at end of line)
    pat = r"(\{\{גדול\|\{\{גדול\|)" + Q3 + r"([^'{}]*)(\}\}\}\})"
    raw = re.sub(pat, lambda m: m.group(1) + Q3 + m.group(2) + Q3 + m.group(3), raw)
    code = compose.mwp.parse(raw)
    compose.expand(code)
    s = str(code)
    return "\n\n".join(compose.norm_paragraphs(s))


TEXTS = {}
TEXTS[MAIN + "/שער"] = title_page()
for label, a, b, name in SECTIONS:
    TEXTS[f"{MAIN}/{name}"] = to_wikitext(label, a, b, name)
json.dump(TEXTS, open('composed_texts.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print("numbered selichot found:", len(FOUND), FOUND, file=sys.stderr)

orig_get = ws_book.WikiClient.get_page


def get_page(self, title):
    t = ws_book.norm_title(title)
    if t in TEXTS:
        return ws_book.PageData(t, "ok", text=TEXTS[t])
    return orig_get(self, title)


ws_book.WikiClient.get_page = get_page

orig_plan = ws_book.build_plan


def build_plan(*a, **k):
    items = orig_plan(*a, **k)
    first = [i for i in items if i.title.endswith("/שער")]
    rest = [i for i in items if not i.title.endswith("/שער")]
    return first + rest


ws_book.build_plan = build_plan

if __name__ == "__main__":
    sys.exit(ws_book.main())
