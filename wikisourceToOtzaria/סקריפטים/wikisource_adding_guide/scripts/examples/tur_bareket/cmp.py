# -*- coding: utf-8 -*-
"""cmp.py (tur_bareket) - השוואה טוקן-טוקן בין "טור ברקת" שבוויקיטקסט (raw/טור ברקת__<סימן>.wiki) לבין "מקור חיים - ג (טור ברקת ...)" של דיקטה.

נכתב כדי להחליט אם כדאי להוסיף את טור ברקת מוויקיטקסט כשכבר יש גרסת דיקטה (המשתמש לא סומך על כך ש-OCR של דיקטה גרוע יותר).
שלבים: (1) מניחים בתיקיית העבודה (TUR_WORK, ברירת מחדל: ה-cwd) תיקייה raw/ עם קובץ wikitext לכל סימן (fetch_raw.py),
(2) python cmp.py -> cmp_result.json: לכל סימן ratio (SequenceMatcher על טוקנים מנורמלים: בלי ניקוד/פיסוק), ספירת סוגי הבדלים ודוגמאות.
wiki_text() מסיר הערות/ממ/סרגל ניווט/תבניות ומוציא רק את גוף "==טור ברקת==" (בלי "==שולחן ערוך==" שחוזר על ספר אחר);
clean_dicta() מסיר כותרות הלכות/שו"ע/הערות סוגריים. הנתיב של דיקטה נגזר משורש הריפו (REPO) - ראה BLOCKED_BOOKS.md לתוצאות (93.5% זהות).
משתני סביבה: TUR_WORK (תיקיית עבודה), OTZARIA_REPO (שורש הריפו; ברירת מחדל: מחפש כלפי מעלה).
"""
import re, glob, os, json, difflib, collections, sys
sys.dont_write_bytecode = True


def find_repo():
    env = os.environ.get("OTZARIA_REPO")
    if env:
        return env
    p = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(p, "manual_links_packaging.py")):
            return p
        q = os.path.dirname(p)
        if q == p:
            raise SystemExit("לא נמצא שורש הריפו; הגדר OTZARIA_REPO")
        p = q


B = os.environ.get("TUR_WORK", os.getcwd())
REPO = find_repo()
D = os.path.join(REPO, "DictaToOtzaria", "ערוך", "ספרים", "אוצריא", "הלכה", "שולחן ערוך", "מפרשים", "מקור חיים")
NIKUD = re.compile(r"[\u0591-\u05C7]")
def norm_tok(t):
    t = NIKUD.sub("", t)
    t = re.sub(r"[\"'׳״“”‘’`,.:;!?()\[\]{}<>\-–—־*_/\|…]", "", t)
    return t
def toks(s):
    return [x for x in (norm_tok(w) for w in s.split()) if x]

def dicta_sections():
    out = {}
    for f in sorted(glob.glob(os.path.join(D, "*ברקת*.txt"))):
        txt = open(f, encoding="utf-8").read()
        parts = re.split(r"^<h2>סימן ([^<]+)</h2>\s*$", txt, flags=re.M)
        for i in range(1, len(parts), 2):
            name = parts[i].strip()
            body = parts[i+1]
            out[name] = body
    return out

def clean_dicta(body):
    lines = []
    for ln in body.split("\n"):
        s = ln.strip()
        if not s: continue
        if re.match(r"^(הלכות [^:]{1,30}:|שו\"ע או\"ח סימן [^ ]+|הקדמת המחבר:)$", s): continue
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"^\[[א-ת\"']+\]\s*", "", s)
        s = re.sub(r"\([^)]*\)", " ", s)
        lines.append(s)
    return "\n".join(lines)

def wiki_text(raw, only_tur=True):
    t = raw
    if only_tur:
        m = re.search(r"^==\s*טור ברקת[^=\n]*==\s*$", t, re.M)
        if m: t = t[m.end():]
    t = re.sub(r"\[\[קטגוריה:[^\]]*\]\]", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    # remove {{הערה|...}} nested-aware
    def strip_tpl(t, names):
        while True:
            m = re.search(r"\{\{\s*(?:%s)\s*[|}]" % "|".join(names), t)
            if not m: return t
            i = m.start(); depth = 0; j = i
            while j < len(t):
                if t.startswith("{{", j): depth += 1; j += 2
                elif t.startswith("}}", j):
                    depth -= 1; j += 2
                    if depth == 0: break
                else: j += 1
            t = t[:i] + " " + t[j:]
    t = strip_tpl(t, ["הערה", "ממ", "ממ זהר", "ממז זהר", "ממ הזר", "ממ משנה", 'ממ רמב"ם', "סרגל ניווט", "הפניה לפסוקים"])
    for _ in range(6):
        t = re.sub(r"\{\{\s*ש\s*\}\}", " ", t)
        t = re.sub(r"\{\{[^{}|]*\|([^{}]*)\}\}", lambda m: m.group(1).split("|")[-1] if "=" not in m.group(1).split("|")[-1] else "", t)
    t = re.sub(r"\{\{[^{}]*\}\}", " ", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"^=+[^=\n]*=+\s*$", "", t, flags=re.M)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"^-{3,}\s*$", "", t, flags=re.M)
    t = re.sub(r"\([^)]*\)", " ", t)
    t = t.replace("__TOC__", "")
    return t

def lev(a, b):
    if a == b: return 0
    if abs(len(a)-len(b)) > 3: return 99
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j]+1, cur[j-1]+1, prev[j-1]+(ca != cb)))
        prev = cur
    return prev[-1]

def main():
    dic = dicta_sections()
    res = {}
    samples = collections.defaultdict(list)
    for fn in sorted(glob.glob(os.path.join(B, "raw", "טור ברקת__*.wiki"))):
        name = os.path.basename(fn)[len("טור ברקת__"):-5]
        if name not in dic: continue
        raw = open(fn, encoding="utf-8").read()
        wt = toks(wiki_text(raw)); dt = toks(clean_dicta(dic[name]))
        sm = difflib.SequenceMatcher(None, dt, wt, autojunk=False)
        c = collections.Counter(); wd = collections.Counter()
        ops = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal": continue
            a, b = dt[i1:i2], wt[j1:j2]
            if tag == "replace" and len(a) == len(b):
                kinds = []
                for x, y in zip(a, b):
                    d = lev(x, y)
                    kinds.append("typo1" if d == 1 else "typo2" if d == 2 else "word")
                k = "replace_same_len"
                for x, y, kk in zip(a, b, kinds):
                    c[kk] += 1
                    ops.append((kk, " ".join(dt[max(0,i1-3):i1]), x, y, " ".join(dt[i2:i2+3])))
            elif tag == "replace":
                c["replace_diff_len"] += 1
                ops.append(("replace_diff_len", " ".join(dt[max(0,i1-3):i1]), " ".join(a), " ".join(b), " ".join(dt[i2:i2+3])))
            elif tag == "delete":
                c["dicta_only"] += 1; wd["dicta_only"] += len(a)
                ops.append(("dicta_only", " ".join(dt[max(0,i1-3):i1]), " ".join(a), "", " ".join(dt[i2:i2+3])))
            else:
                c["wiki_only"] += 1; wd["wiki_only"] += len(b)
                ops.append(("wiki_only", " ".join(dt[max(0,i1-3):i1]), "", " ".join(b), " ".join(dt[i2:i2+3])))
        res[name] = dict(n_d=len(dt), n_w=len(wt), ratio=round(sm.ratio(), 4), c=dict(c), wd=dict(wd), ops=ops)
    json.dump(res, open(os.path.join(B, "cmp_result.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return res

if __name__ == "__main__":
    main()
