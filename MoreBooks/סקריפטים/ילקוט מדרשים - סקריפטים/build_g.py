"""ילקוט מדרשים חלק ג: קובצי .doc (קובץ לכל מדרש) -> ספר לכל מדרש + ספר הערות נלווה.

הטקסט וסמני ההערות נקראים מה־.doc הבינארי (olefile), כי textutil מאבד את סמני
ההערות. העיצוב (מודגש, אותיות קטנות, יישור למרכז) נלקח מה־HTML של textutil,
ומיושר אל טקסט ה־.doc תו מול תו.

    python3 build_g.py SRC_DIR OUT_DIR
"""
import html as htmlmod
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

import olefile

from build import COPYRIGHT, HEADER_LINES

SUFFIX = ' (ילקוט מדרשים)'
SEP = '<div style="text-align: center;">%s</div>'

# (כותרת הספר, שורה 2, [(קובץ, {טקסט פסקה: תפקיד})])
# תפקיד: 'h2'/'h3' (אופציונלית 'h2:טקסט חדש'), 'drop', 'sub' (מצטרף לשורה הקודמת).
# פסקה ממורכזת שאינה ברשימה -> div ממורכז.
BOOKS = [
    ('מדרש הלל', '', [
        ('מדרש הלל', {'[מדרש הלל]': 'h2:מדרש הלל'})]),
    ('מנצפך צופים אמרום', 'אגדות מספר המעשים', [
        ('מנצפך צופים אמרום', {'אגדות מספר המעשים': 'h2:מנצפך צופים אמרום'})]),
    ('ענין חירם מלך צור', '', [
        ('ענין חירם מלך צור', {'ענין חירם מלך צור': 'h2'})]),
    ('אגדות מספר המעשים', '', [
        ('אגדות מספר המעשים', {'טעם אחר': 'h2'}),
        ('אגדות לספר המעשים המשך', {}),
        ('הוספה לספר המעשים מהלכות גדולות הקדמה',
         {'הוספה מהקדמת ספר הלכות גדולות': 'h2'})]),
    ('מדרש אל יתהלל', '', [
        ('מדרש אל יתהלל', {'מדרש אל יתהלל': 'h2'}),
        ('מדרש אל יתהלל נוסח ב', {'מדרש אל יתהלל (נוסח שני)': 'h2'}),
        ('הוספה למדרש אל יתהלל', {
            'הוספה למדרש אל יתהלל': 'h2',
            'מדרש גולית הפלשתי': 'h3',
            'ונקרא גם': 'alias',
            'מעשה דוד ואם גלית הפלשתי': 'sub',
            'מדרש גלות שלמה': 'h3',
            'זה המדרש משלמה המלך': 'h3',
            'הוספה ממדרש הגדת שיר השירים': 'h3',
            'הוספה ממדרש משלי': 'h3'})]),
    ('ענין כסא שלמה', '', [
        ('ענין כסא שלמה', {'ענין כסא שלמה': 'h2'}),
        ('הוספה לענין כסא שלמה', {'הוספה לענין כסא שלמה מספר סודי רזיא': 'h2'}),
        ('הוספה לכסא שלמה מתרגום שני לאסתר',
         {'הוספה למדרש אל יתהלל ולכסא שלמה מהתרגומים למגילת אסתר.':
          'h2:הוספה למדרש אל יתהלל ולכסא שלמה מהתרגומים למגילת אסתר'})]),
    ('דמות כסא שלמה', '', [
        ('דמות כסא שלמה', {'דמות כסא שלמה': 'h2'})]),
    ('מעשה משלמה המלך', '', [
        ('מעשה משלמה המלך', {'מעשה משלמה המלך': 'h2'})]),
    ('מעשה בשלמה המלך שהלך בגלות', '', [
        ('מעשה בשלמה המלך שהלך בגלות', {'מעשה בשלמה המלך': 'h2'})]),
    ('דרשא לעשר מכות', '', [
        ('דרשא לעשר מכות', {'דרשא לעשר מכות': 'h2'})]),
    ('דרשת רבי בנאה', '', [
        ('דרשת רבי בנאה', {'דרשת רבי בנאה': 'h2',
                           'נוסחא ראשונה.': 'h3:נוסחא ראשונה',
                           'נוסחא שנייה.': 'h3:נוסחא שנייה'})]),
    ('אגדת קרני ראמים', '', [
        ('אגדת קרני ראמים', {'אגדת קרני ראמים': 'h2', 'נוסח אחר': 'h2'})]),
    ('ליקוטים ממדרש מי השילוח', '', [
        ('ליקוטים ממדרש מי השילוח', {'ליקוטים ממדרש מי השילוח': 'h2'})]),
    ('מדרש הנסיעה', '', [
        ('מדרש הנסיעה', {'מדרש הנסיעה (להרי"ח)': 'h2'})]),
    ('פיטום הקטרת', '', [
        ('פיטום הקטרת', {'פיטום הקטרת': 'h2'})]),
    ('פירוש קדיש', '', [
        ('פירוש קדיש', {'פירוש קדיש': 'h2'})]),
    ('פרק חסידות', '', [
        ('פרק חסידות', {'פרק חסידות': 'h2'})]),
    ('פרק שירה', '', [
        ('פרק שירה', {'פרק שירה': 'h2'})]),
    ('ברייתא דמסכת נדה', '', [
        ('ברייתא דמסכת נדה', {
            'ברייתא דמסכת נדה (נוסחא ראשונה)': 'h2',
            'ברייתא דמסכת נדה (נוסחא שנייה) ודין יצירת הולד': 'h2'})]),
]

# קישוטי Wingdings בטווח הפרטי: זוג שמאל/ימין -> ☙ / ❧, כמו בחלקים א-ב
SYMBOLS = {'\uf09c': '☙', '\uf061': '☙', '\uf067': '☙',
           '\uf09d': '❧', '\uf062': '❧', '\uf068': '❧', '\uf020': ' '}


# ---------- .doc ----------
def load_doc(path):
    """טקסט ראשי, טקסט הערות, ומיקומי הסמנים."""
    ole = olefile.OleFileIO(path)
    wd = ole.openstream('WordDocument').read()
    flags = struct.unpack_from('<H', wd, 0x0A)[0]
    tbl = ole.openstream('1Table' if flags & 0x200 else '0Table').read()
    csw = struct.unpack_from('<H', wd, 32)[0]
    o = 34 + csw * 2
    cslw = struct.unpack_from('<H', wd, o)[0]
    lw = struct.unpack_from('<%di' % cslw, wd, o + 2)
    ccp_text, ccp_ftn = lw[3], lw[4]
    base = o + 2 + cslw * 4 + 2

    def fc(i):
        return struct.unpack_from('<II', wd, base + i * 8)
    fc_clx, lcb_clx = fc(33)
    fc_txt, lcb_txt = fc(3)
    clx = tbl[fc_clx:fc_clx + lcb_clx]
    i = 0
    while clx[i] == 1:
        i += 3 + struct.unpack_from('<H', clx, i + 1)[0]
    lcb = struct.unpack_from('<I', clx, i + 1)[0]
    plc = clx[i + 5:i + 5 + lcb]
    n = (lcb - 4) // 12
    cps = struct.unpack_from('<%dI' % (n + 1), plc, 0)
    parts = []
    for k in range(n):
        f = struct.unpack_from('<I', plc, 4 * (n + 1) + 8 * k + 2)[0]
        cnt = cps[k + 1] - cps[k]
        if f & 0x40000000:
            off = (f & 0x3FFFFFFF) // 2
            parts.append(wd[off:off + cnt].decode('cp1255', errors='replace'))
        else:
            parts.append(wd[f:f + cnt * 2].decode('utf-16le'))
    text = ''.join(parts)
    txtcps = struct.unpack_from('<%dI' % (lcb_txt // 4), tbl, fc_txt) if lcb_txt else ()
    main = text[:ccp_text]
    ftn = text[ccp_text:ccp_text + ccp_ftn]
    notes = [ftn[txtcps[k]:txtcps[k + 1]] for k in range(len(txtcps) - 2)]
    assert main.count('\x02') == len(notes), path
    return main, notes


# ---------- HTML של textutil ----------
class Paras(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paras, self.cur, self.stack = [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'p':
            self.cur = {'cls': a.get('class'), 'runs': []}
            self.stack = []
        elif self.cur is not None:
            self.stack.append((tag, a.get('class')))

    def handle_endtag(self, tag):
        if tag == 'p' and self.cur is not None:
            self.paras.append(self.cur)
            self.cur = None
        elif self.cur is not None and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.cur is not None:
            self.cur['runs'].append((data, [x for x in self.stack]))


def load_html(path):
    h = open(path, encoding='utf-8').read()
    pcss = dict(re.findall(r'p\.(p\d+) \{([^}]*)\}', h))
    scss = dict(re.findall(r'span\.(s\d+) \{([^}]*)\}', h))
    size = lambda css: float(re.search(r'font: ([\d.]+)px', css).group(1)) \
        if css and re.search(r'font: ([\d.]+)px', css) else None
    p = Paras()
    p.feed(h)
    out = []
    for para in p.paras:
        css = pcss.get(para['cls'], '')
        psize = size(css)
        chars = []          # (תו, מודגש, קטן)
        for data, stack in para['runs']:
            bold = any(t == 'b' for t, _ in stack)
            sz = psize
            for t, c in stack:
                if t == 'span' and c in scss and size(scss[c]):
                    sz = size(scss[c])
            small = psize is not None and sz is not None and sz <= psize - 2
            chars += [(ch, bold, small) for ch in data]
        out.append({'center': 'text-align: center' in css, 'size': psize, 'chars': chars})
    return out


def fmt(chars):
    """[(תו, b, small)] -> html, עם רווחים מחוץ לתגיות."""
    out, cur = [], (False, False)

    def close(st):
        return ('</small>' if st[1] else '') + ('</b>' if st[0] else '')

    def open_(st):
        return ('<b>' if st[0] else '') + ('<small>' if st[1] else '')
    i = 0
    while i < len(chars):
        ch, b, s = chars[i]
        if ch in ' ⁣' or ch == '\x02' or ch.startswith('<sup'):
            # רווח/סמן: יורשים את המצב הנוכחי אם הבא באותו מצב, אחרת סוגרים קודם
            j = i
            while j < len(chars) and (chars[j][0] == ' ' or chars[j][0].startswith('<sup')):
                j += 1
            nxt = (chars[j][1], chars[j][2]) if j < len(chars) else (False, False)
            if nxt != cur:
                out.append(close(cur))
                cur = (False, False)
            out += [c[0] for c in chars[i:j]]
            i = j
            continue
        if (b, s) != cur:
            out.append(close(cur) + open_((b, s)))
            cur = (b, s)
        out.append(ch)
        i += 1
    out.append(close(cur))
    return ''.join(out)


def norm(s):
    return re.sub(r'[\s\xa0\x02]+', '', s)


def merge_para(dpara, hpara, keep_small=True):
    """תווי ה־.doc (כולל \x02) + עיצוב ה־HTML -> רשימת (תו, b, small)."""
    hch = [c for c in hpara['chars'] if not c[0].isspace() and c[0] != '\xa0']
    out, j = [], 0
    for ch in dpara:
        if ch in '\x02\x0b':
            out.append((ch, False, False))
        elif ch.isspace() or ch == '\xa0':
            if out and out[-1][0] != ' ':
                out.append((' ', False, False))
        else:
            h = hch[j]
            assert h[0] == ch or h[0] in SYMBOLS or ch == '(' and h[0] in SYMBOLS, (ch, h[0])
            out.append((SYMBOLS.get(h[0], ch), h[1], h[2] and keep_small))
            j += 1
    assert j == len(hch), (j, len(hch), dpara[:60])
    while out and out[0][0] == ' ':
        out.pop(0)
    while out and out[-1][0] == ' ':
        out.pop()
    return out


def split_soft_breaks(chars):
    """שבירת־שורה רכה (\x0b): קטע של מילה אחת הוא מילת העמוד הבא (קטשווורד) ונמחק;
    קטע ארוך יותר (כמו 'פתשגן הכתב:') הופך לשורה נפרדת."""
    segs, cur = [], []
    for c in chars:
        if c[0] == '\x0b':
            segs.append(cur)
            cur = []
        else:
            cur.append(c)
    segs.append(cur)
    out = [segs[0]]
    for seg in segs[1:]:
        words = ''.join(c[0] for c in seg).split()
        if len(words) == 1 and '\x02' not in words[0]:
            continue
        out.append(seg)
    strip = lambda seg: seg[next((i for i, c in enumerate(seg) if c[0] != ' '), len(seg)):]
    out = [list(reversed(strip(list(reversed(strip(seg)))))) for seg in out]
    return [seg for seg in out if seg]


def is_separator(text):
    return bool(text.strip()) and not re.search(r'[א-ת\w]', re.sub(r'[\ue000-\uf8ff(]', '', text))


def convert_file(src_dir, name, roles, html_dir):
    """-> [(kind, payload)] ; kind: 'h2'/'h3'/'line'/'sub'; payload: [(תו,b,s)] או טקסט כותרת."""
    main, notes = load_doc(os.path.join(src_dir, name + '.doc'))
    hparas = load_html(os.path.join(html_dir, name + '.html'))
    dparas = main.split('\r')
    if dparas and dparas[-1] == '':
        dparas.pop()
    assert all(norm(d) == norm(''.join(c[0] for c in h['chars']))
               or is_separator(d) for d, h in zip(dparas, hparas)), name
    items = []
    used = set()
    for dp, hp in zip(dparas, hparas):
        if not norm(dp) and '\x02' not in dp:
            continue
        plain = re.sub(r'\s+', ' ', dp.replace('\x02', '')).strip()
        if is_separator(dp):
            sym = re.sub(r'\s+', ' ', ''.join(SYMBOLS.get(c[0], c[0]) for c in hp['chars'])
                         .replace('\xa0', ' ')).strip()
            if sym == '*' and items and items[-1][2] == 'sep' and items[-1][1] == '* *':
                sym = '* * *'          # משולש כוכבים שנפרס על שתי פסקאות
                items.pop()
            items.append(('line', sym, 'sep'))
            continue
        role = roles.get(plain)
        if role:
            used.add(plain)
        chars = merge_para(dp, hp, keep_small=not hp['center'])
        marks = [c for c in chars if c[0] == '\x02']
        if role == 'drop':
            assert not marks, (name, plain)
            continue
        if role and role.startswith('h'):
            lvl, _, new = role.partition(':')
            items.append((lvl, new or plain, marks))
            continue
        if role in ('alias', 'sub'):
            items.append((role, chars, None))
            continue
        for seg in split_soft_breaks(chars):
            items.append(('line', seg, 'center' if hp['center'] else None))
    # מילת פתיחה גדולה בפסקה משלה (drop-cap) -> מצטרפת לפסקה שאחריה
    merged = []
    for it in items:
        prev = merged[-1] if merged else None
        if (prev and prev[0] == 'line' and prev[2] is None and it[0] == 'line'
                and it[2] is None):
            body = [c for c in prev[1] if c[0] not in ('\x02', ' ')]
            if body and all(c[1] for c in body) and len(
                    ''.join(c[0] for c in prev[1] if c[0] != '\x02').split()) <= 3:
                merged[-1] = ('line', prev[1] + [(' ', False, False)] + it[1], None)
                continue
        merged.append(it)
    items = merged
    missing = set(roles) - used
    assert not missing, (name, missing)
    # עיצוב ההערות: פסקאות ה־HTML שאחרי הטקסט הראשי, לפי הסדר
    rest = hparas[len(dparas):]
    k = 0
    fnotes = []
    for raw in notes:
        out = []
        for para in raw.split('\r'):
            if not norm(para):
                continue
            while norm(''.join(c[0] for c in rest[k]['chars'])) != norm(para):
                k += 1
            chars = merge_para(para.replace('\x02', ''), rest[k], keep_small=False)
            k += 1
            out.append(fmt(chars))
        fnotes.append('<br>'.join(out))
    return items, fnotes


def render_chars(chars, notemap, counter):
    out = []
    for c in chars:
        if c[0] == '\x02':
            counter[0] += 1
            notemap.append(counter[0])
            out.append(('<sup>%d</sup>' % counter[0], c[1], c[2]))
        else:
            out.append(c)
    return fmt(out)


def note_html(raw):
    return raw


def build(src_dir, out_dir):
    html_dir = tempfile.mkdtemp()
    for f in os.listdir(src_dir):
        if f.endswith('.doc'):
            subprocess.run(['textutil', '-convert', 'html', '-output',
                            os.path.join(html_dir, f[:-4] + '.html'),
                            os.path.join(src_dir, f)], check=True, capture_output=True)
    folder = os.path.join(out_dir, 'חלק ג')
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.join(out_dir, 'links'), exist_ok=True)
    report = []
    for title, sub, files in BOOKS:
        btitle = title + SUFFIX
        ctitle = 'הערות במספרים על ' + btitle
        base = ['<h1>%s</h1>' % title, '<small>%s</small>' % sub if sub else '', COPYRIGHT]
        comp = []
        links = []
        counter = [0]
        pending = []          # סמנים מכותרת שיורדים לשורה הבאה
        heads = []            # שרשרת הכותרות הנוכחית, לשיקוף בספר ההערות
        comp_heads = []
        for fname, roles in files:
            items, notes = convert_file(src_dir, fname, roles, html_dir)
            ni = iter(notes)
            for kind, payload, extra in items:
                if kind in ('h2', 'h3'):
                    base.append('<%s>%s</%s>' % (kind, payload, kind))
                    heads = heads[:int(kind[1]) - 2] + [base[-1]]
                    pending += [next(ni) for _ in extra]
                    continue
                if kind == 'sub':
                    # "ונקרא גם" + השם: שורה ממורכזת אחת
                    base[-1] = SEP % (base[-1] + ' ' + fmt(payload))
                    continue
                if extra == 'sep':
                    base.append(SEP % payload)
                    continue
                nmarks = sum(1 for c in payload if c[0] == '\x02')
                line_notes = pending + [next(ni) for _ in range(nmarks)]
                payload = [('\x02', False, False)] * len(pending) + payload
                pending = []
                notemap = []
                text = render_chars(payload, notemap, counter)
                if extra == 'center':
                    text = SEP % text
                base.append(text)
                if notemap and comp_heads != heads:
                    i = 0
                    while i < min(len(heads), len(comp_heads)) and heads[i] == comp_heads[i]:
                        i += 1
                    comp += heads[i:]
                    comp_heads = list(heads)
                for n, raw in zip(notemap, line_notes):
                    comp.append('<sup>%d</sup> %s' % (n, note_html(raw)))
                    links.append((len(base), len(comp) + HEADER_LINES))
            assert next(ni, None) is None, (fname, 'notes left')
        assert not pending, title
        with open(os.path.join(folder, btitle + '.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(base) + '\n')
        if comp:
            with open(os.path.join(folder, ctitle + '.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(['<h1>%s</h1>' % ctitle, '', COPYRIGHT] + comp) + '\n')
            recs = [{'line_index_1': b, 'heRef_2': '%s %s' % (ctitle, re.match(
                r'<sup>(\d+)</sup>', open(os.path.join(folder, ctitle + '.txt'),
                                          encoding='utf-8').read().split('\n')[c - 1]).group(1)),
                     'path_2': ctitle + '.txt', 'line_index_2': c,
                     'Conection Type': 'footnotes'} for b, c in links]
            with open(os.path.join(out_dir, 'links', btitle + '_links.json'), 'w',
                      encoding='utf-8') as f:
                json.dump(recs, f, ensure_ascii=False, indent=1)
        report.append((title, len(base), counter[0]))
    for r in report:
        print('%-35s lines=%4d notes=%4d' % r)



if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
