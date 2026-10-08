#!/usr/bin/env python3
"""שלמי כהן (ציוני סוגיות על הש"ס, שלמה כהנוב): docx -> ספר + "הערות על" + links.

לכל אחת מ-15 המסכתות נוצרים שלושה קבצים:
  <out>/ספרים/אוצריא/תלמוד בבלי/מראי מקומות/שלמי כהן/שלמי כהן <מסכת>.txt
  <out>/ספרים/אוצריא/תלמוד בבלי/מראי מקומות/שלמי כהן/הערות על שלמי כהן <מסכת>.txt
  <out>/links/שלמי כהן <מסכת>_links.json     ("Conection Type": "footnotes")

המקור: קובצי ה-Word של המחבר, שבהם הערות השוליים הן הערות שוליים אמיתיות של Word.

--src חייב להכיל, כפי שהתקבל מהמחבר:
  שלמי כהן וורד/<תיקיית מסכת>/*.docx
(במאגר: extraBooks/שלמי כהן)

הרצה:
  python3 -I convert.py --src extraBooks/שלמי כהן --out <תיקיית בנייה> [--only מסכת ...]

`--src` חובה (ADDING_BOOKS.md סעיף 6): אין ברירת מחדל שיכולה לדרוס ספרים תקינים בפלט ישן.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SERIES = 'שלמי כהן'
AUTHOR = 'שלמה כהנוב'
CATEGORY = Path('ספרים/אוצריא/תלמוד בבלי/מראי מקומות/שלמי כהן')
BSD_LINE = '<small><b>בס"ד</b></small>'

# תיקיית המקור (תחת "שלמי כהן וורד") -> שם המסכת
TRACTATE_DIRS = {
    'שלמי כהן בב': 'בבא בתרא',
    'שלמי כהן במ': 'בבא מציעא',
    'שלמי כהן בק': 'בבא קמא',
    'שלמי כהן בכורות': 'בכורות',
    'שלמי כהן גיטין': 'גיטין',
    'יבמות': 'יבמות',
    'שלמי כהן כריתות': 'כריתות',
    'כתובות': 'כתובות',
    'שלמי כהן מכות': 'מכות',
    'שלמי כהן נדרים': 'נדרים',
    'שלמי כהן סוכה': 'סוכה',
    'שלמי כהן ערכין': 'ערכין',
    'שלמי כהן פסחים': 'פסחים',
    'שלמי כהן קידושין': 'קידושין',
    'שלמי כהן תמורה': 'תמורה',
}
ALL_TRACTATES = list(TRACTATE_DIRS.items())
# מסכת שיש לה קובץ מלא חדש יותר שמחליף את חלקי הביניים
FULL_FILE = {'יבמות': 'יבמות שלמי כהן.docx'}

# תפקיד הפסקה לפי *שם* הסגנון ב-styles.xml (מזהי הסגנון משתנים בין הקבצים: 3 / 31 ...)
ROLE_BY_STYLE_NAME = {
    'heading 1': 'chapter',
    'heading 2': 'topic',
    'heading 3': 'daf',
    'נושא': 'cover',
    'קטן': 'small',
    'צ': 'small',
}
HEADING_LEVEL = {'chapter': 2, 'daf': 3, 'topic': 4}   # h1 = שם הספר
SMALL_HALF_PT = 20                                     # 10pt ומטה = קטן

TAG = re.compile(r'<(/?)([a-zA-Z0-9]+)[^>]*>')
BIDI = re.compile('[\\u200e\\u200f\\u202a-\\u202e\\u2066-\\u2069]')
# שורת כריכה שחוזרת בראש כל קובץ-חלק: 'בס"ד' לבד, או 'בס"ד' + כותרת החלק
COVER_RE = re.compile(r'^בס"ד(\s+(שלמי כהן|כריתות|יבמות|תמורה)\b.*)?$')
COVER_MAX = 160


class ConvertError(Exception):
    pass


# ---------------------------------------------------------------- gematria
_G = dict(zip('אבגדהוזחטיכלמנסעפצקרשת',
              [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))
_G.update({'ך': 20, 'ם': 40, 'ן': 50, 'ף': 80, 'ץ': 90})


def gematria(n: int) -> str:
    """132 -> 'קלב' (15/16 כ'טו'/'טז' בלי גרשיים; מספיק לדפי הש"ס)."""
    out = ''
    for v, c in ((400, 'ת'), (300, 'ש'), (200, 'ר'), (100, 'ק')):
        while n >= v:
            out += c
            n -= v
    if n in (15, 16):
        return out + ('טו' if n == 15 else 'טז')
    for v, c in ((90, 'צ'), (80, 'פ'), (70, 'ע'), (60, 'ס'), (50, 'נ'), (40, 'מ'), (30, 'ל'), (20, 'כ'), (10, 'י')):
        if n >= v:
            out += c
            n -= v
    out += 'אבגדהוזחט'[n - 1] if n else ''
    return out


def daf_key(text: str):
    """'דף קיד:' -> (114, 1); None אם אינו כותרת דף."""
    m = re.match(r'^\s*דף\s+([א-ת"׳\']+)\s*([.:])\s*$', text)
    if not m:
        return None
    return (sum(_G.get(c, 0) for c in m.group(1)), 1 if m.group(2) == ':' else 0)


def fix_daf_labels(name, items):
    """תווית דף בלי . או : ('דף יז', או '7'): הצד נגזר מכותרת הדף התקינה הבאה.
    הבאה היא (n,:) -> התווית היא n. ; הבאה היא (n+1,.) -> התווית היא n: ."""
    for i, (role, parts, plain) in enumerate(items):
        if role != 'daf' or daf_key(plain):
            continue
        m = re.match(r'^דף\s+([א-ת"׳\']+)$', plain)
        nxt = next((daf_key(x[2]) for x in items[i + 1:] if x[0] == 'daf' and daf_key(x[2])), None)
        n = sum(_G.get(c, 0) for c in m.group(1)) if m else (nxt[0] if nxt and nxt[1] == 1 else None)
        if n is None or nxt is None:
            raise ConvertError(f'{name}: כותרת דף בלתי-תקינה {plain!r} שאי אפשר לשחזר')
        if nxt == (n, 1):
            side = '.'
        elif nxt == (n + 1, 0):
            side = ':'
        else:
            raise ConvertError(f'{name}: תווית דף {plain!r} אינה עקבית עם הכותרת הבאה {nxt}')
        fixed = f'דף {gematria(n)}{side}'
        items[i] = (role, [('t', fixed, False)] + [p for p in parts if p[0] == 'fn'], fixed)


# ---------------------------------------------------------------- docx
def _flag(rp, tag):
    if rp is None:
        return False
    e = rp.find(W + tag)
    return e is not None and e.get(W + 'val') not in ('0', 'false', 'none')


def _clean(text: str) -> str:
    return BIDI.sub('', text).replace('\xa0', ' ')


def _wrap(text, fmt):
    b, i, u, sub = fmt
    if b:
        text = f'<b>{text}</b>'
    if i:
        text = f'<i>{text}</i>'
    if u:
        text = f'<u>{text}</u>'
    if sub:
        text = f'<sub>{text}</sub>'
    return text


def _render(chunk, strip_left=True, strip_right=True):
    """chunk = [(text, fmt)] רצוף וללא הערות -> HTML. ריצות סמוכות באותו עיצוב מתמזגות.
    רווחי קצה נמחקים רק בקצה הפסקה; סביב סמן הערה ובגבול <small> הם נשמרים כפי שהם במקור."""
    merged = []
    for text, fmt in chunk:
        text = _clean(text)
        if merged and merged[-1][1] == fmt:
            merged[-1][0] += text
        else:
            merged.append([text, fmt])
    if not merged:
        return ''
    if strip_left:
        merged[0][0] = merged[0][0].lstrip()
    if strip_right:
        merged[-1][0] = merged[-1][0].rstrip()
    html = ''.join(_wrap(t, f) for t, f in merged if t)
    return re.sub(r'\s+', ' ', html)


def _size_el(rp):
    """גודל הגופן של ריצה/סגנון: szCs קודם. הטקסט עברי (rtl), ו-Word מציג אותו לפי szCs; sz חל על
    טקסט לטיני בלבד. ברוב הקטעים המוקטנים במקור (בכל המסכתות) יש szCs=20 בלי sz כלל."""
    if rp is None:
        return None
    el = rp.find(W + 'szCs')
    return el if el is not None else rp.find(W + 'sz')


class Docx:
    """פסקאות המסמך: [(role, parts, plain)], parts = [('t', html, small) | ('fn', id)]."""

    def __init__(self, path: Path):
        self.path = path
        self.name = path.name
        z = zipfile.ZipFile(path)
        self.styles = self._styles(ET.fromstring(z.read('word/styles.xml')))
        doc = ET.fromstring(z.read('word/document.xml'))
        body = doc.find(W + 'body')
        if body.find('.//' + W + 'tbl') is not None:
            raise ConvertError(f'{self.name}: טבלה במסמך - לא נתמך')
        self.footnotes = self._footnotes(ET.fromstring(z.read('word/footnotes.xml')))
        self.items = []
        for p in body.iter(W + 'p'):
            it = self._paragraph(p)
            if it:
                self.items.append(it)
        self.junk_tail = self._strip_junk_tail()
        self._fix_daf_labels()

    def _strip_junk_tail(self):
        """שברי תווים בסוף הקובץ (אחרי 'הדרן'): ע / ס. / נן / ם. / [\\. / \\ ... באורך <=6, הערות של עד 3 תווים."""
        removed = []
        while self.items:
            role, parts, plain = self.items[-1]
            fns = [self.footnotes.get(p[1], '') for p in parts if p[0] == 'fn']
            if len(plain) <= 6 and all(len(re.sub(r'<[^>]+>', '', f)) <= 3 for f in fns):
                removed.append((role, plain))
                self.items.pop()
            else:
                break
        return removed

    def _fix_daf_labels(self):
        fix_daf_labels(self.name, self.items)

    # -- סגנונות
    @staticmethod
    def _styles(root):
        out = {}
        for s in root.iter(W + 'style'):
            if s.get(W + 'type') != 'paragraph':
                continue
            nm = s.find(W + 'name')
            sz = _size_el(s.find(W + 'rPr'))
            bo = s.find(W + 'basedOn')
            out[s.get(W + 'styleId')] = (nm.get(W + 'val') if nm is not None else '',
                                         int(sz.get(W + 'val')) if sz is not None else None,
                                         bo.get(W + 'val') if bo is not None else None)
        return out

    def _style_size(self, sid):
        seen = set()
        while sid and sid not in seen:
            seen.add(sid)
            _, sz, bo = self.styles.get(sid, ('', None, None))
            if sz:
                return sz
            sid = bo
        return None

    # -- ריצות
    def _runs(self, p, base_sz, keep_size):
        """[('t', text, (b,i,u,sub), small)] ו-('fn', id) בסדר המסמך."""
        segs = []
        for ch in p:
            if ch.tag != W + 'r':
                if ch.tag in (W + 'pPr', W + 'bookmarkStart', W + 'bookmarkEnd', W + 'proofErr'):
                    continue
                if ch.find('.//' + W + 'r') is not None:
                    raise ConvertError(f'{self.name}: ריצות מתחת ל-{ch.tag}')
                continue
            rp = ch.find(W + 'rPr')
            szel = _size_el(rp)
            sz = int(szel.get(W + 'val')) if szel is not None else base_sz
            va = rp.find(W + 'vertAlign') if rp is not None else None
            fmt = (_flag(rp, 'b'), _flag(rp, 'i'), _flag(rp, 'u'),
                   va is not None and va.get(W + 'val') == 'subscript')
            if va is not None and va.get(W + 'val') == 'superscript':
                raise ConvertError(f'{self.name}: superscript מפורש בגוף הטקסט')
            small = keep_size and sz <= SMALL_HALF_PT
            buf = []
            for el in ch:
                if el.tag == W + 't':
                    buf.append(el.text or '')
                elif el.tag in (W + 'tab', W + 'br', W + 'ptab', W + 'cr'):
                    buf.append(' ')
                elif el.tag == W + 'noBreakHyphen':
                    buf.append('-')
                elif el.tag == W + 'footnoteReference':
                    if buf:
                        segs.append(('t', ''.join(buf), fmt, small))
                        buf = []
                    segs.append(('fn', el.get(W + 'id')))
                elif el.tag in (W + 'rPr', W + 'lastRenderedPageBreak', W + 'footnoteRef',
                                W + 'separator', W + 'continuationSeparator'):
                    pass
                else:
                    raise ConvertError(f'{self.name}: רכיב לא מוכר בריצה: {el.tag}')
            if buf:
                segs.append(('t', ''.join(buf), fmt, small))
        return segs

    @staticmethod
    def _parts(segs):
        """ממזג מקטעים רצופים (לפי small) ל-parts = [('t', html, small) | ('fn', id)]."""
        # ריצה של רווחים בלבד אינה מפרידה בין מקטעים: היא מצטרפת לטקסט שלפניה, ואם לפניה סמן הערה - לטקסט שאחריה
        segs = list(segs)
        for i, sg in enumerate(segs):
            if sg[0] == 't' and not sg[1].strip():
                before = segs[i - 1] if i else None
                if before is not None and before[0] == 't':
                    nb = before
                else:
                    nb = next((x for x in segs[i + 1:] if x[0] == 't' and x[1].strip()), before)
                if nb is not None and nb[0] == 't':
                    segs[i] = (sg[0], sg[1], sg[2], nb[3])
        groups = []   # ('t', [(text, fmt)], small) | ('fn', id)
        for s in segs:
            if s[0] == 'fn':
                groups.append(('fn', s[1]))
                continue
            _, text, fmt, small = s
            if groups and groups[-1][0] == 't' and groups[-1][2] == small:
                groups[-1][1].append((text, fmt))
            else:
                groups.append(('t', [(text, fmt)], small))
        parts = []
        for i, g in enumerate(groups):
            if g[0] == 'fn':
                parts.append(g)
                continue
            first = i == 0
            nxt = groups[i + 1] if i + 1 < len(groups) else None
            html = _render(g[1], strip_left=first, strip_right=nxt is None)
            if html:
                parts.append(('t', html, g[2]))
        return parts

    def _footnotes(self, root):
        out = {}
        for f in root:
            if f.get(W + 'type') in ('separator', 'continuationSeparator'):
                continue
            paras = []
            for p in f.iter(W + 'p'):
                # בהערות: נטייה כ-<em> (<i> אסור בספר הערות שמתמזג), ללא תגי גודל
                segs = [s for s in self._runs(p, 24, keep_size=False) if s[0] == 't']
                html = _to_em(segs)
                if html:
                    paras.append(html)
            out[f.get(W + 'id')] = '<br>'.join(paras)
        return out

    def _paragraph(self, p):
        ps = p.find(W + 'pPr/' + W + 'pStyle')
        sid = ps.get(W + 'val') if ps is not None else None
        name = self.styles.get(sid, ('', None, None))[0] if sid else ''
        role = ROLE_BY_STYLE_NAME.get(name, 'normal')
        style_sz = self._style_size(sid) or 24
        base_sz = SMALL_HALF_PT if role == 'small' else (style_sz if role == 'normal' else 24)
        is_heading = role in HEADING_LEVEL
        segs = self._runs(p, base_sz, keep_size=not is_heading)
        plain = re.sub(r'\s+', ' ', _clean(''.join(s[1] for s in segs if s[0] == 't'))).strip()
        has_ref = any(s[0] == 'fn' for s in segs)
        if not plain and not has_ref:
            return None
        if COVER_RE.match(plain):
            if len(plain) > COVER_MAX:
                raise ConvertError(f'{self.name}: פסקת כריכה ארוכה: {plain[:60]}')
            return ('cover', [], plain)
        if role == 'cover':
            # הסגנון "נושא" משמש גם לכותרות נושא רגילות (למשל 'סתמא לאו לשמה')
            role = 'topic'
            is_heading = True
        if is_heading:
            # כותרת: ללא עיצוב (מודגשת ממילא), למעט subscript
            segs = [(s[0], s[1], (False, False, False, s[2][3]), False) if s[0] == 't' else s for s in segs]
        return (role, self._parts(segs), plain)


def _to_em(segs):
    """פסקת הערה: <b>, <u>, <em> (במקום <i>)."""
    chunk = [(s[1], s[2]) for s in segs]
    merged = []
    for text, fmt in chunk:
        text = _clean(text)
        if merged and merged[-1][1] == fmt:
            merged[-1][0] += text
        else:
            merged.append([text, fmt])
    if not merged:
        return ''
    merged[0][0] = merged[0][0].lstrip()
    merged[-1][0] = merged[-1][0].rstrip()
    out = []
    for t, (b, i, u, sub) in merged:
        if not t:
            continue
        if b:
            t = f'<b>{t}</b>'
        if i:
            t = f'<em>{t}</em>'
        if u:
            t = f'<u>{t}</u>'
        if sub:
            t = f'<sub>{t}</sub>'
        out.append(t)
    return re.sub(r'\s+', ' ', ''.join(out))


# ---------------------------------------------------------------- איחוי הקבצים
def doc_start_key(doc: Docx):
    for role, _parts, plain in doc.items:
        if role == 'daf':
            k = daf_key(plain)
            if k:
                return k
    raise ConvertError(f'{doc.name}: אין כותרת דף')


def successor(k):
    """הדף העוקב: (n,0)->(n,1)->(n+1,0)."""
    return (k[0], 1) if k[1] == 0 else (k[0] + 1, 0)


def check_daf_sequence(stream, log):
    """חוסרים אמיתיים במקור -> התראה. כפילות כותרת-דף אחרי 'הדרן'/פרק חדש היא מבנה המחבר (פרק שנפתח באמצע דף)."""
    last, between = None, []
    for x in stream:
        if x[0] != 'daf':
            if x[0] == 'chapter' or x[2].startswith('הדרן'):   # 'הדרן' מופיע גם כנושא וגם כפסקה קטנה
                between.append(x[0])
            continue
        k = daf_key(x[2])
        if last is not None and k != successor(last):
            lab = f'{gematria(last[0])}{":" if last[1] else "."}'
            if k == last:
                if not between:
                    log(f'  !! כותרת דף כפולה בלי גבול פרק: {x[2]}')
            else:
                log(f'  !! חסר במקור: אחרי דף {lab} בא {x[2]}')
        last, between = k, []


def merge_docs(docs, log):
    """קבצי-חלקים חופפים בגבולות -> זרם אחד. מוחק כותרת-דף כפולה בחיבור, וחלק כפול שהוא רישא של חברו."""
    seen, uniq = {}, []
    for d in docs:
        sig = tuple((r, t) for r, _p, t in d.items)
        if sig in seen:
            log(f'  דילוג על עותק זהה: {d.name} (= {seen[sig]})')
            continue
        seen[sig] = d.name
        uniq.append(d)
    uniq.sort(key=doc_start_key)
    stream = []
    for d in uniq:
        items = [(r, p, t, d) for r, p, t in d.items if r != 'cover']
        first = next((i for i, x in enumerate(items) if x[0] == 'daf'), None)
        last_a = max((i for i, x in enumerate(stream) if x[0] == 'daf'), default=None)
        if first is not None and last_a is not None:
            ka, kb = daf_key(stream[last_a][2]), daf_key(items[first][2])
            if kb < ka:
                # כותרת פתיחה שגויה בקובץ-חלק (בקידושין: 'דף כא:' במקום 'דף כב:'): תקינה אם הבאה אחריה היא העוקבת
                nb = next((daf_key(x[2]) for x in items[first + 1:] if x[0] == 'daf' and daf_key(x[2])), None)
                if nb != successor(ka):
                    raise ConvertError(f'{d.name}: סדר דפים הפוך: {items[first][2]} אחרי {stream[last_a][2]}')
                log(f'  תיקון כותרת פתיחה ב-{d.name}: {items[first][2]} -> {stream[last_a][2]}')
                items[first] = ('daf', [('t', stream[last_a][2], False)], stream[last_a][2], d)
                kb = ka
            if kb == ka:
                end = next((i for i in range(first + 1, len(items)) if items[i][0] == 'daf'), len(items))
                sec_a = [x[2] for x in stream[last_a + 1:]]
                sec_b = [x[2] for x in items[first + 1:end]]
                if sec_a and sec_b[:len(sec_a)] == sec_a:
                    log(f'  חפיפה ב-{items[first][2]}: מחיקת רישא כפולה ({len(sec_a)} פריטים) מהחלק הקודם')
                    del stream[last_a + 1:]
                elif sec_b and sec_a[:len(sec_b)] == sec_b:
                    log(f'  חפיפה ב-{items[first][2]}: מחיקת רישא כפולה ({len(sec_b)} פריטים) מ-{d.name}')
                    del items[first + 1:end]
                elif first + 1 < len(items) and items[first + 1][0] == 'chapter':
                    # 'דף X' ומיד פרק חדש: הפרק הקודם נגמר באמצע דף X והחדש נפתח בו - מבנה המחבר, הכותרת נשארת
                    log(f'  חיבור ב-{items[first][2]}: פרק חדש באמצע הדף, כותרת הדף נשמרת')
                    stream.extend(items)
                    continue
                else:
                    log(f'  חיבור ב-{items[first][2]}: {len(sec_a)} פריטים + {len(sec_b)} (ללא חפיפה)')
                del items[first]
        stream.extend(items)
    check_daf_sequence(stream, log)
    return stream


# ---------------------------------------------------------------- בניית הספר
class Book:
    def __init__(self):
        self.lines = []      # גוף הספר
        self.notes = []      # שורות ספר ההערות
        self.links = []      # (שורה בספר, שורת הערה)
        self.dropped_empty_notes = 0
        self.level_jumps = []


def build_book(name, docs, log):
    stream = merge_docs(docs, log)

    # כותרת-פרק שהיא המילה 'פרק' לבדה ואחריה מיד כותרת-פרק מלאה (אולי אחרי כותרת דף): שבר כפול של הכותרת
    for i in range(len(stream) - 1, -1, -1):
        j = next((k for k in range(i + 1, len(stream)) if stream[k][0] != 'daf'), None)
        if stream[i][0] == 'chapter' and stream[i][2] == 'פרק' and j is not None \
                and stream[j][0] == 'chapter' and stream[j][2].startswith('פרק '):
            log(f'  מחיקת כותרת פרק שבורה: {stream[i][2]!r} לפני {stream[j][2]!r}')
            del stream[i]

    # כותרת-דף שאחריה מיד כותרת-פרק: הפרק פותח את הדף, ולכן הוא קודם לו בהיררכיה
    for i in range(len(stream) - 1):
        if stream[i][0] == 'daf' and stream[i + 1][0] == 'chapter':
            stream[i], stream[i + 1] = stream[i + 1], stream[i]

    # הערה שמסומנת בכותרת עוברת לתחילת הפסקה הבאה (קישור לשורת כותרת אסור)
    is_body = [x[0] in ('normal', 'small') for x in stream]
    carry = {}
    for i, x in enumerate(stream):
        if x[0] in HEADING_LEVEL:
            refs = [p for p in x[1] if p[0] == 'fn']
            if refs:
                j = next((k for k in range(i + 1, len(stream)) if is_body[k]), None)
                if j is None:
                    j = max(k for k in range(i) if is_body[k])
                carry.setdefault(j, []).extend((r[1], x[3]) for r in refs)

    book = Book()
    book.lines = [f'<h1>{SERIES} {name}</h1>', AUTHOR, BSD_LINE]

    def marker(fnid, doc):
        body = doc.footnotes.get(fnid, '')
        if not body.strip():
            book.dropped_empty_notes += 1
            return ''
        n = len(book.notes) + 1
        book.notes.append(f'<sup>{n}</sup> {body}')
        book.links.append((len(book.lines) + 1, n))
        return f'<sup>{n}</sup>'

    prev_level, have_daf = 1, False
    for i, (role, parts, plain, doc) in enumerate(stream):
        if role in HEADING_LEVEL:
            html = ''.join(p[1] for p in parts if p[0] == 't').strip()
            if not html:
                continue
            lvl = HEADING_LEVEL[role]
            if role == 'chapter':
                have_daf = False
            elif role == 'daf':
                have_daf = True
            elif not have_daf:
                lvl = 3          # נושא בפרק שעוד לא נפתחה בו כותרת דף: ישירות תחת הפרק (בלי דילוג רמה)
            if lvl > prev_level + 1:
                book.level_jumps.append((len(book.lines) + 1, f'h{prev_level}->h{lvl}', plain[:30]))
            prev_level = lvl
            book.lines.append(f'<h{lvl}>{html}</h{lvl}>')
            continue
        out = []
        for fnid, fdoc in carry.get(i, []):
            out.append(marker(fnid, fdoc))
        for p in parts:
            if p[0] == 'fn':
                out.append(marker(p[1], doc))
            elif p[2]:
                out.append(f'<small>{p[1]}</small>')
            else:
                out.append(p[1])
        line = ''.join(out)
        if line.strip():
            book.lines.append(line)
    return book


# ---------------------------------------------------------------- בדיקות פנימיות
def balanced(line):
    st = []
    for m in TAG.finditer(line):
        n = m.group(2).lower()
        if n == 'br':
            continue
        if m.group(1):
            if not st or st.pop() != n:
                return False
        else:
            st.append(n)
    return not st


def check_book(name, book):
    errs = []
    for i, l in enumerate(book.lines, 1):
        if not l.strip():
            errs.append(f'שורה ריקה בספר: {i}')
        if not balanced(l):
            errs.append(f'שורה לא מאוזנת בספר: {i}: {l[:60]}')
        if '\t' in l or '\ufeff' in l or '\r' in l:
            errs.append(f'תו אסור בשורה {i}')
    for i, l in enumerate(book.notes, 1):
        if not l.startswith(f'<sup>{i}</sup> '):
            errs.append(f'הערה {i} לא מתחילה בסמן שלה')
        if re.search(r'</?i[ >]', l):
            errs.append(f'<i> בהערה {i}')
        if not balanced(l):
            errs.append(f'שורה לא מאוזנת בהערות: {i}')
        if '\t' in l or '\ufeff' in l or '\r' in l:
            errs.append(f'תו אסור בהערה {i}')
        if re.match(r'^<h[1-6]', l):
            errs.append(f'הערה {i} היא כותרת')
    # כל הערה מקושרת בדיוק פעם, וכל סמן בגוף תואם את ההערה המקושרת אליו
    linked = [b for _a, b in book.links]
    if sorted(linked) != list(range(1, len(book.notes) + 1)):
        errs.append('לא כל ההערות מקושרות בדיוק פעם')
    for a, b in book.links:
        if f'<sup>{b}</sup>' not in book.lines[a - 1]:
            errs.append(f'קישור {a}->{b}: אין סמן בשורה')
        if re.match(r'^<h[1-6]', book.lines[a - 1]):
            errs.append(f'קישור לשורת כותרת: {a}')
    return errs


# ---------------------------------------------------------------- כתיבה
def links_json(base_title, notes_title, book):
    rows = [{'line_index_1': a, 'heRef_2': 'הערות', 'path_2': notes_title + '.txt',
             'line_index_2': b, 'Conection Type': 'footnotes'} for a, b in book.links]
    return json.dumps(rows, ensure_ascii=False, indent=2) + '\n'


def write_book(out_root: Path, name, book):
    title = f'{SERIES} {name}'
    notes_title = f'הערות על {title}'
    d = out_root / CATEGORY
    d.mkdir(parents=True, exist_ok=True)
    (out_root / 'links').mkdir(parents=True, exist_ok=True)
    (d / f'{title}.txt').write_bytes(('\n'.join(book.lines) + '\n').encode('utf-8'))
    (d / f'{notes_title}.txt').write_bytes(('\n'.join(book.notes) + '\n').encode('utf-8'))
    (out_root / 'links' / f'{title}_links.json').write_bytes(links_json(title, notes_title, book).encode('utf-8'))


def tractate_docs(src: Path, dirname, name):
    d = src / 'שלמי כהן וורד' / dirname
    files = sorted(d.glob('*.docx'))
    if name in FULL_FILE:
        files = [f for f in files if f.name == FULL_FILE[name]]
        if len(files) != 1:
            raise ConvertError(f'{name}: הקובץ המלא {FULL_FILE[name]} לא נמצא')
    if not files:
        raise ConvertError(f'{name}: אין docx בתיקייה {d}')
    return [Docx(f) for f in files]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', required=True, type=Path, help='תיקיית "שלמי כהן" שהתקבלה (חובה)')
    ap.add_argument('--out', required=True, type=Path, help='שורש MoreBooks (ספרים/ ו-links/ נכתבים תחתיו)')
    ap.add_argument('--only', nargs='*', help='מסכתות לעבד (ברירת מחדל: כולן)')
    args = ap.parse_args(argv)
    bad = 0
    for dirname, name in ALL_TRACTATES:
        if args.only and name not in args.only:
            continue
        print(f'== {name}')
        docs = tractate_docs(args.src, dirname, name)
        for d in docs:
            if d.junk_tail:
                print(f'  זבל בסוף {d.name}: {d.junk_tail}')
        book = build_book(name, docs, lambda s: print(s))
        errs = check_book(name, book)
        h = {lv: sum(1 for l in book.lines if l.startswith(f'<h{lv}>')) for lv in (2, 3, 4)}
        print(f'  קבצים: {len(docs)} | שורות: {len(book.lines)} | הערות: {len(book.notes)} | '
              f'כותרות h2/h3/h4: {h[2]}/{h[3]}/{h[4]} | הערות ריקות שהושמטו: {book.dropped_empty_notes}')
        if book.level_jumps:
            print(f'  דילוגי רמה: {book.level_jumps[:6]} (סה"כ {len(book.level_jumps)})')
        for e in errs[:10]:
            print('  שגיאה:', e)
        bad += len(errs)
        if not errs:
            write_book(args.out, name, book)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
