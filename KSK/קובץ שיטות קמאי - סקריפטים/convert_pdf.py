#!/usr/bin/env python3
"""Deterministic converter: KSK (Kovetz Shitot Kamai) HED PRESS PDFs -> Otzaria books.

Run with the venv python (PyMuPDF + pypdf):
    ksk/venv/bin/python ksk/convert_pdf.py            # all books
    ksk/venv/bin/python ksk/convert_pdf.py keritot    # one book
Outputs: out_pdf/<key>.txt, out_pdf/names.json, out_pdf/report.json (structure stats only).
Decoded pages are cached in work/dec/<index>.jsonl.gz (invalidated when kskdec.py changes).

Pipeline
 1. kskdec.decode_file: glyph-name -> cp1255 decoding with per-span font names.
 2. body pages = from the page carrying the ~36pt tractate title to the end
    (drops the Menachot title/preface/notices/introduction pages).
 3. per page: drop running header (y < 80), tractate title / figure captions (>= 14.5pt),
    diagram-label fonts; table fonts (Arakhin) become table rows; reading order =
    right column then left column (full-width lines flush in place).
 4. lines -> paragraphs: a paragraph starts on a first-line indent (~13pt from the
    column's right edge) or on a daf-marker line (13.6pt).  No hyphenation in source.
 5. paragraph -> daf marker (h2), trailing bold bracketed source label (h3).  Source-font
    bold (lemma / dibbur hamatchil) is not emitted as <b> (uniform with the doc books).
 6. sections (paragraphs up to and including the one carrying a label) get their h3
    placed before them, after an h2 that opens the section (old fix.py convention);
    "Aruch" labels follow the old convention (<h3>Aruch</h3> once per run + <b>label</b>
    line after each passage); labels >= 150 chars become a plain line (old h_3 rule).
"""
import sys, os, re, json, glob, unicodedata
HERE = os.path.dirname(os.path.abspath(__file__))
# Configurable locations (env overrides; defaults assume this folder is KSK/קובץ שיטות קמאי - סקריפטים/)
REPO = os.environ.get('KSK_REPO', os.path.dirname(os.path.dirname(HERE)))
WORK = os.environ.get('KSK_WORK', HERE)  # manifest.json, mapping.json, paras/, work/, out*/ live here
OLD_ROOT = os.environ.get('KSK_OLD_ROOT', os.path.join(
    REPO, 'KSK', 'ספרים', 'אוצריא', 'תלמוד בבלי', 'ראשונים'))  # reference h1/names: the packaged books by default;
# point it at an extracted pre-2026 KSK/ tree for real QA (same <root>/קובץ שיטות קמאי/<seder>/ layout)
AUTHOR = '\u05d4\u05e8\u05d1 \u05e9\u05dc\u05d5\u05dd \u05de\u05d0\u05d9\u05e8 \u05d9\u05d5\u05e0\u05d2\u05e8\u05de\u05df'  # line 2 of every book
sys.path.insert(0, HERE)
from kskdec import decode_file
from copyright_line import COPYRIGHT_LINE  # line 3 of every book

OUT = os.path.join(WORK, 'out_pdf')

# key -> (manifest indices in order, latin transliteration of the old file's tractate)
BOOKS = {
    'bekhorot': ([5], 'bkvrvt'),
    'keritot': ([13], 'krytvt'),
    'middot': ([17], 'mdvt'),
    'menachot': ([19, 20, 21, 22, 23], 'mnchvt'),
    'meilah': ([24], 'meylh'),
    'nedarim': ([26], 'ndrym'),
    'arakhin': ([33], 'erkyn'),
    'kinnim': ([36], 'qnym'),
    'temurah': ([40], 'tmvrh'),
    'tamid': ([41], 'tmyd'),
}

_T = dict(zip('אבגדהוזחטיכךלמםנןסעפףצץקרשת',
              ['a', 'b', 'g', 'd', 'h', 'v', 'z', 'ch', 't', 'y', 'k', 'k', 'l', 'm', 'm', 'n', 'n', 's',
               'e', 'p', 'f', 'tz', 'tz', 'q', 'r', 'sh', 't']))


def tr(s):
    s = re.sub(r'[֑-ׇ]', '', s)
    return ''.join(_T.get(c, '~' if '֐' <= c <= '׿' else c) for c in s)


HEB = 'א-ת'
AYIN, ALEF, BET = 'ע', 'א', 'ב'
DAF_WORD = 'דף'           # "daf"
ARUCH_KEY = 'הערוך'   # "he-Aruch" (as tested by the old fix.py)
ARUCH_H3 = 'ערוך'          # "Aruch"

TABLE_FONTS = re.compile(r'^(vil\.|frl\.|vilb-)')
DIAGRAM_FONTS = {'tam_bp', 'tam_rp', 'StamAshkenazy', 'GuttmanMiryamLight', 'Shlomo',
                 'Socializm-Regular', 'Pi3'}
BOLD_FONTS = re.compile(r'^(vil_b|vil\.b|vilb|frl_bp)')
MIRROR = str.maketrans({'(': ')', ')': '(', '[': ']', ']': '[', '{': '}', '}': '{'})


# --------------------------------------------------------------------------- lines
def body_lines(pages, stats):
    """Yield ('line', dict) / ('table', row_text) / ('page', n) in reading order."""
    start = None
    for i, pg in enumerate(pages):
        if any(34 < l['size'] < 38 for l in pg):
            start = i; break
    stats['front_pages_dropped'] = start
    stats['body_pages'] = len(pages) - start
    stats['header_lines'] = 0; stats['title_caption_lines'] = 0
    stats['diagram_chars'] = 0; stats['table_rows'] = 0
    for pi in range(start, len(pages)):
        pg = pages[pi]
        yield ('page', pi + 1)
        items = []; tables = []
        for l in pg:
            if l['y'] < 80:
                stats['header_lines'] += 1; continue
            if l['size'] >= 14.5:
                stats['title_caption_lines'] += 1; continue
            spans = []
            for f, s, sz in l['spans']:
                # drawing labels: small text (< 9pt) in drawing fonts, or any text < 7.5pt
                # outside tables; body-size letters in these fonts are kept
                if (f in DIAGRAM_FONTS and sz < 9) or (sz < 7.5 and not TABLE_FONTS.match(f)):
                    stats['diagram_chars'] += len(s.strip()); continue
                spans.append([f, s])
            if not spans or not ''.join(s for f, s in spans).strip():
                continue
            if all(TABLE_FONTS.match(f) for f, s in spans):
                tables.append(dict(l, spans=spans)); continue
            items.append(dict(l, spans=spans))
        # merge segments of one line split by a wide justification gap
        merged = {}
        for l in sorted(items, key=lambda d: -d['x1']):
            k = (l['col'], round(l['y']))
            if k in merged and l['col'] != 'F':
                m = merged[k]
                m['spans'] = m['spans'] + [[l['spans'][0][0], ' ']] + l['spans']
                m['x0'] = min(m['x0'], l['x0'])
            else:
                merged[k] = dict(l)
        items = sorted(merged.values(), key=lambda d: d['y'])
        # table rows: cluster table cells by (column, baseline); cells keep geometry
        trows = []
        for col in ('R', 'L'):
            cs = sorted([t for t in tables if (t['col'] if t['col'] != 'F' else 'R') == col], key=lambda d: d['y'])
            row = []
            for t in cs:
                if row and t['y'] - row[0]['y'] > 2:
                    trows.append(row); row = []
                row.append(t)
            if row:
                trows.append(row)
        trows = [dict(col=r[0]['col'] if r[0]['col'] != 'F' else 'R', y=min(c['y'] for c in r), page=pi + 1,
                      table=[dict(x0=c['x0'], x1=c['x1'], size=c['size'],
                                  bold=all(BOLD_FONTS.match(f) for f, s in c['spans'] if s.strip()),
                                  text=''.join(s for f, s in c['spans']).strip())
                             for c in sorted(r, key=lambda d: -d['x1'])])
                 for r in trows]
        seq = []
        buf = {'R': [], 'L': []}
        allit = sorted(items + trows, key=lambda d: d['y'])
        for it in allit:
            if it['col'] == 'F':
                seq += buf['R'] + buf['L']; buf = {'R': [], 'L': []}; seq.append(it)
            else:
                buf[it['col']].append(it)
        seq += buf['R'] + buf['L']
        for it in seq:
            if 'table' in it:
                stats['table_rows'] += 1
                yield ('table', it)
            else:
                yield ('line', it)


# -------------------------------------------------------------------------- tables
def build_tables(rows, st):
    """Consecutive table rows -> [('title', text) | ('table', html)].
    Tables are split on page/column change, a vertical gap > 30pt, or a title row
    (a single bold cell >= 12pt), which stays a normal line before its table.
    Columns come from the row with most cells (RTL order); other cells go to the
    column(s) whose centre they cover (-> colspan), missing ones become empty cells."""
    out = []; groups = []; cur = []
    for r in rows:
        cells = r['table']
        is_title = len(cells) == 1 and cells[0]['bold'] and cells[0]['size'] >= 12
        if cur and (r['page'] != cur[-1]['page'] or r['col'] != cur[-1]['col']
                    or r['y'] - cur[-1]['y'] > 30 or is_title):
            groups.append(cur); cur = []
        if is_title:
            groups.append([dict(r, title=True)]); continue
        cur.append(r)
    if cur:
        groups.append(cur)
    for g in groups:
        if g[0].get('title'):
            out.append(('title', g[0]['table'][0]['text'])); st['table_titles'] += 1; continue
        if len(g) == 1 and len(g[0]['table']) == 1:
            out.append(('title', g[0]['table'][0]['text'])); st['table_single_cell_as_text'] += 1; continue
        ref = max(g, key=lambda r: len(r['table']))['table']
        cols = [(c['x0'] + c['x1']) / 2 for c in ref]          # right-to-left
        ncol = len(cols)
        html = ['<table border="1">']
        for r in g:
            slots = [None] * ncol; spans = {}
            for c in r['table']:
                cover = [i for i, x in enumerate(cols) if c['x0'] - 2 <= x <= c['x1'] + 2]
                if not cover:
                    cx = (c['x0'] + c['x1']) / 2
                    cover = [min(range(ncol), key=lambda i: abs(cols[i] - cx))]
                i0 = cover[0]
                t = esc(clean(c['text'].translate(MIRROR)).strip())
                words = t.split(' ')
                if len(cover) > 1 and len(words) == len(cover):
                    # one decoded segment holding k narrow cells (gap < segment threshold)
                    for i, w in zip(cover, words):
                        slots[i] = w if slots[i] is None else slots[i] + ' ' + w
                    st['table_cells_split'] += 1
                    continue
                slots[i0] = t if slots[i0] is None else slots[i0] + ' ' + t
                if len(cover) > 1:
                    spans[i0] = len(cover)
                    for i in cover[1:]:
                        slots[i] = slots[i] if slots[i] is not None else ''
                        spans.setdefault(i, 0)
            tds = []; i = 0
            while i < ncol:
                if i in spans and spans[i] > 1:
                    tds.append(f'<td colspan="{spans[i]}">{slots[i] or ""}</td>'); st['table_colspans'] += 1
                    i += spans[i]; continue
                if slots[i] is None:
                    st['table_empty_cells'] += 1
                tds.append(f'<td>{slots[i] or ""}</td>'); i += 1
            html.append('<tr>' + ''.join(tds) + '</tr>')
        html.append('</table>')
        out.append(('table', ''.join(html))); st['tables'] += 1; st['table_rows_in_tables'] += len(g)
    return out


# ---------------------------------------------------------------------- paragraphs
def build_paragraphs(pages, stats):
    """Return list of items: ('para', runs, is_marker, page) or ('table', text, page)."""
    out = []; cur = None; pending_tables = []; page = None
    right = {'R': 538.0, 'L': 288.0, 'F': 538.0}
    for kind, v in body_lines(pages, stats):
        if kind == 'page':
            page = v; continue
        if kind == 'table':
            pending_tables.append(('table', v, page)); continue
        l = v
        ind = right[l['col']] - l['x1']
        indented = 8 < ind < 20
        marker = (l['size'] > 13.2 and indented and
                  bool(MARK_RE.match(''.join(s for f, s in l['spans']).translate(MIRROR))))
        start = marker or indented
        runs = [[bool(BOLD_FONTS.match(f)), s] for f, s in l['spans']]
        if start or cur is None:
            if cur is not None:
                out.append(cur)
            out.extend(pending_tables); pending_tables = []
            cur = ['para', runs, marker, page]
        else:
            cur[1] = cur[1] + [[cur[1][-1][0] if cur[1] else False, ' ']] + runs
    if cur is not None:
        out.append(cur)
    out.extend(pending_tables)
    return out


def norm_runs(runs):
    """merge runs, mirror brackets, normalise spacing; returns list of [bold, text]."""
    res = []
    for b, s in runs:
        s = s.translate(MIRROR)
        if res and res[-1][0] == b:
            res[-1][1] += s
        else:
            res.append([b, s])
    # whitespace-only runs inherit the neighbouring style (avoid <b> </b> noise)
    txt = ''.join(s for b, s in res)
    return res


def clean(s):
    s = ''.join(ch for ch in s if unicodedata.category(ch)[0] != 'C' or ch == ' ')
    s = s.replace('״', '"').replace('׳', "'").replace("''", '"')
    s = re.sub(r'\s+', ' ', s)
    # characters are ordered right-to-left, which reverses left-to-right digit runs
    s = re.sub(r'[0-9]{2,}', lambda m: m.group()[::-1], s)
    return s


def esc(s):
    return s.replace('<', '&lt;').replace('>', '&gt;')


def render(runs):
    """runs -> plain html-escaped text.  Source-font bold (the Vilna lemma / dibbur
    hamatchil runs) is not emitted, to match the doc-converted books, which carry <b>
    only on the Aruch label lines.  The run bold flags are still used upstream
    (split_label, table titles)."""
    return re.sub(r' {2,}', ' ', esc(''.join(clean(s) for b, s in runs))).strip()


ARUCH_BR = re.compile(r'\[([^\[\]]*' + ARUCH_KEY + r' [^\[\]]*)\]\.?')


def split_aruch(runs):
    """Split runs at every [he-Aruch erekh X] bracket (old fix_aruch rule).
    Returns list of ('text', runs) / ('aruch', label)."""
    flat = []
    for b, s in runs:
        flat += [(c, b) for c in s]
    txt = ''.join(c for c, b in flat)
    res = []; pos = 0
    def seg(a, z):
        out = []
        for c, b in flat[a:z]:
            if out and out[-1][0] == b:
                out[-1][1] += c
            else:
                out.append([b, c])
        return out
    for m in ARUCH_BR.finditer(txt):
        res.append(('text', seg(pos, m.start()))); res.append(('aruch', m.group(1))); pos = m.end()
    res.append(('text', seg(pos, len(flat))))
    return res


# --------------------------------------------------------------------- structure
MARK_RE = re.compile(r'^\s*([' + HEB + r'"\']{1,5} (?:' + AYIN + r'"[' + ALEF + BET + r']|\u05de"?[' + HEB + r']{1,2}))\.\s*')


def old_h2(text):
    """Marker -> h2 in the old KSK format.
    daf/amud  "B' AYIN"ALEF"  -> "DAF B."  (amud b -> ":"), quotes removed (old fix.py h_2);
    perek/mishna "P"A M"A"    -> "PEREK A MISHNA A" (canonical letters, no geresh; the old
                                 files had the h_2 artifact "DAF PA MA")."""
    toks = text.replace("''", '"').split()
    amud = re.sub('["\']', '', toks[-1]) if toks else ''
    if len(toks) == 2 and amud in (AYIN + ALEF, AYIN + BET):
        daf = re.sub('["\']', '', toks[0])
        return '<h2>' + DAF_WORD + ' ' + daf + ('.' if amud == AYIN + ALEF else ':') + '</h2>'
    if len(toks) == 2 and toks[0][:1] == PE and toks[1][:1] == MEM:
        p = heb_num(gem_val(re.sub('["\']', '', toks[0][1:])))
        m = heb_num(gem_val(re.sub('["\']', '', toks[1][1:])))
        return '<h2>' + PEREK_WORD + ' ' + p + ' ' + MISHNA_WORD + ' ' + m + '</h2>'
    t = re.sub('["\']', '', text).strip('[]. ')
    return '<h2>' + DAF_WORD + ' ' + t + '</h2>'


PEREK_WORD = 'פרק'
MISHNA_WORD = 'משנה'
PE, MEM = 'פ', 'מ'
_GV = dict(zip('אבגדהוזחטיכלמנסעפצקרשת',
               [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))
_GV.update({'ך': 20, 'ם': 40, 'ן': 50, 'ף': 80, 'ץ': 90})


def gem_val(s):
    return sum(_GV.get(c, 0) for c in s)


def heb_num(n):
    out = ''
    for v, c in ((400, 'ת'), (300, 'ש'), (200, 'ר'), (100, 'ק')):
        while n >= v:
            out += c; n -= v
    if n in (15, 16):
        return out + 'ט' + ('ו' if n == 15 else 'ז')
    for v, c in zip([90, 80, 70, 60, 50, 40, 30, 20, 10], 'צפעסנמלכי'):
        if n >= v:
            out += c; n -= v; break
    if n:
        out += 'אבגדהוזחט'[n - 1]
    return out


LABEL_RE = re.compile(r'\[([^\[\]]+)\]\s*\.?\s*$')


def split_label(runs):
    """If the paragraph ends with a bold [label](.), return (runs_without_label, label)."""
    flat = []   # (char, bold)
    for b, s in runs:
        flat += [(c, b) for c in s]
    txt = ''.join(c for c, b in flat).rstrip()
    m = LABEL_RE.search(txt)
    if not m:
        return runs, None
    inner = range(m.start(1), m.end(1))
    letters = [flat[i][1] for i in inner if 'א' <= flat[i][0] <= 'ת']
    if not letters or sum(letters) / len(letters) < 0.8:
        return runs, None
    keep = flat[:m.start()]
    out = []
    for c, b in keep:
        if out and out[-1][0] == b:
            out[-1][1] += c
        else:
            out.append([b, c])
    return out, m.group(1)


def h3_text(label):
    t = clean(label).replace("''", '"').replace('0', ' ').strip('[]. ').strip()
    return re.sub(r'\s+', ' ', t)


def convert(key):
    idxs, oldtr = BOOKS[key]
    manifest = json.load(open(os.path.join(WORK, 'manifest.json')))
    stats = {'volumes': []}
    items = []
    for ix in idxs:
        pages = decode_file(manifest[str(ix)]['path'], os.path.join(WORK, 'work', 'dec', f'{ix}.jsonl.gz'))
        vst = {'index': ix, 'pages': len(pages)}
        its = build_paragraphs(pages, vst)
        stats['volumes'].append(vst)
        items += its
    # ---- old file for name / h1
    old = [f for f in glob.glob(OLD_ROOT + '/*/*/*.txt') if tr(os.path.basename(f)).endswith(' el ' + oldtr + '.txt')]
    if old:
        oldf = old[0]
        fname = os.path.basename(oldf)
        h1 = open(oldf, encoding='utf-8').readline().rstrip('\n')
    else:
        oldf = None
        mp = json.load(open(os.path.join(WORK, 'mapping.json')))
        ref = [f for f in glob.glob(OLD_ROOT + '/*/*/*.txt') if tr(os.path.basename(f)).startswith('qvbtz shytvt qmay el ')][0]
        prefix = os.path.basename(ref).rsplit(' ', 1)[0]      # "<series> <al>"
        fname = prefix + ' ' + mp[str(idxs[0])]['tractate_he'] + '.txt'
        h1 = '<h1>' + fname[:-4] + '</h1>'
    # ---- build sections
    lines = [h1, AUTHOR, COPYRIGHT_LINE]
    sec = []          # list of output strings for the current section (paragraph/table lines)
    sec_h2 = None     # h2 that opens the current section
    in_aruch = False
    st = dict(paragraphs=0, h2=0, h3=0, aruch_labels=0, long_labels=0, unlabeled_sections=0,
              aruch_inline=0, repeated_marker_dropped=0, nonmarker_large_lines=0, tables=0, table_rows_in_tables=0, table_titles=0, table_single_cell_as_text=0, table_colspans=0, table_cells_split=0, table_empty_cells=0, paras_with_bold_lead=0, markers_midsection=0, labels_nonbold_end=0)
    dafs = []

    def flush(label):
        nonlocal sec, sec_h2, in_aruch
        if not sec and sec_h2 is None and label is None:
            return
        head = []
        if sec_h2:
            head.append(sec_h2)
        body = list(sec)
        if label is not None:
            lt = h3_text(label)
            if ARUCH_KEY in lt:
                st['aruch_labels'] += 1
                if not in_aruch:
                    head.append('<h3>' + ARUCH_H3 + '</h3>'); st['h3'] += 1
                body.append('<b>' + esc(lt) + '</b>')
                in_aruch = True
            elif len(lt) < 150:
                head.append('<h3>' + esc(lt) + '</h3>'); st['h3'] += 1; in_aruch = False
            else:
                head.append(esc(lt)); st['long_labels'] += 1; in_aruch = False
        else:
            if sec:
                st['unlabeled_sections'] += 1
            in_aruch = False
        lines.extend(head + body)
        sec = []; sec_h2 = None

    grouped = []
    for it in items:
        if it[0] == 'table' and grouped and grouped[-1][0] == 'tables':
            grouped[-1][1].append(it[1])
        elif it[0] == 'table':
            grouped.append(['tables', [it[1]]])
        else:
            grouped.append(it)
    for it in grouped:
        if it[0] == 'tables':
            for kind, v in build_tables(it[1], st):
                if kind == 'title':
                    t = render([[True, v.translate(MIRROR)]])
                    sec.append(t)
                else:
                    sec.append(v)
            continue
        _, runs, marker, page = it
        runs = norm_runs(runs)
        if marker:
            flat = ''.join(s for b, s in runs)
            m = MARK_RE.match(flat)
            if m:
                h2 = old_h2(m.group(1))
                # drop marker characters from the runs
                n = m.end(); out = []
                for b, s in runs:
                    if n >= len(s):
                        n -= len(s); continue
                    out.append([b, s[n:]]); n = 0
                runs = out
                if dafs and dafs[-1][0] == h2:
                    # volume seam: the next volume repeats the running amud marker
                    st['repeated_marker_dropped'] += 1
                else:
                    if sec:
                        # an amud starts inside an open section: close it unlabeled
                        st['markers_midsection'] += 1
                        flush(None)
                    elif sec_h2:
                        flush(None)
                    sec_h2 = h2; st['h2'] += 1; dafs.append((h2, page))
            else:
                st['nonmarker_large_lines'] += 1
        pieces = split_aruch(runs)
        label = None
        last = pieces[-1][1]
        if len(pieces) > 1 and not ''.join(s for b, s in last).strip(' .'):
            label = pieces[-2][1]; pieces = pieces[:-2]      # terminal Aruch label
        else:
            last, label = split_label(last); pieces[-1] = ('text', last)
        if any(b for b, s in runs if s.strip()) and [r for r in runs if r[1].strip()][0][0]:
            st['paras_with_bold_lead'] += 1
        np = 0
        for kind, v in pieces:
            if kind == 'aruch':
                sec.append('<b>' + esc(h3_text(v)) + '</b>'); st['aruch_inline'] += 1; continue
            text = render(v)
            if text:
                sec.append(text); np += 1
        st['paragraphs'] += 1 if np else 0
        if label is not None:
            flush(label)
    flush(None)
    # final hygiene: no empty lines after the three header lines, balanced tags
    body = [l for l in lines[3:] if l.strip()]
    lines = lines[:3] + body
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, key + '.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    stats.update(st)
    stats['file_name_translit'] = tr(fname)
    stats['old_file'] = tr(oldf) if oldf else None
    stats['dafs'] = [tr(h) for h, p in dafs]
    return fname, stats


def main():
    keys = sys.argv[1:] or list(BOOKS)
    names = {}
    npath = os.path.join(OUT, 'names.json')
    if os.path.exists(npath):
        names = json.load(open(npath, encoding='utf-8'))
    rpath = os.path.join(OUT, 'report.json')
    report = json.load(open(rpath)) if os.path.exists(rpath) else {}
    for k in keys:
        fname, st = convert(k)
        names[k] = fname
        report[k] = st
        print(k, {x: st[x] for x in ('paragraphs', 'h2', 'h3', 'aruch_labels', 'long_labels',
                                      'unlabeled_sections', 'markers_midsection', 'aruch_inline')})
    names = {k: names[k] for k in BOOKS if k in names}
    with open(npath, 'w', encoding='utf-8') as f:
        json.dump(names, f, ensure_ascii=False, indent=1)
    with open(rpath, 'w') as f:
        json.dump(report, f, indent=1)


if __name__ == '__main__':
    main()
