#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ws_book.py (גרסת מכלול) - הורדת ספר מוויקיטקסט העברי והמרתו לקובצי ספר אוצריא.

ws_book_michlol.py - גרסה מורחבת של ws_book.py שנכתבה עבור "ספר מכלול (רד"ק)". (דוגמה; ראה TOOLS.md)

ההבדלים מ-ws_book.py (כל השאר זהה):
  1. צבע גופן: התבנית {{צבע גופן|ירוק|טקסט}} / {{צבע גופן|ערמון|...}} -> <span style="color:green|Maroon;">.
  2. רשת עמידה יותר ל-HTTP 429: 8 ניסיונות (במקום 3) עם המתנה של 8*ניסיון שניות (במקום 3*).
  3. תיקוני טעויות הקלדה מקומיות במקור (michlol_fix.py) - מוחלים על כל דף שנטען (נספרים בדוח).
  4. הדגל --order-page: דף (תבנית ניווט) שהקישורים בו קובעים את סדר הדפים (כשהדף הראשי אינו מכיל את התוכן).
  5. norm_start ב-convert_page: נרמול רמות הכותרת בתוך דף לפי עומק הדף בעץ (כשלדפים יש כותרות פנימיות משלהם
     ברמה שונה מהצפוי) - ראה את הקריאה ל-process_body_html.
בדוגמה זו הוא הורץ עם --template-map tmap.json (שמוציא את התבנית "עוגן בשורה"). הספר: ספר מכלול (רד"ק) +
"הערות על ספר מכלול" (207 הערות; 61 מהן "א"א" = נימוקי רבי אליהו בחור). ה"לפי דפים" (דפי ליק) לא נכללה (שכפול של אותו טקסט).

--- התיעוד המקורי של ws_book.py ---

שימוש:
    python -X utf8 ws_book.py --page "<כותרת הדף הראשי>" --out <תיקיית פלט> [--name <שם הספר>] [--author "..."]

פלט (בתיקיית --out):
    <שם קובץ>.txt                    ספר הבסיס
    הערות על <שם קובץ>.txt           (אם יש הערות שוליים)
    links/<שם קובץ>_links.json       (אם יש הערות) קישורי footnotes
    _report/<שם קובץ>.report.txt|json  דוח: תבניות לא ממופות, דפים שנכשלו/נחסמו/ריקים/אדומים,
                                     שאריות, חוזה המיזוג, תוצאת הוולידטורים

כלל נטפרי: דף שנחסם (תגובת חסימה / קוד שגיאה חריג / תגובה שאינה JSON / הפניה מחוץ לאתר / SSL)
נרשם כ"נחסם בנטפרי: <דף>", הכלי לא מנסה שום דרך חלופית, ואינו משתמש בתוכן מדף חסום.
ספר שיש בו דף חסום מסומן "נחסם" ולא נכתב (אלא עם --allow-partial, ואז בשם ...PARTIAL_BLOCKED).

מה הכלי עושה: מאתר תתי-דפים (allpages), קובע סדר לפי הקישורים בדף הראשי/בדפי הפרקים (לא לפי א"ב),
מרחיב מקומית {{#קטע:..}} ו-{{:..}} (ספרים שתתי-הדפים שלהם מצטטים את דף "/שלם"), ממיר עם הקוד הקיים
(mediawikitootzaria) + תיקונים בצד הכלי, ושומר הערות ל"הערות על X" עם קישורי footnotes.
אין שינוי בריפו; --lib-dir/OTZARIA_WS_LIB מצביעים על wikisourceToOtzaria/סקריפטים. בלי אלה הכלי מחפש את
התיקייה הזו כלפי מעלה מהמיקום שלו ומה-cwd (ראה default_lib_candidates), כך שכשהכלי יושב בערכה שבתוך הריפו -
אין צורך בשום דגל. הדרישות: Python 3.12+ וחבילות mwparserfromhell wikitextparser gematriapy wikiexpand
beautifulsoup4 requests (ראה TOOLS.md בערכה).

מה לבדוק ידנית בכל ספר: ראה "== תוכנית הדפים ==", "תבניות לא ממופות", "שאריות סימון", "בדיקת שימור"
ו"אזהרות" בדוח. תבנית לא ממופה מוחלפת בפרמטר האחרון שלה - להוסיף מיפוי ב--template-map.
אל תשתמש ב--include-main כשהדף הראשי כולל בעצמו את תתי-הדפים (תקבל כפילות).

קודי יציאה: 0 תקין | 1 הספר נכתב אך הוולידטור מצא שגיאות | 2 שימוש שגוי | 3 נחסם |
            4 כשל בדפים (רשת/המרה) | 5 לא נמצא / אין תוכן
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

sys.dont_write_bytecode = True  # לא להשאיר __pycache__ בתוך הריפו
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API = "https://he.wikisource.org/w/api.php"
SITE_HOST = "he.wikisource.org"
USER_AGENT = "OtzariaLibraryBot/1.0 (https://github.com/Otzaria/otzaria-library)"
LIB_MARKER = Path("mediawikitootzaria") / "templates.py"


def default_lib_candidates() -> list[Path]:
    """ברירות מחדל בלתי-תלויות-מכונה לתיקיית wikisourceToOtzaria/סקריפטים (זו שמכילה mediawikitootzaria).

    מחפש כלפי מעלה מהמיקום של הקובץ הזה ומהתיקייה הנוכחית (cwd): בכל אב-קדמון בודק אם הוא עצמו
    התיקייה הזו, או אם מתחתיו wikisourceToOtzaria/סקריפטים. הערכה יושבת בתוך התיקייה הזו בריפו
    (wikisourceToOtzaria/סקריפטים/wikisource_adding_guide/scripts), ולכן בדרך כלל זה נמצא מיד.
    """
    out: list[Path] = []
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for anc in [start, *start.parents]:
            out.append(anc)
            out.append(anc / "wikisourceToOtzaria" / "סקריפטים")
    return out

COPYRIGHT_TMPL = (
    '<p style="color: gray;"><small><small>באדיבות "וויקי-טקסט", נלקח מהדף: '
    '<a href="https://he.wikisource.org/wiki/{enc}">כאן</a>, בשימוש בהתאם לרישיון CC BY-SA 3.0. '
    'בוצעו שינויים בעיבוד, להתאמה לאוצריא.</small></small></p>'
)

# שמות תתי-דפים שאינם פרקים (דף "הכול" / תוכן עניינים) - מדולגים אלא אם ביקשו אחרת
FULL_NAMES = {"שלם", "הכול", "הכל", "הכל בדף אחד", "כל הספר", "כל הספר בדף אחד", "הכל כדף אחד"}
TOC_NAMES = {"תוכן", "תוכן עניינים", "תוכן העניינים", "ניווט"}

# תווי שימוש-פרטי כמחזיקי מקום (לא מופיעים בטקסט עברי רגיל)
PH_PLUS = "\ue0f0"
PH_UNDER = "\ue0f1"
PH_GERSH2 = "\ue0f2"
PH_EMPTY = "\ue0fe"
PH_HR = chr(0xe0f4)
REF_OPEN, REF_CLOSE = "\ue010", "\ue011"
NOWIKI_OPEN, NOWIKI_CLOSE = "\ue020", "\ue021"
MARK_OPEN, MARK_CLOSE = "\ue030", "\ue031"

HEB_RE = re.compile(r"[\u05d0-\u05ea]+")
SECTION_TAG_RE = re.compile(r"<\s*(?:קטע|section)\s[^>]*>", re.I)
HEADING_LINE_RE = re.compile(r"^\s*<h([1-6])\b")
HEADING_FULL_RE = re.compile(r"^<h([1-6])>(.*)</h\1>$", re.S)

# ---------------------------------------------------------------------------
# טעינת הקוד הקיים של ויקיטקסט→אוצריא (הריפו לא משתנה)
# ---------------------------------------------------------------------------
htmltootzaria = mediawikitohtml = templates = tfuncs = None  # type: ignore
mwp = None
BeautifulSoup = None


def load_libs(lib_dir: str | None) -> Path:
    global htmltootzaria, mediawikitohtml, templates, tfuncs, mwp, BeautifulSoup
    cands = [lib_dir, os.environ.get("OTZARIA_WS_LIB"), *default_lib_candidates()]
    chosen = None
    for c in cands:
        if c and (Path(c) / LIB_MARKER).exists():
            chosen = Path(c).resolve()
            break
    if chosen is None:
        raise SystemExit("לא נמצאה חבילת mediawikitootzaria; השתמש ב---lib-dir או במשתנה OTZARIA_WS_LIB "
                         "(הנתיב: <שורש הריפו>/wikisourceToOtzaria/סקריפטים)")
    sys.path.insert(0, str(chosen))
    from mediawikitootzaria import htmltootzaria as _h, mediawikitohtml as _m, template_funcs as _tf, templates as _t
    import mwparserfromhell as _mwp
    from bs4 import BeautifulSoup as _bs
    htmltootzaria, mediawikitohtml, templates, tfuncs, mwp, BeautifulSoup = _h, _m, _t, _tf, _mwp, _bs
    templates.replacement_dict = dict(templates.wikisource_replacement_dict)
    install_overrides()
    return chosen


def _smart_paren(inner: str) -> str:
    s = inner.strip()
    return s if (s.startswith("(") and s.endswith(")")) else f"({s})"


def install_overrides():
    """תיקונים קטנים מעל המיפוי הקיים (הקוד בריפו לא משתנה)."""
    pos = tfuncs.positional
    rd = templates.replacement_dict
    rd["ק"] = lambda t: _smart_paren(pos(t)[0]) if pos(t) else ""
    rd["קטן"] = lambda t: _smart_paren(" ".join(pos(t)))
    rd['עין משפט טוש"ע'] = lambda t: _smart_paren(" ".join(pos(t)))
    rd["ממ"] = lambda t: _smart_paren(pos(t)[0]) if pos(t) and pos(t)[0].strip() else ""
    rd["רווח קשיח"] = lambda t: " "

    # צבע גופן: שמירת הצבע (כמו ב-ספר_השרשים.py שבריפו); ספר מכלול משתמש בירוק ובערמון
    _colors = {"ירוק": "green", "ערמון": "Maroon"}

    def color_font(t):
        p = pos(t)
        if len(p) < 2:
            return " ".join(p[1:])
        c = _colors.get(p[0].strip())
        return f'<span style="color:{c};">{p[1]}</span>' if c else p[1]
    rd["צבע גופן"] = color_font

    def align(t):
        p = pos(t)
        if not p:
            return ""
        how = {"שמאל": "left", "ימין": "right", "מרכז": "center", "left": "left", "right": "right", "center": "center"}.get(p[0].strip())
        body = " ".join(p[1:]) if how else " ".join(p)
        return f'<div style="text-align: {how};">{body}</div>' if how else body
    rd["יישור טקסט"] = align
    rd["ממורכז"] = lambda t: '<div style="text-align: center;">' + " ".join(pos(t)) + "</div>"


# ---------------------------------------------------------------------------
# רשת: לקוח עם זיהוי חסימת נטפרי
# ---------------------------------------------------------------------------
class Blocked(Exception):
    def __init__(self, what: str, reason: str):
        super().__init__(f"{what}: {reason}")
        self.what, self.reason = what, reason


class FetchError(Exception):
    pass


@dataclass
class PageData:
    title: str
    status: str  # ok | missing | empty | blocked | failed | mismatch
    text: str = ""
    redirect_to: str | None = None
    note: str = ""
    resolved: str | None = None
    errors: list[str] = field(default_factory=list)


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from michlol_fix import michlol_fix, FIX_LOG


class WikiClient:
    def __init__(self, delay: float = 0.25):
        import requests
        self.requests = requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        self.delay = delay
        self.cache: dict[str, PageData] = {}
        self.requests_made = 0

    def _request(self, params: dict, what: str) -> dict:
        rq = self.requests
        last = ""
        for attempt in range(1, 9):
            time.sleep(self.delay)
            self.requests_made += 1
            try:
                r = self.s.get(API, params=params, timeout=45, allow_redirects=True)
            except rq.exceptions.SSLError as e:
                raise Blocked(what, f"שגיאת SSL ({type(e).__name__})")
            except (rq.exceptions.ConnectionError, rq.exceptions.Timeout) as e:
                last = f"{type(e).__name__}"
                time.sleep(2 * attempt)
                continue
            hosts = [urllib.parse.urlparse(h.url).hostname for h in r.history] + [urllib.parse.urlparse(r.url).hostname]
            if any(h != SITE_HOST for h in hosts):
                raise Blocked(what, f"הפניה מחוץ לאתר ({hosts[-1]})")
            hdr = " ".join(f"{k}:{v}" for k, v in r.headers.items()).lower()
            if "netfree" in hdr or "x-netfree" in hdr:
                raise Blocked(what, "כותרות תגובה של נטפרי")
            if r.status_code == 429 or 500 <= r.status_code < 600:
                last = f"HTTP {r.status_code}"
                time.sleep(8 * attempt)
                continue
            if r.status_code != 200:
                raise Blocked(what, f"קוד שגיאה חריג HTTP {r.status_code}")
            ctype = r.headers.get("content-type", "")
            if "json" not in ctype:
                raise Blocked(what, f"תגובה שאינה JSON ({ctype or 'ללא סוג'})")
            try:
                data = r.json()
            except ValueError:
                raise Blocked(what, "גוף תגובה שאינו JSON תקין")
            if not isinstance(data, dict):
                raise Blocked(what, "מבנה תגובה בלתי צפוי")
            if "error" in data:
                code = (data["error"] or {}).get("code", "")
                if code in ("ratelimited", "maxlag", "internal_api_error_DBQueryError"):
                    last = f"API {code}"
                    time.sleep(3 * attempt)
                    continue
                raise FetchError(f"שגיאת API: {code}")
            return data
        raise FetchError(f"כשל רשת אחרי 3 ניסיונות ({last})")

    # -- רשימת דפים --
    def allpages(self, prefix: str, redirects_only: bool = False) -> list[str]:
        out: list[str] = []
        cont = None
        while True:
            params = {"action": "query", "list": "allpages", "apprefix": prefix, "apnamespace": 0,
                      "aplimit": "max", "apfilterredir": "redirects" if redirects_only else "nonredirects",
                      "format": "json", "formatversion": 2}
            if cont:
                params["apcontinue"] = cont
            d = self._request(params, f"רשימת דפים {prefix}")
            out += [p["title"] for p in d.get("query", {}).get("allpages", [])]
            cont = d.get("continue", {}).get("apcontinue")
            if not cont:
                return out

    def categories(self, title: str) -> list[str]:
        d = self._request({"action": "query", "prop": "categories", "titles": title, "cllimit": "max",
                           "format": "json", "formatversion": 2}, f"קטגוריות {title}")
        pages = d.get("query", {}).get("pages", [])
        return [c["title"].split(":", 1)[-1] for p in pages for c in p.get("categories", [])]

    def redirect_target(self, title: str) -> str | None:
        d = self._request({"action": "query", "titles": title, "redirects": 1, "format": "json",
                           "formatversion": 2}, f"הפניה {title}")
        rd = d.get("query", {}).get("redirects", [])
        return rd[0]["to"] if rd else None

    # -- תוכן דף --
    def get_page(self, title: str) -> PageData:
        title = norm_title(title)
        if title in self.cache:
            return self.cache[title]
        params = {"action": "query", "prop": "revisions", "titles": title, "rvslots": "main",
                  "rvprop": "content|size", "redirects": 1, "format": "json", "formatversion": 2}
        try:
            d = self._request(params, title)
        except Blocked as b:
            pd = PageData(title, "blocked", note=b.reason)
        except FetchError as e:
            pd = PageData(title, "failed", note=str(e))
        else:
            q = d.get("query", {})
            pages = q.get("pages", [])
            rd = q.get("redirects", [])
            rto = rd[0]["to"] if rd else None
            if not pages:
                pd = PageData(title, "failed", note="תגובה בלי pages")
            else:
                p = pages[0]
                if p.get("missing") or p.get("invalid") or "revisions" not in p:
                    pd = PageData(title, "missing", redirect_to=rto)
                else:
                    rv = p["revisions"][0]
                    text = rv.get("slots", {}).get("main", {}).get("content", "")
                    size = rv.get("size")
                    if size is not None and len(text.encode("utf-8")) != size:
                        pd = PageData(title, "mismatch", note=f"גודל שהתקבל {len(text.encode('utf-8'))} שונה מהגודל המוצהר {size} (קטיעה?)")
                    elif not text.strip():
                        pd = PageData(title, "empty", redirect_to=rto)
                    else:
                        pd = PageData(title, "ok", text=michlol_fix(text.replace("\r\n", "\n")), redirect_to=rto)
        self.cache[title] = pd
        return pd


def norm_title(t: str) -> str:
    t = t.replace("_", " ").replace("\u200e", "").replace("\u200f", "")
    return re.sub(r"\s+", " ", t).strip()


def abs_title(target: str, ctx: str) -> str:
    target = target.strip()
    if target.startswith(":"):
        target = target[1:]
    if target.startswith("../"):
        parent = ctx.rsplit("/", 1)[0] if "/" in ctx else ctx
        target = parent + "/" + target[3:]
    elif target.startswith("/"):
        target = ctx + target.rstrip("/")
    return norm_title(target.rstrip("/"))


# ---------------------------------------------------------------------------
# הרחבת transclusion מקומית: {{#קטע:דף|תווית}} ו-{{:דף}}
# ---------------------------------------------------------------------------
def extract_section(text: str, label: str) -> str | None:
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


def apply_inclusion(text: str, transcluded: bool) -> str:
    fl = re.S | re.I
    if transcluded:
        only = re.findall(r"<onlyinclude>(.*?)</onlyinclude>", text, fl)
        if only:
            text = "".join(only)
        text = re.sub(r"<noinclude>.*?</noinclude>", "", text, flags=fl)
        return re.sub(r"</?includeonly>", "", text, flags=re.I)
    text = re.sub(r"<includeonly>.*?</includeonly>", "", text, flags=fl)
    return re.sub(r"</?(?:noinclude|onlyinclude)>", "", text, flags=re.I)


def resolve_text(client: WikiClient, title: str, text: str, errors: list[str], stack: tuple = ()) -> str:
    """מרחיב transclusion. כשל בהרחבה נרשם ב-errors והתבנית נשארת (תיתפס כשארית). חסימה מועברת הלאה."""
    if "{{" not in text or len(stack) > 6:
        return text
    parsed = mwp.parse(text)
    for tpl in parsed.filter_templates(recursive=False):
        name = str(tpl.name).strip()
        m = re.match(r"#(?:קטע|section|lst)\s*:(.*)$", name, re.I | re.S)
        label = None
        if m:
            target = abs_title(m.group(1) or title, title)
            label = str(tpl.params[0].value).strip() if tpl.params else ""
        elif name.startswith(":") or (name.startswith("/") and len(name) > 1):
            target = abs_title(name, title)
        else:
            continue
        if target == title or target in stack:
            errors.append(f"transclusion מעגלי: {target}")
            continue
        pd = client.get_page(target)
        if pd.status == "blocked":
            raise Blocked(target, pd.note)
        if pd.status != "ok":
            errors.append(f"יעד transclusion {pd.status}: {target}")
            continue
        body = pd.text
        if label is not None:
            sec = extract_section(body, label)
            if sec is None:
                errors.append(f"תווית '{label}' לא נמצאה ב-{target}")
                continue
            body = sec
        body = apply_inclusion(body, True)
        body = resolve_text(client, target, body, errors, stack + (title,))
        try:
            parsed.replace(tpl, body)
        except ValueError:
            errors.append(f"החלפת transclusion נכשלה: {name}")
    return str(parsed)


def extract_links(text: str, ctx: str) -> list[str]:
    out = []
    for wl in mwp.parse(text).filter_wikilinks():
        t = str(wl.title).strip()
        if not t or t.startswith("#"):
            continue
        t = t.split("#")[0]
        if not t:
            continue
        out.append(abs_title(t, ctx))
    return out


# ---------------------------------------------------------------------------
# עזרים: שמות, גימטריה, ספירת מילים
# ---------------------------------------------------------------------------
NIQQUD_RE = re.compile(r"[\u0591-\u05c7]")
ILLEGAL_RE = re.compile(r'[\\/:*"\u05f4?<>|]')


def sanitize_filename(name: str) -> str:
    """זהה ל-validate_book.sanitize_filename (ולפונקציה של ספריא)."""
    s = NIQQUD_RE.sub("", name)
    s = ILLEGAL_RE.sub("", s)
    return s.replace("_", " ").replace("''", "").replace("'", "").strip()


def default_book_name(title: str) -> str:
    return re.sub(r"\s*\([^()]*\)\s*$", "", title).strip() or title


GEM = {c: v for c, v in zip("אבגדהוזחטיכלמנסעפצקרשת",
                            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400])}
GEM.update({"ך": 20, "ם": 40, "ן": 50, "ף": 80, "ץ": 90})


def natural_key(seg: str):
    parts = seg.split()
    out = []
    for p in parts:
        q = re.sub(r"[\"'׳״]", "", p)
        if q.isdigit():
            out.append((1, int(q), ""))
        elif q and all(c in GEM for c in q) and len(q) <= 4:
            out.append((1, sum(GEM[c] for c in q), ""))
        else:
            out.append((0, 0, p))
    return out


def count_words(wikitext: str) -> int:
    t = re.sub(r"<!--.*?-->", "", wikitext, flags=re.S)
    t = SECTION_TAG_RE.sub("", t)
    for _ in range(6):
        n = re.sub(r"\{\{[^{}]*\}\}", "", t)
        if n == t:
            break
        t = n
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)
    return len(HEB_RE.findall(t))


# ---------------------------------------------------------------------------
# טבלאות ויקי -> HTML בשורה אחת
# ---------------------------------------------------------------------------
def _split_top(s: str, seps: tuple[str, ...]) -> list[str]:
    """מפצל לפי מפרידים ברמה העליונה (לא בתוך {{ }} / [[ ]])."""
    parts, cur, depth, i = [], "", 0, 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur += two
            i += 2
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            cur += two
            i += 2
            continue
        hit = next((sp for sp in seps if depth == 0 and s.startswith(sp, i)), None)
        if hit:
            parts.append(cur)
            cur = ""
            i += len(hit)
            continue
        cur += s[i]
        i += 1
    parts.append(cur)
    return parts


def _first_pipe(s: str) -> int:
    depth, i = 0, 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            i += 2
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            i += 2
            continue
        if s[i] == "|" and depth == 0:
            return i
        i += 1
    return -1


def _span_attrs(attrs: str) -> str:
    out = ""
    for k in ("colspan", "rowspan"):
        m = re.search(k + r'\s*=\s*"?(\d+)"?', attrs, re.I)
        if m and int(m.group(1)) > 1:
            out += f' {k}="{m.group(1)}"'
    return out


def convert_tables(text: str, stats: Counter) -> str:
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("{|"):
            depth, j = 0, i
            while j < len(lines):
                s = lines[j].strip()
                if s.startswith("{|"):
                    depth += 1
                if s.startswith("|}"):
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            block = lines[i:j + 1]
            out.append("")
            out.append(_table_html(block, stats))
            out.append("")
            i = j + 1
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def _cell_html(content: str, stats: Counter) -> str:
    content = content.strip()
    if "{|" in content:
        content = convert_tables(content, stats)
    content = re.sub(r"\n\s*\n+", "<br>", content.strip())
    content = content.replace("\n", " ")
    return content if content.strip() else PH_EMPTY


def _table_html(block: list[str], stats: Counter) -> str:
    stats["tables"] += 1
    head_attrs = block[0].strip()[2:]
    rows: list[list[tuple[str, str, str]]] = []  # (tag, attrs, content)
    caption = ""
    cur_row: list[list] | None = None
    depth = 0
    for raw in block[1:-1] if block[-1].strip().startswith("|}") else block[1:]:
        s = raw.strip()
        if depth > 0 or s.startswith("{|"):
            depth += s.startswith("{|") - s.startswith("|}")
            if cur_row:
                cur_row[-1][2] += "\n" + raw
            continue
        if s.startswith("|+"):
            caption = s[2:].strip()
        elif s.startswith("|-"):
            cur_row = None
        elif s.startswith("|") or s.startswith("!"):
            tag = "th" if s.startswith("!") else "td"
            seps = ("||", "!!") if tag == "th" else ("||",)
            if cur_row is None:
                cur_row = []
                rows.append(cur_row)
            for part in _split_top(s[1:], seps):
                k = _first_pipe(part)
                attrs, content = ("", part) if k < 0 else (part[:k], part[k + 1:])
                if k >= 0 and ("[[" in attrs or "{{" in attrs):
                    attrs, content = "", part
                cur_row.append([tag, attrs, content])
        elif cur_row:
            cur_row[-1][2] += "\n" + raw
    bm = re.search(r"border\s*=\s*[\"']?(\d+)", head_attrs, re.I)
    border = ' border="1"' if (re.search(r"wikitable", head_attrs, re.I) or (bm and int(bm.group(1)) > 0)) else ""
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<{t}{_span_attrs(a)}>{_cell_html(c, stats)}</{t}>" for t, a, c in r) + "</tr>"
    cap = f"<caption>{caption}</caption>" if caption else ""
    return f"<table{border}>{cap}{body}</table>"


# ---------------------------------------------------------------------------
# עיבוד מקדים של wikitext
# ---------------------------------------------------------------------------
MAGIC_HE_RE = re.compile(r"__[א-ת_]{3,30}__")  # __ללא_עריכה__ וכד'
MAGIC_RE = re.compile(r"__(?:NOTOC|TOC|FORCETOC|NOEDITSECTION|NOGALLERY|NOCONTENTCONVERT|NOTITLECONVERT|HIDDENCAT|INDEX|NOINDEX|NEWSECTIONLINK|NONEWSECTIONLINK|NOCC)__")
FILE_NS = ("file:", "image:", "קובץ:", "תמונה:", "מדיה:", "media:")
CAT_NS = ("category:", "קטגוריה:")
REF_RE = re.compile(r"<ref\b([^>]*?)(?:/>|>(.*?)</ref\s*>)", re.S | re.I)
HEADING_WIKI_RE = re.compile(r"^(=+)(.*?)(=+)[ \t]*$")


class PageCtx:
    def __init__(self):
        self.refs: list[str] = []
        self.named_refs: dict[str, str] = {}
        self.nowiki: list[str] = []
        self.stats: Counter = Counter()
        self.warnings: list[str] = []


def strip_file_and_category_links(text: str, ctx: PageCtx) -> str:
    if "[[" not in text:
        return text
    parsed = mwp.parse(text)
    for wl in parsed.filter_wikilinks():
        t = str(wl.title).strip().lower().lstrip(":")
        kind = "files" if t.startswith(FILE_NS) else ("cats" if t.startswith(CAT_NS) else None)
        if kind:
            try:
                parsed.remove(wl)
                ctx.stats["תמונות/קבצים שהוסרו" if kind == "files" else "קטגוריות שהוסרו"] += 1
            except ValueError:
                pass
    return str(parsed)


def wiki_headings_to_html(text: str, start: int) -> str:
    out = []
    for line in text.split("\n"):
        m = HEADING_WIKI_RE.match(line.strip()) if line.lstrip().startswith("=") else None
        if m:
            la, inner, lc = len(m.group(1)), m.group(2), len(m.group(3))
            lvl = max(1, min(6, min(la, lc)))
            inner = "=" * (la - lvl) + inner + "=" * (lc - lvl)
            inner = inner.strip()
            if inner:
                h = max(2, min(6, start + lvl - 2))
                out += ["", f"<h{h}>{inner}</h{h}>", ""]
                continue
        out.append(line)
    return "\n".join(out)


PH_PIPE = "\ue0f3"
NL = chr(10)


def drop_standalone_removed_template_lines(text: str, ctx: PageCtx) -> str:
    """שורה שכולה תבנית שמוסרת (למשל {{עמוד|2}}) נמחקת כולה: ב-MediaWiki היא inline ואינה שוברת פסקה."""
    out = []
    for ln in text.split(NL):
        if ln.strip() and _is_remove_template_line(ln):
            ctx.stats["שורות תבנית-מוסרת עצמאית שנמחקו (עמוד וכד')"] += 1
            continue
        out.append(ln)
    return NL.join(out)


def preprocess(wt: str, ctx: PageCtx, start: int, view_page: bool = True, lite: bool = False) -> str:
    wt = wt.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    wt = re.sub(r"<!--.*?-->", "", wt, flags=re.S)
    wt = SECTION_TAG_RE.sub("", wt)
    if view_page:
        wt = apply_inclusion(wt, False)
    wt = MAGIC_HE_RE.sub("", MAGIC_RE.sub("", wt))
    if not lite:
        wt = drop_standalone_removed_template_lines(wt, ctx)
    wt = re.sub(r"<references\b[^>]*/>|<references\b[^>]*>.*?</references\s*>", "", wt, flags=re.S | re.I)
    wt = re.sub(r"<templatestyles\b[^>]*/>", "", wt, flags=re.I)
    n = len(re.findall(r"<gallery\b", wt, re.I))
    if n:
        ctx.stats["gallery שהוסרו"] += n
        wt = re.sub(r"<gallery\b.*?</gallery>", "", wt, flags=re.S | re.I)
    if re.search(r"<pages\b", wt, re.I):
        ctx.warnings.append("תג <pages> (ProofreadPage) - לא נתמך, הטקסט לא נטען")
    # nowiki / pre -> מחזיקי מקום (התוכן נשמר כמות שהוא)
    wt = re.sub(r"<nowiki\s*/>", "", wt, flags=re.I)

    def keep(m):
        ctx.nowiki.append(m.group(1))
        return f"{NOWIKI_OPEN}{len(ctx.nowiki) - 1}{NOWIKI_CLOSE}"
    wt = re.sub(r"<nowiki>(.*?)</nowiki>", keep, wt, flags=re.S | re.I)
    wt = re.sub(r"<pre\b[^>]*>(.*?)</pre>", lambda m: keep(m).replace("\n", ""), wt, flags=re.S | re.I)

    def poem(m):
        ctx.stats["poem"] += 1
        rows = [r.strip() for r in m.group(1).strip("\n").split("\n")]
        return "\n\n" + "<br>".join(rows) + "\n\n"
    wt = re.sub(r"<poem\b[^>]*>(.*?)</poem>", poem, wt, flags=re.S | re.I)

    if not lite:
        def ref(m):
            attrs, body = m.group(1), m.group(2)
            nm = re.search(r'name\s*=\s*"?([^"\s/>]+)"?', attrs)
            key = nm.group(1) if nm else None
            if body is None:
                if key and key in ctx.named_refs:
                    body = ctx.named_refs[key]
                    ctx.stats["הפניות ref בשם (הערה שוכפלה)"] += 1
                else:
                    ctx.warnings.append(f"<ref name={key}/> ללא גוף מוגדר")
                    return ""
            elif key:
                ctx.named_refs[key] = body
            ctx.refs.append(body)
            return f"{REF_OPEN}{len(ctx.refs) - 1}{REF_CLOSE}"
        wt = REF_RE.sub(ref, wt)
    wt = strip_file_and_category_links(wt, ctx)
    if not lite:
        if "{|" in wt:
            wt = convert_tables(wt, ctx.stats)
        wt = wiki_headings_to_html(wt, start)
    wt = re.sub(r"(?m)^[ 	]*-{4,}[ 	]*$", NL + PH_HR + NL, wt)  # ---- = קו מפריד
    # מניעת פירוש שגוי של טקסט מקור כסימון ויקי
    wt = wt.replace("+", PH_PLUS).replace("__", PH_UNDER)
    wt = re.sub(r"(?<=[א-ת])''(?=[א-ת]{1,2}(?![א-ת']))", PH_GERSH2, wt)  # ר''ת / חז''ל = גרשיים (1-2 אותיות אחריהם), לא תחילת נטוי כמו ו''נטוי''
    return wt


# ---------------------------------------------------------------------------
# איזון תגים בין פסקאות, ניקוי וסריאליזציה
# ---------------------------------------------------------------------------
TAG_TOKEN = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s[^<>]*)?)(/?)>")
CARRY = {"b", "i", "u", "s", "small", "big", "center", "div", "blockquote", "strong", "em", "mark",
         "span", "font", "strike", "del", "ins", "cite", "code"}
ALLOWED = {"h1", "h2", "h3", "h4", "h5", "h6", "b", "strong", "i", "em", "big", "small", "u", "ins", "s", "del",
           "strike", "mark", "sup", "sub", "a", "details", "summary", "ol", "ul", "li", "table", "tr", "td", "th",
           "caption", "thead", "tbody", "div", "p", "blockquote", "center", "pre", "code", "br", "ruby", "rt", "rp",
           "abbr", "acronym", "span"}
DROP_TAGS = {"img", "hr", "script", "style", "svg", "video", "audio", "iframe", "noscript", "template"}
ATTR_OK = {"a": {"href"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"},
           "table": {"border", "cellpadding"}, "ol": {"start", "type", "reversed"}, "ul": {"type"},
           "details": {"open"}}
STYLE_TAGS = {"p", "div", "center", "blockquote", "span"}
ITALIC_TAGS = {"i", "em", "cite", "var", "dfn"}
# בלוקים ברמה העליונה של שורה: כל אחד בשורת ספר משלו (חוזה: בלוק = שובר שורה)
BLOCK_TOP = {"div", "center", "blockquote", "ul", "ol", "table", "p", "details", "pre"}


def rebalance(lines: list[str]) -> list[str]:
    """תגי עיצוב שנפתחו בפסקה ונסגרו בפסקה מאוחרת: נסגרים בסוף כל שורה ונפתחים מחדש בבאה."""
    out: list[str] = []
    stack: list[tuple[str, str]] = []
    for idx, line in enumerate(lines):
        if HEADING_LINE_RE.match(line):
            stack = []
            out.append(line)
            continue
        prefix = "".join(t for _, t in stack)
        local = list(stack)
        for m in TAG_TOKEN.finditer(line):
            closing, name, _attrs, selfc = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
            if name not in CARRY:
                continue
            if closing:
                for k in range(len(local) - 1, -1, -1):
                    if local[k][0] == name:
                        del local[k]
                        break
            elif not selfc:
                local.append((name, m.group(0)))
        carry: list[tuple[str, str]] = []
        for name, opening in local:
            ahead = "\n".join(lines[idx + 1: idx + 60])
            if re.search(rf"</{name}\s*>", ahead, re.I):
                carry.append((name, opening))
        suffix = "".join(f"</{n}>" for n, _ in reversed(local))
        out.append(prefix + line + suffix)
        stack = carry
    return out


def esc_text(s: str) -> str:
    s = re.sub(r"&(?=#?\w+;)", "&amp;", s)
    return s.replace("<", "&lt;").replace(">", "&gt;").replace("\xa0", "&nbsp;")


def clean_style(val: str) -> str:
    keep = []
    for decl in val.split(";"):
        if ":" not in decl:
            continue
        k, v = (x.strip().lower() for x in decl.split(":", 1))
        ok = (
            (k == "text-align" and v in ("left", "right", "center", "justify"))
            or (k == "color" and re.fullmatch(r"#[0-9a-f]{3,8}|[a-z]+|rgba?\([\d\s,.%]+\)", v) and "rebecca" not in v)
            or (k == "font-size" and re.fullmatch(r"\d+(\.\d+)?(px|pt|em|%)", v))
            or (k == "font-weight" and v in ("bold", "normal") or (k == "font-weight" and re.fullmatch(r"[1-9]00", v)))
            or (k == "font-style" and v in ("italic", "normal"))
            or (k == "text-decoration" and v in ("underline", "line-through", "none"))
        )
        if ok:
            keep.append(f"{k}: {v}")
    return "; ".join(keep) + (";" if keep else "")


def ser_node(node, in_heading: bool, in_note: bool) -> str:
    from bs4 import Comment, NavigableString
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return esc_text(str(node))
    name = (node.name or "").lower()
    if name in DROP_TAGS:
        return ""
    if name in ("ul", "ol"):
        parts: list[str] = []
        for c in node.children:
            piece = ser_node(c, in_heading, in_note)
            if getattr(c, "name", None) in ("ul", "ol") and piece:
                k = next((j for j in range(len(parts) - 1, -1, -1) if parts[j].strip()), None)
                if k is not None and parts[k].startswith("<li") and parts[k].endswith("</li>"):
                    parts[k] = parts[k][:-5] + piece + "</li>"
                    continue
            parts.append(piece)
        inner = "".join(parts)
    else:
        inner = "".join(ser_node(c, in_heading, in_note) for c in node.children)
    if name == "br":
        return " " if in_heading else "<br>"
    if in_note and name in ITALIC_TAGS:
        return inner
    if in_heading and name in ("b", "strong", "big", "small", "i", "em", "p", "div", "center", "span", "font"):
        return inner
    if name not in ALLOWED:
        return inner
    if not inner.strip():
        return ""
    attrs = ""
    for k in sorted(ATTR_OK.get(name, ())):
        v = node.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            v = " ".join(v)
        if name == "a":
            if not re.match(r"(https?://|mailto:|#)", v.strip(), re.I):
                return inner
            v = v.strip()
        elif k in ("colspan", "rowspan", "border", "cellpadding", "start") and not str(v).isdigit():
            continue
        attrs += f' {k}="{htmllib.escape(str(v), quote=True)}"' if v != "" else f" {k}"
    if name in STYLE_TAGS and node.get("style"):
        st = clean_style(node["style"] if isinstance(node["style"], str) else " ".join(node["style"]))
        if st:
            attrs += f' style="{st}"'
    if name == "span" and not attrs:
        return inner
    if name == "a" and not attrs:
        return inner
    return f"<{name}{attrs}>{inner}</{name}>"


def finalize_line(line: str, in_note: bool = False) -> list[str]:
    """שורת HTML -> שורות סופיות נקיות (כותרות בשורה משלהן)."""
    from bs4 import Tag
    soup = BeautifulSoup(line, "html.parser")
    outs: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        s = buf
        buf = ""
        s = re.sub(r"[ \t]*<br>[ \t]*", "<br>", s)
        s = re.sub(r"^(?:<br>)+|(?:<br>)+$", "", s.strip())
        s = re.sub(r" {2,}", " ", s).strip()
        s = re.sub(r"^(?:<br>)+|(?:<br>)+$", "", s)
        if re.sub(r"<[^>]*>", "", s).strip():
            outs.append(s)

    for node in soup.contents:
        if isinstance(node, Tag) and (node.name or "").lower() in ("h1", "h2", "h3", "h4", "h5", "h6"):
            flush()
            if in_note:
                buf += ser_node(node, True, in_note)
                continue
            inner = "".join(ser_node(ch, True, in_note) for ch in node.children)
            inner = re.sub(r"\s+", " ", inner).strip()
            if re.sub(r"<[^>]*>", "", inner).strip():
                outs.append(f"<{node.name.lower()}>{inner}</{node.name.lower()}>")
        elif isinstance(node, Tag) and not in_note and (node.name or "").lower() in BLOCK_TOP:
            flush()
            buf += ser_node(node, False, in_note)
            flush()
        else:
            buf += ser_node(node, False, in_note)
    flush()
    return outs


def restore_tokens(s: str, ctx: PageCtx) -> str:
    s = s.replace(PH_PLUS, "+").replace(PH_UNDER, "__").replace(PH_GERSH2, "''").replace(PH_PIPE, "|")
    s = s.replace(PH_EMPTY, "&nbsp;")
    if s.strip() == PH_HR:
        return "<hr>"
    s = s.replace(PH_HR, "")

    def nw(m):
        raw = ctx.nowiki[int(m.group(1))]
        return raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(NOWIKI_OPEN + r"(\d+)" + NOWIKI_CLOSE, nw, s)


# ---------------------------------------------------------------------------
# המרת דף / הערה
# ---------------------------------------------------------------------------
GRAY_SUP_RE = re.compile(r'<sup style="color: gray;">(\d+)</sup>')
MARK_SCAN_RE = re.compile(r'<sup style="color: gray;">(\d+)</sup>|' + REF_OPEN + r"(\d+)" + REF_CLOSE)


def convert_note(body_html_or_wiki: str, ctx: PageCtx, is_wikitext: bool) -> str:
    """גוף הערה -> שורת HTML אחת בלי <i> (חוזה המיזוג)."""
    t = body_html_or_wiki
    if is_wikitext:
        t = preprocess(t, ctx, 2, view_page=True, lite=True)
        t = mediawikitohtml.media_wiki_list_to_html(t)
    t = mediawikitohtml.wikitext_to_html(t, 2)
    if is_wikitext:
        t, _ = templates.remove_templates(t)
    t = GRAY_SUP_RE.sub("", t)
    t = re.sub(REF_OPEN + r"\d+" + REF_CLOSE, "", t)
    t = htmltootzaria.fix_comments(t)
    t = htmllib.unescape(t)
    parts: list[str] = []
    for ln in t.split("\n"):
        parts += finalize_line(ln, in_note=True)
    s = "<br>".join(parts)
    return restore_tokens(s, ctx).strip()


@dataclass
class PageResult:
    lines: list[str]
    notes: list[str]
    unmapped: Counter
    warnings: list[str]
    stats: Counter


def convert_page(wt: str, start: int, note_start: int, norm_start: int | None = None) -> PageResult:
    ctx = PageCtx()
    before = Counter(templates.unmapped_templates)
    c = preprocess(wt, ctx, start)
    c = mediawikitohtml.media_wiki_list_to_html(c)
    c = mediawikitohtml.wikitext_to_html(c, start)
    c, sup = templates.remove_templates(c)
    c = mediawikitohtml.fix_new_lines(c)
    c = "\n".join(rebalance(c.split("\n")))
    c = htmltootzaria.process_body_html(c, norm_start or start)
    c = htmltootzaria.adjust_html_tag_spaces(c)
    # סמני הערות -> אסימון עם מספר גלובלי, לפי סדר הופעה
    notes: list[str] = []
    counter = [note_start]

    def mark(m):
        if m.group(1) is not None:
            body, is_wt = sup.get(int(m.group(1)), ""), False
        else:
            body, is_wt = ctx.refs[int(m.group(2))], True
        counter[0] += 1
        notes.append(convert_note(body, ctx, is_wt) if body.strip() else "")
        return f"{MARK_OPEN}{counter[0]}{MARK_CLOSE}"
    c = MARK_SCAN_RE.sub(mark, c)
    lines: list[str] = []
    for ln in c.split("\n"):
        for fl in finalize_line(ln):
            lines.append(restore_tokens(fl, ctx))
    after = templates.unmapped_templates
    diff = Counter({k: v - before.get(k, 0) for k, v in after.items() if v - before.get(k, 0) > 0})
    return PageResult(lines, notes, diff, ctx.warnings, ctx.stats)


# ---------------------------------------------------------------------------
# זיהוי כותרת בראש הדף, דף-תוכן בלבד
# ---------------------------------------------------------------------------
def _is_remove_template_line(line: str) -> bool:
    s = line.strip()
    if not (s.startswith("{{") and s.endswith("}}")):
        return False
    try:
        tpls = mwp.parse(s).filter_templates(recursive=False)
    except Exception:
        return False
    if len(tpls) != 1 or str(tpls[0]) != s:
        return False
    name = str(tpls[0].name).strip()
    if name.startswith("#") and ":" in name:
        name = name.split(":", 1)[0].strip()
    act = templates.replacement_dict.get(name, "missing")
    return act is tfuncs.remove or name in ("עמוד",)


def leading_heading_level(wt: str) -> int | None:
    t = re.sub(r"<!--.*?-->", "", wt, flags=re.S)
    t = SECTION_TAG_RE.sub("", t)
    for line in t.split("\n"):
        if not line.strip() or _is_remove_template_line(line):
            continue
        m = HEADING_WIKI_RE.match(line.strip()) if line.lstrip().startswith("=") else None
        if m and m.group(2).strip():
            return max(1, min(6, min(len(m.group(1)), len(m.group(3)))))
        return None
    return None


def toc_only(wt: str) -> bool:
    t = re.sub(r"<!--.*?-->", "", wt, flags=re.S)
    for _ in range(6):
        n = re.sub(r"\{\{[^{}]*\}\}", "", t)
        if n == t:
            break
        t = n
    words = 0
    for line in t.split("\n"):
        s = line.strip()
        if not s or s.startswith(("=", "*", "#", ":", ";", "[[קטגוריה")):
            continue
        words += len(HEB_RE.findall(re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)))
    return words < 12


# ---------------------------------------------------------------------------
# עץ הספר
# ---------------------------------------------------------------------------
@dataclass
class Node:
    title: str
    seg: str
    depth: int
    exists: bool = False
    children: list["Node"] = field(default_factory=list)


@dataclass
class PlanItem:
    title: str
    seg: str
    depth: int
    kind: str  # content | container | synthetic | problem
    status: str = ""
    note: str = ""
    resolved: str = ""
    own_heading_level: int | None = None
    words: int = 0
    errors: list[str] = field(default_factory=list)


class Report:
    def __init__(self):
        self.blocked: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.missing: list[str] = []
        self.red_links: list[str] = []
        self.empty: list[str] = []
        self.skipped: list[tuple[str, str]] = []
        self.not_in_toc: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []
        self.unmapped: dict[str, dict] = {}
        self.unresolved: list[str] = []
        self.page_warnings: list[tuple[str, str]] = []
        self.stats: Counter = Counter()
        self.plan: list[dict] = []
        self.leftovers: dict[str, list] = {}
        self.footnote_checks: list[str] = []
        self.validator: dict[str, str] = {}
        self.mode = ""
        self.coverage: dict = {}
        self.preservation: dict = {}
        self.author_hints: list[str] = []
        self.status = ""

    def block(self, title: str, reason: str):
        if all(t != title for t, _ in self.blocked):
            self.blocked.append((title, reason))
            print(f"נחסם בנטפרי: {title} ({reason})", file=sys.stderr)


def get_resolved(client: WikiClient, title: str, rep: Report) -> PageData:
    pd = client.get_page(title)
    if pd.status == "blocked":
        rep.block(title, pd.note)
        return pd
    if pd.status != "ok":
        return pd
    if pd.resolved is None:
        errs: list[str] = []
        try:
            pd.resolved = resolve_text(client, title, pd.text, errs)
        except Blocked as b:
            rep.block(b.what, b.reason)
            pd.status, pd.note = "blocked", f"תלוי ב-{b.what}: {b.reason}"
            return pd
        pd.errors = errs
    return pd


def rank_in(links: list[str], node_title: str) -> int:
    for i, l in enumerate(links):
        if l == node_title or l.startswith(node_title + "/"):
            return i
    return 10 ** 6


def build_plan(client: WikiClient, main_title: str, main_resolved: str, subpages: list[str],
               redirects: set[str], args, rep: Report) -> list[PlanItem]:
    nodes: dict[str, Node] = {}
    root = Node(main_title, main_title, 0, True)
    nodes[main_title] = root
    for t in subpages:
        rel = t[len(main_title) + 1:]
        segs = rel.split("/")
        parent = root
        for i in range(1, len(segs) + 1):
            tt = main_title + "/" + "/".join(segs[:i])
            nd = nodes.get(tt)
            if nd is None:
                nd = Node(tt, segs[i - 1], i)
                nodes[tt] = nd
                parent.children.append(nd)
            if i == len(segs):
                nd.exists = True
            parent = nd

    main_links_raw = extract_links(main_resolved, main_title)
    main_links: list[str] = []
    for l in main_links_raw:
        if l in redirects:
            try:
                tgt = client.redirect_target(l)
            except (Blocked, FetchError) as e:
                if isinstance(e, Blocked):
                    rep.block(l, e.reason)
                tgt = None
            l = norm_title(tgt) if tgt else l
        main_links.append(l)
    # קישורי תוכן עניינים לדפים שאינם קיימים = דפים אדומים
    for l in dict.fromkeys(main_links):
        if l.startswith(main_title + "/") and l not in nodes:
            rep.red_links.append(l)

    def rel(e: str) -> str:
        e = norm_title(e)
        return e if e.startswith(main_title + "/") else main_title + "/" + e.lstrip("/")
    excl = {rel(e) for e in args.exclude_page}
    incl = {rel(e) for e in args.include_page}
    items: list[PlanItem] = []

    def skip(nd: Node, why: str):
        rep.skipped.append((nd.title, why))

    def visit(nd: Node, local_links: list[str]):
        kids = sorted(nd.children, key=lambda c: (
            (0, rank_in(main_links, c.title)) if rank_in(main_links, c.title) < 10 ** 6 else
            (1, rank_in(local_links, c.title)) if rank_in(local_links, c.title) < 10 ** 6 else (2, 0),
            natural_key(c.seg)))
        unlisted = [c.title for c in kids if rank_in(main_links, c.title) >= 10 ** 6 and rank_in(local_links, c.title) >= 10 ** 6]
        if unlisted:
            rep.not_in_toc += [u for u in unlisted if u not in rep.not_in_toc]
        for c in kids:
            if c.title in excl or (c.seg in FULL_NAMES | TOC_NAMES and c.title not in incl):
                skip(c, "דף הכול (השתמש ב--mode full)" if c.seg in FULL_NAMES else
                     "דף תוכן/ניווט" if c.seg in TOC_NAMES else "הוחרג ב--exclude-page")
                continue
            if not c.exists:
                items.append(PlanItem(c.title, c.seg, c.depth, "synthetic"))
                visit(c, [])
                continue
            pd = get_resolved(client, c.title, rep)
            if pd.status in ("blocked",):
                items.append(PlanItem(c.title, c.seg, c.depth, "problem", "blocked", pd.note))
                continue
            if pd.status in ("failed", "mismatch"):
                rep.failed.append((c.title, f"{pd.status}: {pd.note}"))
                items.append(PlanItem(c.title, c.seg, c.depth, "problem", pd.status, pd.note))
                continue
            if pd.status == "missing":
                rep.missing.append(c.title)
                items.append(PlanItem(c.title, c.seg, c.depth, "problem", "missing"))
                continue
            if pd.status == "empty" or not (pd.resolved or "").strip():
                rep.empty.append(c.title)
                if c.children:
                    items.append(PlanItem(c.title, c.seg, c.depth, "container", "empty"))
                    visit(c, [])
                else:
                    items.append(PlanItem(c.title, c.seg, c.depth, "problem", "empty"))
                continue
            for e in pd.errors:
                rep.unresolved.append(f"{c.title}: {e}")
            loc = extract_links(pd.resolved, c.title)
            it = PlanItem(c.title, c.seg, c.depth, "content", "ok", resolved=pd.resolved, errors=pd.errors)
            if c.children and toc_only(pd.resolved):
                it.kind = "container"
                it.resolved = ""
            elif c.children:
                rep.warnings.append(f"דף עם תתי-דפים וגם טקסט משלו (ייתכן שבגוף יש רשימת קישורים כפולה): {c.title}")
            it.own_heading_level = leading_heading_level(it.resolved) if it.kind == "content" else None
            it.words = count_words(it.resolved)
            items.append(it)
            visit(c, loc)

    visit(root, main_links)
    return items


# ---------------------------------------------------------------------------
# הרצת וולידטורים, בדיקות
# ---------------------------------------------------------------------------
def run_validators(repo: Path, book: Path, notes: Path | None, links: Path | None, rep: Report) -> int:
    scripts = repo / ".claude" / "skills" / "otzaria-book-format" / "scripts"
    rc_all = 0
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    vb = scripts / "validate_book.py"
    if vb.exists():
        files = [str(book)] + ([str(notes)] if notes else [])
        r = subprocess.run([sys.executable, "-X", "utf8", "-I", str(vb), *files], capture_output=True,
                           encoding="utf-8", errors="replace", env=env)
        rep.validator["validate_book"] = (r.stdout + r.stderr).strip()
        rc_all = max(rc_all, 1 if r.returncode else 0)
    else:
        rep.validator["validate_book"] = f"לא נמצא: {vb}"
    vs = scripts / "validate_sidecars.py"
    if links and vs.exists():
        cmd = [sys.executable, "-X", "utf8", "-I", str(vs), "--links", str(links), "--book", str(book)]
        if notes:
            cmd += ["--target", str(notes)]
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", env=env)
        rep.validator["validate_sidecars"] = (r.stdout + r.stderr).strip()
        rc_all = max(rc_all, 1 if r.returncode else 0)
    return rc_all


LEFTOVER_PATTERNS = {
    "{{": r"\{\{", "}}": r"\}\}", "[[": r"\[\[", "]]": r"\]\]", "<ref": r"</?ref\b",
    "__HTML_REGION_": r"__HTML_REGION_", "''/'''": r"'{2,}", "<קטע": r"<\s*(?:קטע|section)\b",
    "<pages": r"<pages\b", "{| / |}": r"\{\||\|\}", "<!--": r"<!--", "__MAGIC__": r"__[A-Z]{3,}__",
    "<nowiki/<poem/<gallery": r"<(?:nowiki|poem|gallery|references)\b", "&lt;": r"&lt;|&gt;",
}


def scan_leftovers(lines: list[str], tag: str, rep: Report):
    for name, pat in LEFTOVER_PATTERNS.items():
        rx = re.compile(pat)
        for i, ln in enumerate(lines, 1):
            m = rx.search(ln)
            if m:
                s = max(0, m.start() - 25)
                rep.leftovers.setdefault(name, []).append((tag, i, ln[s:m.end() + 35]))


def check_merge_contract(base: list[str], notes: list[str], links: list[dict], notes_name: str, rep: Report):
    """חוזה HearotCompanionMerge (ADDING_BOOKS סעיף 3) - לפי הטבלה."""
    problems = []
    if not notes_name.startswith("הערות על "):
        problems.append("שם ספר ההערות אינו מתחיל ב'הערות על '")
    linked = {l["line_index_2"] for l in links}
    for i, ln in enumerate(notes, 1):
        blank = not ln.strip()
        head = bool(HEADING_LINE_RE.match(ln))
        if not blank and not head and i not in linked:
            problems.append(f"unlinked note line: {i}")
        if re.search(r"<i\b|<em\b", ln, re.I):
            problems.append(f"note with <i> markup: {i}")
    for l in links:
        j = l["line_index_2"]
        if not (1 <= j <= len(notes)):
            problems.append(f"companion link out of range (note): {j}")
            continue
        if not notes[j - 1].strip():
            problems.append(f"linked blank note line: {j}")
        if HEADING_LINE_RE.match(notes[j - 1]):
            problems.append(f"linked heading note line: {j}")
        k = l["line_index_1"]
        if not (1 <= k <= len(base)):
            problems.append(f"companion link out of range (base): {k}")
        elif HEADING_LINE_RE.match(base[k - 1]):
            problems.append(f"link from heading base line: {k}")
        if any(x in l for x in ("line_index_1_end", "line_index_2_end", "start", "end")):
            problems.append(f"ranged/word-anchored link: {l}")
        if l.get("Conection Type") != "footnotes" or "ref_2" in l:
            problems.append("סוג קישור אינו footnotes או שיש ref_2")
    for i, ln in enumerate(base, 1):
        if 'class="footnote' in ln:
            problems.append(f"base line carries inline footnotes: {i}")
    rep.footnote_checks = problems or ["חוזה המיזוג: תקין (כל הבדיקות עברו)"]


TOKEN_RE = re.compile(r"[֐-׿]+")


def expected_tokens(wt: str) -> Counter:
    """טוקנים עבריים שצפויים להופיע בפלט: ה-wikitext בלי שמות תבניות, יעדי קישור, תגיות והערות."""
    t = re.sub(r"<!--.*?-->", "", wt, flags=re.S)
    t = SECTION_TAG_RE.sub("", t)
    t = MAGIC_HE_RE.sub("", t)
    t = re.sub(r"\[\[\s*(?:קובץ|File|Image|תמונה|קטגוריה|Category)\s*:[^\]]*\]\]", "", t, flags=re.I)
    if "{{" in t:  # תבניות שמיפויין "הסר" - גם הפרמטרים שלהן אינם צפויים בפלט
        parsed = mwp.parse(t)
        for tpl in parsed.filter_templates(recursive=False):
            nm = str(tpl.name).strip()
            if nm.startswith("#") and ":" in nm:
                nm = nm.split(":", 1)[0].strip()
            if nm not in templates.footnote_templates and nm in templates.replacement_dict and (templates.replacement_dict[nm] is None or templates.replacement_dict[nm] is tfuncs.remove):
                try:
                    parsed.remove(tpl)
                except ValueError:
                    pass
        t = str(parsed)
    t = re.sub(r"\{\{\s*[^{}|]*", " ", t)
    t = re.sub(r"\[\[(?:[^\]|\[]*\|)", "[[", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"<[^>]*>", " ", t)
    return Counter(TOKEN_RE.findall(t))


def preservation_check(plan: list, base_lines: list[str], notes_lines: list[str], rep: Report):
    src = Counter()
    for it in plan:
        if it.kind == "content":
            src += expected_tokens(it.resolved)
    out = Counter()
    for ln in base_lines[3:] + notes_lines[1:]:
        out += Counter(TOKEN_RE.findall(re.sub(r"<[^>]*>", " ", htmllib.unescape(ln))))
    missing = src - out
    extra = out - src
    rep.preservation = {
        "טוקנים עבריים במקור (אחרי הסרת שמות תבניות/יעדי קישור)": sum(src.values()),
        "טוקנים בפלט (ספר+הערות)": sum(out.values()),
        "חסרים בפלט": sum(missing.values()),
        "עודפים בפלט (כותרות שנוספו וכד')": sum(extra.values()),
        "חסרים - הנפוצים": ", ".join(f"{k}x{v}" for k, v in missing.most_common(25)),
        "עודפים - הנפוצים": ", ".join(f"{k}x{v}" for k, v in extra.most_common(15)),
    }
    if sum(missing.values()) > max(5, 0.002 * sum(src.values())):
        rep.warnings.append(f"בדיקת שימור: {sum(missing.values())} טוקנים עבריים מהמקור לא נמצאו בפלט - לבדוק (ראה הדוח)")


# ---------------------------------------------------------------------------
# דוח
# ---------------------------------------------------------------------------
def render_report(rep: Report, ctx: dict) -> str:
    L: list[str] = []
    add = L.append
    add(f"דוח ws_book - {ctx['title']}")
    add(f"סטטוס: {rep.status}")
    add(f"שם הספר (h1): {ctx['h1']} | קובץ: {ctx['file_name']}.txt | מצב: {rep.mode} | בקשות רשת: {ctx.get('requests', 0)}")
    add(f"שורות בספר: {ctx.get('lines', 0)} | הערות: {ctx.get('notes', 0)} | מילים: {ctx.get('words', 0)}")
    add("")
    if rep.blocked:
        add("== נחסם בנטפרי (הספר מסומן 'נחסם'; לא נעשה כל ניסיון עקיפה) ==")
        for t, r in rep.blocked:
            add(f"נחסם בנטפרי: {t}  [{r}]")
        add("")
    for title, items in (("דפים שנכשלו (רשת/המרה/שלמות)", [f"{t}  [{r}]" for t, r in rep.failed]),
                         ("דפים אדומים (קישור בתוכן עניינים לדף שאינו קיים)", rep.red_links),
                         ("דפים שנמצאו חסרים", rep.missing),
                         ("דפים ריקים", rep.empty),
                         ("תתי-דפים שלא מופיעים בתוכן העניינים (סדרם נקבע בניחוש; נכללו)", rep.not_in_toc),
                         ("תתי-דפים שדולגו", [f"{t}  [{r}]" for t, r in rep.skipped]),
                         ("transclusion שלא נפתר", rep.unresolved),
                         ("אזהרות", rep.warnings),
                         ("אזהרות לפי דף", [f"{t}: {w}" for t, w in rep.page_warnings])):
        if items:
            add(f"== {title} ({len(items)}) ==")
            for x in items:
                add(f"  {x}")
            add("")
    add(f"== תבניות לא ממופות (templates.unmapped_templates) - {len(rep.unmapped)} ==")
    if not rep.unmapped:
        add("  אין")
    for name, d in sorted(rep.unmapped.items(), key=lambda kv: -kv[1]["count"]):
        add(f"  {{{{{name}}}}} x{d['count']}  דפים: {', '.join(d['pages'][:4])}{' ...' if len(d['pages']) > 4 else ''}")
        if d.get("example"):
            add(f"      דוגמה: {d['example']}")
    add("  (תבנית לא ממופה מוחלפת בפרמטר המיקומי האחרון שלה - לבדוק שזה נכון, או להוסיף מיפוי ב--template-map)")
    add("")
    add("== שאריות סימון ==")
    if not rep.leftovers:
        add("  אין")
    for name, hits in rep.leftovers.items():
        add(f"  {name}: {len(hits)}")
        for tag, ln, snip in hits[:5]:
            add(f"      [{tag} שורה {ln}] {snip}")
    add("")
    if rep.stats:
        add("== סטטיסטיקה ==")
        for k, v in rep.stats.items():
            add(f"  {k}: {v}")
        add("")
    add("== חוזה מיזוג הערות ==")
    for x in rep.footnote_checks or ["אין הערות"]:
        add(f"  {x}")
    add("")
    if rep.preservation:
        add("== בדיקת שימור טקסט (טוקנים עבריים: מקור מול פלט) ==")
        for k, v in rep.preservation.items():
            add(f"  {k}: {v}")
        add("")
    if rep.coverage:
        add("== השוואה לדף 'הכול' ==")
        for k, v in rep.coverage.items():
            add(f"  {k}: {v}")
        add("")
    if rep.author_hints:
        add("== רמזים למחבר (לא נכנסו לקובץ; להזין ב--author) ==")
        for h in rep.author_hints:
            add(f"  {h}")
        add("")
    if rep.info:
        add("== מידע ==")
        for x in rep.info:
            add(f"  {x}")
        add("")
    add("== תוכנית הדפים (סדר הספר) ==")
    for p in rep.plan:
        add(f"  {'  ' * (p['depth'] - 1)}[{p['kind']}{'/' + p['status'] if p['status'] and p['status'] != 'ok' else ''}] "
            f"{p['title']}  ({p['words']} מילים)")
    add("")
    for k, v in rep.validator.items():
        add(f"== {k} ==")
        add(v)
        add("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# הרצה ראשית
# ---------------------------------------------------------------------------
def apply_template_map(path: str | None, rep: Report):
    if not path:
        return
    acts = {
        "remove": tfuncs.remove, "keep_all": tfuncs.save_all, "keep_first": partial(tfuncs.keep_some_params, params_to_keep=[0]),
        "keep_last": tfuncs.last_positional, "bold": tfuncs.bold, "big": tfuncs.big, "line_break": tfuncs.line_break,
        "parenthesize": tfuncs.parenthesize_only, "underline": tfuncs.line_under, "new_line": tfuncs.new_line,
        "small": lambda t: f"<small>{' '.join(tfuncs.positional(t))}</small>",
        "italic": lambda t: f"<i>{' '.join(tfuncs.positional(t))}</i>",
    }
    m = json.load(open(path, encoding="utf-8"))
    for name, act in m.items():
        if isinstance(act, str) and act.startswith("literal:"):
            lit = act[len("literal:"):]
            templates.replacement_dict[name] = lambda t, _l=lit: _l
            continue
        if act not in acts:
            raise SystemExit(f"--template-map: פעולה לא מוכרת '{act}' (אפשרויות: {', '.join(acts)})")
        templates.replacement_dict[name] = acts[act]
    rep.info.append(f"מיפויי תבניות נוספים מ-{path}: {', '.join(m)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="הורדת ספר מוויקיטקסט והמרה לאוצריא")
    ap.add_argument("--page", required=True, help="כותרת הדף הראשי של הספר")
    ap.add_argument("--out", required=True, help="תיקיית פלט")
    ap.add_argument("--name", help="שם הספר (h1 ושם הקובץ לפני ניקוי). ברירת מחדל: כותרת הדף בלי הסוגריים שבסופה")
    ap.add_argument("--author", default="", help="שם המחבר (שורה 2). ריק = שורה ריקה")
    ap.add_argument("--mode", choices=["auto", "chapters", "full"], default="auto",
                    help="chapters: תתי-דפים לפי תוכן העניינים (auto); full: דף 'הכול' בלבד")
    ap.add_argument("--full-page", help="שם תת-הדף של 'הכול' (ברירת מחדל: שלם/הכול/הכל שקיים)")
    ap.add_argument("--exclude-page", action="append", default=[], help="תת-דף להחרגה (שם יחסי או מלא); חוזר")
    ap.add_argument("--include-page", action="append", default=[], help="תת-דף שיוחרג אוטומטית אך רוצים לכלול")
    ap.add_argument("--include-main", action="store_true", help="לכלול גם את גוף הדף הראשי לפני הפרקים")
    ap.add_argument("--template-map", help="JSON {שם תבנית: remove|keep_all|keep_first|keep_last|bold|big|small|italic|parenthesize|line_break|new_line|underline|literal:טקסט}")
    ap.add_argument("--marker-style", choices=["bare", "gray"], default="bare",
                    help="סמן ההערה בבסיס: bare=<sup>N</sup> (ברירת מחדל, בטוח ב-RTL) | gray=<sup style=\"color: gray;\">N</sup>")
    ap.add_argument("--note-line-style", choices=["sup", "plain"], default="sup",
                    help="תחילת שורת הערה: sup=<sup>N</sup> טקסט (כבבית אהרן וישראל) | plain=N טקסט")
    ap.add_argument("--order-page", help="דף (תבנית ניווט) שקישוריו קובעים סדר")
    ap.add_argument("--plan-only", action="store_true", help="רק לבנות ולהציג את תוכנית הדפים והסדר, בלי המרה")
    ap.add_argument("--allow-partial", action="store_true", help="לכתוב ספר חלקי (בשם PARTIAL_BLOCKED) גם כשדף נחסם/נכשל")
    ap.add_argument("--delay", type=float, default=0.25, help="השהיה בין בקשות (שניות)")
    ap.add_argument("--lib-dir", help="תיקיית wikisourceToOtzaria/סקריפטים (עם mediawikitootzaria)")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    lib = load_libs(args.lib_dir)
    repo = lib.parents[1]
    rep = Report()
    apply_template_map(args.template_map, rep)
    client = WikiClient(args.delay)
    out = Path(args.out)
    (out / "_report").mkdir(parents=True, exist_ok=True)

    def finish(code: int, status: str, ctx: dict, file_name: str) -> int:
        rep.status = status
        rep.info.append("תיקוני מקור מקומיים: " + "; ".join(f"{k} x{v}" for k, v in FIX_LOG.items()))
        ctx["requests"] = client.requests_made
        txt = render_report(rep, ctx)
        (out / "_report" / f"{file_name}.report.txt").write_text(txt, encoding="utf-8")
        js = {k: (v if not isinstance(v, Counter) else dict(v)) for k, v in rep.__dict__.items()}
        (out / "_report" / f"{file_name}.report.json").write_text(json.dumps(js, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"סטטוס: {status} | דוח: {out / '_report' / (file_name + '.report.txt')}")
        return code

    title = norm_title(args.page)
    h1 = args.name or default_book_name(title)
    file_name = sanitize_filename(h1)
    ctx = {"title": title, "h1": h1, "file_name": file_name}

    # --- דף ראשי ---
    main = client.get_page(title)
    if main.status == "blocked":
        rep.block(title, main.note)
        return finish(3, "נחסם", ctx, file_name)
    if main.status != "ok":
        rep.failed.append((title, f"דף ראשי: {main.status} {main.note}"))
        return finish(5 if main.status in ("missing", "empty") else 4, f"דף ראשי {main.status}", ctx, file_name)
    if main.redirect_to:
        title = norm_title(main.redirect_to)
        ctx["title"] = title
        rep.info.append(f"הדף הוגדר כהפניה; נעשה שימוש ב: {title}")
        if not args.name:
            h1 = default_book_name(title)
            file_name = sanitize_filename(h1)
            ctx.update(h1=h1, file_name=file_name)

    main_res = get_resolved(client, title, rep)
    if main_res.status == "blocked":
        return finish(3, "נחסם", ctx, file_name)
    for e in main_res.errors:
        rep.unresolved.append(f"{title}: {e}")
    try:
        subpages = client.allpages(title + "/")
        redirects = set(client.allpages(title + "/", redirects_only=True))
        cats = client.categories(title)
    except Blocked as b:
        rep.block(b.what, b.reason)
        return finish(3, "נחסם", ctx, file_name)
    except FetchError as e:
        rep.failed.append((title, f"רשימת תתי-דפים: {e}"))
        return finish(4, "כשל", ctx, file_name)
    if cats:
        rep.author_hints.append("קטגוריות הדף הראשי: " + " | ".join(cats[:12]))
    for tpl in mwp.parse(main.text).filter_templates(recursive=False):
        for pname in ("מחבר", "מחברים", "עורך", "מתרגם"):
            if tpl.has(pname) and str(tpl.get(pname).value).strip():
                rep.author_hints.append(f"תבנית {{{{{str(tpl.name).strip()}}}}} פרמטר {pname}: " + re.sub(r"\s+", " ", str(tpl.get(pname).value).strip())[:120])
    m = re.search(r"\{\{\s*דף שער\s*\|([^{}|]*)\|([^{}]*)", main.text)
    if m:
        rep.author_hints.append("דף שער: " + re.sub(r"\s+", " ", (m.group(1) + " | " + m.group(2)))[:200])
    rep.info.append(f"נמצאו {len(subpages)} תתי-דפים (ns 0, בלי הפניות)" + (f" ו-{len(redirects)} הפניות" if redirects else ""))

    # --- דף "הכול" ---
    full_name = None
    if args.full_page:
        full_name = abs_title("/" + args.full_page.lstrip("/"), title)
    else:
        for s in subpages:
            if s[len(title) + 1:] in FULL_NAMES:
                full_name = s
                break

    mode = args.mode
    if not subpages:
        mode = "single"
    elif mode == "auto":
        mode = "chapters"
    if mode == "full" and not full_name:
        rep.failed.append((title, "אין דף 'הכול' (שלם/הכול/הכל) - אפשר להריץ ב--mode chapters"))
        return finish(5, "אין דף הכול", ctx, file_name)
    rep.mode = mode

    plan: list[PlanItem] = []
    full_words = None
    if mode == "single":
        plan = [PlanItem(title, title, 1, "content", "ok", resolved=main_res.resolved or "")]
        plan[0].own_heading_level = None
        plan[0].words = count_words(plan[0].resolved)
        links_out = [l for l in extract_links(main.text, title) if not l.startswith(title)]
        if plan[0].words < 40 and len(links_out) >= 3:
            rep.warnings.append("אין תתי-דפים והדף הראשי נראה כתוכן עניינים לדפים אחרים: " + " | ".join(dict.fromkeys(links_out))[:300]
                                + " - ייתכן שהספר מורכב מדפים נפרדים (לא נתמך אוטומטית)")
    elif mode == "full":
        fp = get_resolved(client, full_name, rep)
        if fp.status != "ok":
            if fp.status != "blocked":
                rep.failed.append((full_name, f"{fp.status} {fp.note}"))
            return finish(3 if fp.status == "blocked" else 4, "נחסם" if fp.status == "blocked" else "כשל", ctx, file_name)
        it = PlanItem(full_name, full_name.rsplit("/", 1)[-1], 1, "content", "ok", resolved=fp.resolved or "")
        it.words = count_words(it.resolved)
        plan = [it]
    else:
        try:
            plan = build_plan(client, title, (main_res.resolved or main.text) + (chr(10) + client.get_page(args.order_page).text if args.order_page else ""), subpages, redirects, args, rep)
        except Blocked as b:
            rep.block(b.what, b.reason)
        if full_name:
            fp = get_resolved(client, full_name, rep)
            if fp.status == "ok":
                full_words = count_words(fp.resolved or "")
            elif fp.status != "blocked":
                rep.info.append(f"דף הכול {full_name}: {fp.status}")
        # גוף הדף הראשי
        body_words = count_words(re.sub(r"(?m)^\s*[*#:;].*$", "", main_res.resolved or main.text))
        rep.info.append(f"מילות טקסט בדף הראשי מלבד רשימות וקישורי תוכן: {body_words}"
                        + (" - יש טקסט משמעותי, ייתכן שצריך --include-main" if body_words > 80 and not args.include_main else ""))
        if args.include_main:
            it = PlanItem(title, "", 0, "content", "ok", resolved=main_res.resolved or main.text)
            it.words = count_words(it.resolved)
            plan.insert(0, it)

    rep.plan = [{"title": p.title, "depth": p.depth, "kind": p.kind, "status": p.status, "words": p.words} for p in plan]
    if args.plan_only:
        return finish(0, "תוכנית בלבד", ctx, file_name)

    if not any(p.kind == "content" for p in plan):
        if not rep.blocked:
            rep.failed.append((title, "לא נמצא שום דף תוכן"))
        return finish(3 if rep.blocked else 5, "נחסם" if rep.blocked else "אין תוכן", ctx, file_name)

    # --- המרה ---
    base_lines: list[str] = [f"<h1>{htmllib.escape(h1, quote=False)}</h1>", args.author.strip(),
                             COPYRIGHT_TMPL.format(enc=urllib.parse.quote(title.replace(" ", "_"), safe=""))]
    notes: list[str] = []
    convert_errors = 0
    for it in plan:
        d = max(2, min(6, it.depth + 1))
        if it.kind == "problem":
            continue
        if it.kind in ("synthetic", "container"):
            base_lines.append(f"<h{d}>{htmllib.escape(it.seg, quote=False)}</h{d}>")
            continue
        start = 2
        if mode in ("single", "full") or it.depth == 0:
            start = 2
        elif it.own_heading_level is not None:
            start = max(2, min(6, d - (it.own_heading_level - 2)))
        else:
            base_lines.append(f"<h{d}>{htmllib.escape(it.seg, quote=False)}</h{d}>")
            start = min(6, d + 1)
        try:
            res = convert_page(it.resolved, start, len(notes), max(start, d) if it.own_heading_level is not None and mode not in ("single", "full") and it.depth != 0 else None)
        except Blocked as b:  # לא אמור לקרות (אין רשת בהמרה)
            rep.block(b.what, b.reason)
            continue
        except Exception as e:  # noqa: BLE001
            convert_errors += 1
            rep.failed.append((it.title, f"שגיאת המרה: {type(e).__name__}: {e}"))
            continue
        for n, c in res.unmapped.items():
            d_ = rep.unmapped.setdefault(n, {"count": 0, "pages": [], "example": ""})
            d_["count"] += c
            d_["pages"].append(it.title)
            if not d_["example"]:
                mm = re.search(r"\{\{\s*" + re.escape(n) + r"\s*[|}][^{}]{0,70}", it.resolved)
                d_["example"] = mm.group(0)[:90] if mm else ""
        for w in res.warnings:
            rep.page_warnings.append((it.title, w))
        rep.stats.update(res.stats)
        if not res.lines:
            rep.empty.append(it.title + " (אחרי המרה)")
        while res.lines and res.lines[-1] == "<hr>":
            res.lines.pop()  # קו מפריד בסוף דף (לפני הערות שוליים שהוסרו)
        base_lines += res.lines
        notes += res.notes

    if rep.blocked or convert_errors or rep.failed:
        status = "נחסם" if rep.blocked else "כשל בדפים"
        if not args.allow_partial:
            ctx.update(lines=len(base_lines))
            return finish(3 if rep.blocked else 4, status + " - לא נכתב ספר (אפשר --allow-partial)", ctx, file_name)
        file_name = file_name + ".PARTIAL_BLOCKED"
        rep.info.append("נכתב ספר חלקי בגלל --allow-partial. אין להכניס אותו לספרייה.")

    # --- כותרות: רציפות היררכית ---
    fixes = 0
    prev = 1
    for i, ln in enumerate(base_lines):
        m = HEADING_FULL_RE.match(ln)
        if i == 0 or not m:
            continue
        lvl = int(m.group(1))
        if lvl > prev + 1:
            lvl = prev + 1
            base_lines[i] = f"<h{lvl}>{m.group(2)}</h{lvl}>"
            fixes += 1
        prev = lvl
    if fixes:
        rep.stats["כותרות שרמתן הוחלשה (דילוג רמות)"] = fixes

    # --- סמני הערות: הוצאה משורות כותרת, בניית קישורים ---
    mrk = re.compile(MARK_OPEN + r"(\d+)" + MARK_CLOSE)
    for i, ln in enumerate(base_lines):
        if HEADING_LINE_RE.match(ln) and mrk.search(ln):
            moved = "".join(m.group(0) for m in mrk.finditer(ln))
            base_lines[i] = mrk.sub("", ln)
            j = next((k for k in range(i + 1, len(base_lines)) if not HEADING_LINE_RE.match(base_lines[k]) and base_lines[k].strip()), None)
            if j is None:
                rep.warnings.append(f"סמן הערה בכותרת (שורה {i + 1}) ללא שורת טקסט אחריה - ההערה אבדה")
                for m in mrk.finditer(ln):
                    notes[int(m.group(1)) - 1] = ""
            else:
                base_lines[j] = moved + base_lines[j]
                rep.warnings.append(f"סמן הערה בתוך כותרת (שורה {i + 1}) הועבר לתחילת שורה {j + 1}")
    dead = {i + 1 for i, n in enumerate(notes) if not n.strip()}
    if dead:
        rep.warnings.append(f"הערות ריקות הוסרו (סמן והערה): {sorted(dead)[:20]}")
    # מספור מחדש רציף ללא ריקות
    remap: dict[int, int] = {}
    kept_notes: list[str] = []
    for i, n in enumerate(notes, 1):
        if i not in dead:
            kept_notes.append(n)
            remap[i] = len(kept_notes)
    links: list[dict] = []
    marker_html = (lambda n: f"<sup>{n}</sup>") if args.marker_style == "bare" else (lambda n: f'<sup style="color: gray;">{n}</sup>')
    notes_title = f"הערות על {file_name}"
    for i, ln in enumerate(base_lines, 1):
        for m in mrk.finditer(ln):
            old = int(m.group(1))
            if old in remap:
                links.append({"line_index_1": i, "line_index_2": remap[old] + 1, "heRef_2": "הערות",
                              "path_2": f"{notes_title}.txt", "Conection Type": "footnotes"})
        base_lines[i - 1] = mrk.sub(lambda m: marker_html(remap[int(m.group(1))]) if int(m.group(1)) in remap else "", ln)
    notes_lines: list[str] = []
    if kept_notes:
        notes_lines = [f"<h1>{notes_title}</h1>"]
        for n, body in enumerate(kept_notes, 1):
            notes_lines.append((f"<sup>{n}</sup> " if args.note_line_style == "sup" else f"{n} ") + body)
        check_merge_contract(base_lines, notes_lines, links, notes_title, rep)

    # --- כתיבה ---
    out.mkdir(parents=True, exist_ok=True)
    book_path = out / f"{file_name}.txt"
    book_path.write_text("\n".join(base_lines), encoding="utf-8", newline="\n")
    notes_path = links_path = None
    if notes_lines:
        notes_path = out / f"{notes_title}.txt"
        notes_path.write_text("\n".join(notes_lines), encoding="utf-8", newline="\n")
        (out / "links").mkdir(exist_ok=True)
        links_path = out / "links" / f"{file_name}_links.json"
        links_path.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    # --- בדיקות ---
    preservation_check(plan, base_lines, notes_lines, rep)
    scan_leftovers(base_lines, "ספר", rep)
    scan_leftovers(notes_lines, "הערות", rep)
    words = sum(len(HEB_RE.findall(re.sub(r"<[^>]*>", " ", l))) for l in base_lines[3:])
    ctx.update(lines=len(base_lines), notes=len(kept_notes), words=words)
    if full_words:
        chap_words = sum(p.words for p in plan if p.kind == "content")
        ratio = chap_words / full_words
        rep.coverage = {"מילים (wikitext מורחב) בדפי הפרקים שנבחרו": chap_words,
                        "מילים (wikitext גולמי) בדף הכול": full_words, "יחס": f"{ratio:.3f}",
                        "הערה": "אותה שיטת ספירה בשני הצדדים. פרק שאינו ב'הכול' (למשל נספחים) מעלה את היחס; פרק שחסר מוריד אותו. יחס רחוק מ-1 = לבדוק"}
        if not 0.9 <= ratio <= 1.1:
            rep.warnings.append(f"פער מילים מול דף הכול: יחס {ratio:.2f} (ייתכן שנספחים/פרקים אינם ב'הכול', או שפרק חסר)")
    rc = 0
    if not args.no_validate:
        rc = run_validators(repo, book_path, notes_path, links_path, rep)
    status = "נכתב"
    if rep.blocked:
        status = "נחסם (חלקי)"
    elif rc:
        status = "נכתב - הוולידטור מצא שגיאות"
    elif rep.red_links or rep.missing or rep.empty or rep.unmapped or rep.leftovers or rep.unresolved or rep.warnings:
        status = "נכתב - יש ממצאים לבדיקה (ראה דוח)"
    code = 3 if rep.blocked else (1 if rc else 0)
    return finish(code, status, ctx, file_name)


if __name__ == "__main__":
    sys.exit(main())
