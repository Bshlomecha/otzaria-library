"""Split the two Yalkut Midrashim volumes into one book per midrash, with each
note series moved to its own standalone companion book (footnotes links).

Usage: python3 build.py OUT_DIR
Prints only counts and ASCII-masked structure.
"""
import json
import os
import re
import sys

from common import SRC, gem, mask

SUFFIX = ' (ילקוט מדרשים)'
FOLDER = {'A': 'חלק א', 'B': 'חלק ב'}
SERIES_NAME = {'dig': 'הערות במספרים על ',
               'heb': 'הערות באותיות על ',
               'ast': 'שינויי נוסחאות על '}
SERIES_ORDER = ['dig', 'heb', 'ast']

# (title, subtitle, [(first, last, level_shift), ...], extra)
# line numbers are 1-based and inclusive, in the source volume
SPEC = {
    'A': [
        ('מדרש חופת אליהו', 'או פרקי רבינו הקדוש',
         [(69, 176, 1), (178, 915, 1), (1085, 1180, 0)], {}),
        ('מאמר ארבעה מלכים', None, [(917, 957, 1)], {}),
        ('סדר ארקים', 'או סידור של מדות טובות', [(959, 989, 1)], {}),
        ('פרק אדם הראשון', None, [(991, 1016, 1)], {}),
        ('ברייתא דישועה', None, [(1018, 1059, 1)], {}),
        ('מדרש חמש עשרה נקודות שבמקרא', None, [(1061, 1079, 1)], {}),
        ('טעם ארבע תקופות', None, [(1081, 1084, 1)], {}),
    ],
    'B': [
        ('מדרש תדשא', 'או ברייתא דרבי פינחס בן יאיר',
         [(50, 51, 0), (55, 203, 1), (1066, 1143, 1)],
         {'intro_note': (53, 54, 'dig')}),
        ('מדרש תמורה', 'ונקרא גם מסכת תמורה', [(205, 312, 1)], {}),
        ('מדרש עשרת מלכים', None, [(314, 356, 1), (1144, 1170, 1)], {}),
        ('פרק ארחות תושיה', 'והם שלשים ושתים נתיבות חכמה',
         [(358, 397, 1)], {}),
        ('טעם שבע נקודות של שבעה מלכים', None, [(399, 411, 1)], {}),
        ('סדר יצירת הולד', None, [(413, 443, 1), (1171, 1186, 1)], {}),
        ('ברייתא ברייתו של עולם', 'אגדת עולם קטן',
         [(445, 455, 1), (1187, 1201, 1)], {}),
        ('פרק צדקות', None, [(457, 490, 1), (1202, 1207, 1)], {}),
        ('מדרש חסד לאומים', None, [(492, 494, 1)], {}),
        ('פרקי רבי יוסי', None, [(496, 515, 1)], {}),
        ('עשרה מילי דחסידותא', 'דהוה נהיג בהון רב', [(517, 531, 1)], {}),
        ('ספר אורחות חיים', None, [(533, 616, 1), (1208, 1222, 1)],
         {'renumber_heb': (533, 616), 'sub_from_line': 532}),
        ('סדר גן עדן', None, [(618, 678, 1), (1223, 1274, 1)], {}),
        ('מסכת גן עדן', None, [(680, 702, 1)], {}),
        ('מעשה דרבי יהושע בן לוי', None, [(704, 782, 1)], {}),
        ('פרק גן החיים', None, [(784, 790, 1)], {}),
        ('מסכת שמחות זוטרתי דרבי חייא', None, [(792, 833, 1)], {}),
        ('פרק מעשה המת', 'ונקרא גם סדר רחיצה להלל הזקן',
         [(835, 858, 1)], {}),
        ('פרקי חיבוט הקבר', None, [(860, 1037, 1), (1275, 1278, 1)], {}),
        ('ברייתא של עשרים וארבעה דברים', None, [(1039, 1064, 1)], {}),
    ],
}
# source lines deliberately not carried into any book
DROPPED = {
    # title page + פתיחה; each midrash's <h2> becomes its book's <h1>
    'A': set(range(2, 69)) | {177, 916, 958, 990, 1017, 1060, 1080},
    'B': (set(range(2, 50)) | {52, 204, 313, 357, 398, 412, 444, 456, 491,
                               495, 516, 532, 617, 679, 703, 783, 791, 834,
                               859, 1038, 1065}),
}

NOTE_RE = re.compile(
    r'<sup class="footnote-marker">(.*?)</sup><i class="footnote">(.*?)</i>')
HEAD_RE = re.compile(r'^<h(\d)>(.*)</h\d>$')
SMALL_TAIL = re.compile(r'^(.*?)\s*<small>(.*)</small>\s*$')

ONES = 'אבגדהוזחט'
TENS = 'יכלמנסעפצ'
HUND = 'קרשת'


def heb_num(n):
    out = ''
    while n >= 400:
        out += 'ת'
        n -= 400
    if n >= 100:
        out += HUND[n // 100 - 1]
        n %= 100
    if n in (15, 16):
        return out + ('טו' if n == 15 else 'טז')
    if n >= 10:
        out += TENS[n // 10 - 1]
        n %= 10
    if n:
        out += ONES[n - 1]
    return out


def series_of(mark, vol):
    if re.fullmatch(r'\d+', mark):
        return 'dig'
    if vol == 'A' and mark == '*':
        return 'ast'
    # in part B '*' and 'ה*' are supplements inside the letter series
    return 'heb'


def split_heading(level, text):
    """-> (heading_text, subtitle_or_None)"""
    m = SMALL_TAIL.match(text)
    if m:
        text, sub = m.group(1), m.group(2)
    else:
        sub = None
    text = text.strip()
    if text.endswith('.'):
        text = text[:-1].rstrip()
    return text, sub


def build(out_dir):
    report = []
    os.makedirs(os.path.join(out_dir, 'links'), exist_ok=True)
    for vol, specs in SPEC.items():
        name = [x for x in os.listdir(SRC)
                if len(x) > 9 and x.endswith(
                    'ראשון.txt' if vol == 'A' else 'שני.txt')][0]
        src = open(os.path.join(SRC, name), encoding='utf-8').read()
        assert src.endswith('\n')
        L = src[:-1].split('\n')
        used = set()
        folder = os.path.join(out_dir, FOLDER[vol])
        os.makedirs(folder, exist_ok=True)
        for title, sub, segs, extra in specs:
            btitle = title + SUFFIX
            if extra.get('sub_from_line'):
                _, sub = split_heading(2, HEAD_RE.match(
                    L[extra['sub_from_line'] - 1]).group(2))
            base = ['<h1>%s</h1>' % title,
                    '<small>%s</small>' % sub if sub else '']
            comp = {s: [] for s in SERIES_ORDER}   # note lines per series
            comp_links = {s: [] for s in SERIES_ORDER}
            comp_heads = {s: [] for s in SERIES_ORDER}  # emitted chain
            head_stack = []   # [(level, text)] current chain in base
            origin = []       # base line idx -> source line no (or None)
            origin += [None, None]
            ren = extra.get('renumber_heb')
            ren_count = 0
            if extra.get('intro_note'):
                a, b, s = extra['intro_note']
                comp[s].append('<h2>מבוא</h2>')
                for n in range(a + 1, b + 1):
                    comp[s].append(L[n - 1])
                    comp_links[s].append((2, len(comp[s])))
                    used.add(n)
                used.add(a)
            for first, last, shift in segs:
                for n in range(first, last + 1):
                    assert n not in used, (vol, n)
                    used.add(n)
                    line = L[n - 1]
                    hm = HEAD_RE.match(line)
                    if hm:
                        lvl = int(hm.group(1)) - shift
                        assert lvl >= 2, (vol, n, lvl)
                        text, hsub = split_heading(lvl, hm.group(2))
                        assert '<sup' not in text
                        base.append('<h%d>%s</h%d>' % (lvl, text, lvl))
                        origin.append(n)
                        while head_stack and head_stack[-1][0] >= lvl:
                            head_stack.pop()
                        head_stack.append((lvl, text))
                        if hsub:
                            base.append('<small>%s</small>' % hsub)
                            origin.append(None)
                        continue
                    notes = []

                    def repl(m):
                        nonlocal ren_count
                        mark, body = m.group(1), m.group(2)
                        s = series_of(mark, vol)
                        if ren and ren[0] <= n <= ren[1] and s == 'heb':
                            ren_count += 1
                            mark = heb_num(ren_count)
                        notes.append((s, mark, body))
                        return '<sup>%s</sup>' % mark
                    new = NOTE_RE.sub(repl, line)
                    base.append(new)
                    origin.append(n)
                    bline = len(base)
                    for s, mark, body in notes:
                        # emit the heading chain the companion lacks
                        chain = comp_heads[s]
                        k = 0
                        while (k < len(chain) and k < len(head_stack)
                               and chain[k] == head_stack[k]):
                            k += 1
                        del chain[k:]
                        for h in head_stack[k:]:
                            comp[s].append('<h%d>%s</h%d>' % (h[0], h[1], h[0]))
                            chain.append(h)
                        comp[s].append('<sup>%s</sup> %s' % (mark, body))
                        comp_links[s].append((bline, len(comp[s])))
            # write base
            with open(os.path.join(folder, btitle + '.txt'), 'w',
                      encoding='utf-8') as f:
                f.write('\n'.join(base) + '\n')
            recs = []
            made = []
            for s in SERIES_ORDER:
                if not comp[s]:
                    continue
                ctitle = SERIES_NAME[s] + btitle
                clines = ['<h1>%s</h1>' % ctitle, ''] + comp[s]
                with open(os.path.join(folder, ctitle + '.txt'), 'w',
                          encoding='utf-8') as f:
                    f.write('\n'.join(clines) + '\n')
                for bl, cl in comp_links[s]:
                    mk = re.match(r'<sup>([^<]+)</sup>', comp[s][cl - 1])
                    recs.append({
                        'line_index_1': bl,
                        'heRef_2': '%s %s' % (ctitle, mk.group(1) if mk else 'מבוא'),
                        'path_2': ctitle + '.txt',
                        'line_index_2': cl + 2,
                        'Conection Type': 'footnotes',
                    })
                made.append((s, len(comp_links[s])))
            recs.sort(key=lambda r: (r['line_index_1'], r['path_2'],
                                     r['line_index_2']))
            if recs:
                with open(os.path.join(out_dir, 'links', btitle + '_links.json'),
                          'w', encoding='utf-8') as f:
                    json.dump(recs, f, ensure_ascii=False, indent=1)
            json.dump({'origin': origin},
                      open(os.path.join(folder, '.' + btitle + '.origin.json'),
                           'w', encoding='utf-8'))
            report.append((vol, mask(btitle), len(base), made, ren_count))
        missing = sorted(set(range(1, len(L) + 1)) - used - DROPPED[vol])
        overlap = sorted(used & DROPPED[vol])
        report.append((vol, 'UNCOVERED', missing, 'OVERLAP', overlap))
    for r in report:
        print(*r)


if __name__ == '__main__':
    build(sys.argv[1])
