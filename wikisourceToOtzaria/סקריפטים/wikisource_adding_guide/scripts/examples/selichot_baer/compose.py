# -*- coding: utf-8 -*-
"""compose.py (selichot_baer) - הרכבת טקסט מדפים ש"מורכבים" מעמודי סריקה (<pages> של ProofreadPage). נכתב עבור: הסליחות לכל השנה - זליגמן בער.

הבעיה: דפי הספר "הסליחות לכל השנה - זליגמן בער/סליחות ליום ראשון" ודומיהם אינם מכילים טקסט אלא תבניות/תג <pages> שמושכים
מקטעים (<section begin="..."/> ... <section end="..."/>) מעמודי הסריקה במרחב "עמוד:" (למשל
"עמוד:The Seliḥot for the Entire Year.pdf/16"). הכלי ws_book.py אינו תומך בזה ("תג <pages> ... לא נתמך, הטקסט לא נטען").

הפתרון כאן: (1) מורידים את כל עמודי הסריקה ל-pages.json (fetch_pages.py), (2) compose.py חותך מכל עמוד את הקטע לפי label
(extract_section), מנקה noinclude/includeonly, ומרחיב ידנית את תבניות הסימון הנפוצות (rep_for) ל-HTML/wikitext פשוט,
(3) run_book.py מזריק את הטקסט המורכב ל-ws_book דרך monkey-patch של WikiClient.get_page ומריץ את ws_book.main() כרגיל.

דרישות: pages.json בתיקיית העבודה (או PAGES_JSON), בפורמט {שם עמוד: [contentmodel, content]}. מריצים מתוך תיקייה זו.
הסקריפט עצמו (python compose.py) כותב composed_view.txt - סקירה של הפסקאות שהורכבו, לבדיקה בעין לפני הריצה.
SECTIONS בסוף: (label, עמוד התחלה, עמוד סוף) - התאמה ידנית לכל ספר. לספר אחר יש להחליף PRE ו-SECTIONS ולבדוק את rep_for:
כל תבנית שאינה מטופלת מדפיסה "UNHANDLED TEMPLATE" ל-stderr.
"""
import json, os, re, sys
import mwparserfromhell as mwp

PRE = "עמוד:The Seliḥot for the Entire Year.pdf/"
PAGES = json.load(open(os.environ.get('PAGES_JSON', 'pages.json'), encoding='utf-8'))

def page(n):
    return PAGES[PRE + str(n)][1]

def extract_section(text, label):
    lab = re.escape(label)
    pb = re.compile(r'<section\s+begin\s*=\s*"' + lab + r'"\s*/>')
    pe = re.compile(r'<section\s+end\s*=\s*"' + lab + r'"\s*/>')
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

def apply_inclusion_transcluded(text):
    fl = re.S | re.I
    text = re.sub(r"<noinclude>.*?</noinclude>", "", text, flags=fl)
    return re.sub(r"</?includeonly>", "", text, flags=re.I)

BRK = "\n\n"
def tpl_name(t):
    return re.sub(r'\s+', ' ', str(t.name).strip())

def pos(t):
    return [str(p.value) for p in t.params if not p.showkey]

def named(t, k):
    for p in t.params:
        if str(p.name).strip() == k:
            return str(p.value)
    return None

def rep_for(t):
    if True:
        nm = tpl_name(t)
        ps = pos(t)
        rep = None
        if nm in ('טקסט מנוקד', 'סוף'):
            rep = BRK
        elif nm == 'עם-ניקוד':
            body = named(t, 'טקסט')
            if body is None:
                body = ps[0] if ps else ''
            rep = BRK + body + BRK
        elif nm in ('ק', 'קטן'):
            body = named(t, 'קטן')
            if body is None:
                body = ' '.join(ps)
            rep = f"<small>{body}</small>"
        elif nm == 'הוראה למתפללים':
            rep = f"<small>{ps[0] if ps else ''}</small>"
        elif nm in ('ג', 'גדול'):
            rep = f"<big>{ps[0] if ps else ''}</big>"
        elif nm == 'מרכז':
            rep = BRK + '<div style="text-align: center;">' + (ps[0] if ps else '') + '</div>' + BRK
        elif nm == 'כו':
            rep = BRK + '<div style="text-align: center;"><b>' + (ps[0] if ps else '') + '</b></div>' + BRK
        elif nm == 'הערה':
            body = named(t, '1')
            if body is None:
                body = ps[0] if ps else ''
            rep = f"<ref>{body}</ref>"
        elif nm in ('רווח קשיח', 'ססס', 'ררר'):
            rep = ' '
        elif nm == 'ש':
            rep = '<br>'
        elif nm == 'מ:ירושלם':
            rep = (ps[0] if ps else '') + (ps[1] if len(ps) > 1 else '') + '͏ִ'
        elif nm == 'ממ':
            ps2 = [p.strip() for p in ps]
            if len(ps2) >= 3:
                rep = f"({ps2[0]} {ps2[1]}, {ps2[2]})"
            else:
                rep = "(" + ' '.join(ps2) + ")"
            rep = rep  # plain, no link
        elif nm == '!':
            rep = '|'
        elif nm == 'קיצור':
            rep = ps[0] if ps else ''
        elif nm == 'רן':
            rep = BRK + '<br>'.join(l.strip() for l in (ps[0] if ps else '').strip('\n').split('\n')) + BRK
        else:
            rep = None
        return rep

def expand(code):
    """expand templates in place, innermost first (also inside bold/italic tags)"""
    skipped = set()
    while True:
        cands = []
        for t in code.filter_templates(recursive=True):
            if len(mwp.parse(str(t)).filter_templates(recursive=True)) == 1 and str(t) not in skipped:
                cands.append(t)
        if not cands:
            return
        t = cands[0]
        rep = rep_for(t)
        if rep is None:
            print("UNHANDLED TEMPLATE", tpl_name(t), file=sys.stderr)
            skipped.add(str(t))
            continue
        code.replace(t, rep)

def compose(label, a, b):
    parts = []
    for n in range(a, b + 1):
        raw = page(n)
        sec = extract_section(raw, label)
        if sec is None:
            continue
        sec = apply_inclusion_transcluded(sec)
        sec = re.sub(r'(?m)^:+', '', sec)
        parts.append((n, sec))
    return parts

def norm_paragraphs(txt):
    # normalise: spaces around breaks, single newlines -> space, blank lines -> paragraph break
    txt = txt.replace('\r', '')
    paras = re.split(r'\n\s*\n', txt)
    out = []
    for p in paras:
        p = re.sub(r'[ \t]*\n[ \t]*', ' ', p)
        p = re.sub(r'[ \t]{2,}', ' ', p).strip()
        if p:
            out.append(p)
    return out

def build(label, a, b, heading=None):
    parts = compose(label, a, b)
    big = ' '.join(sec.strip() for n, sec in parts)
    code = mwp.parse(big)
    expand(code)
    return norm_paragraphs(str(code))

if __name__ == '__main__':
    import itertools
    SECTIONS = [("סדר סליחות", 10, 16), ("סליחות ליום ראשון", 16, 30), ("סליחות ליום שני", 30, 36),
                ("סליחות ליום שלישי", 36, 44), ("סליחות ליום רביעי", 44, 50), ("סליחות ליום חמישי", 50, 58),
                ("סליחות ליום שישי", 58, 67)]
    with open('composed_view.txt', 'w', encoding='utf-8') as f:
        for lab, a, b in SECTIONS:
            paras = build(lab, a, b)
            f.write(f"######## {lab} ({a}-{b}) paras={len(paras)}\n")
            for i, p in enumerate(paras):
                f.write(f"[{i}] {p[:160]}{' ...' if len(p)>160 else ''}  <<len {len(p)}>>\n")
