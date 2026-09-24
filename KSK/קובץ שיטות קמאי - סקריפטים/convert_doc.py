#!/usr/bin/env python3
"""Convert the new Kovetz Shitot Kamai .doc sources into Otzaria book files.

Input : paras/<i>.jsonl  (produced by extract.py via the Word-97 parser docparse.py;
        regenerated automatically from manifest.json if missing)
Output: out/<i>.txt, out/<i>.stats.json, out/names.json, out/summary.json

Structure produced (mirrors the old KSK files under KSK/<..>/<seder>/):
  line 1  <h1>TITLE</h1>          (identical to the old file's h1)
  line 2  AUTHOR                   (anthology label, identical in all 38 books)
  <h2>DAF X.</h2> / <h2>DAF X:</h2> per amud  (period = amud a, colon = amud b)
  <h3>LABEL</h3> before each passage; LABEL = the trailing "[...]" source label of the
          passage (moved from the end of its last paragraph, like KSK/fix and split/fix.py)
  Arukh passages (label contains HERUKH): one <h3>ARUKH</h3> per consecutive run of
          Arukh passages (an h2 does not break the run -- fix.py behaviour); every Arukh
          entry label "[HERUKH ERECH X]" (trailing or inside a paragraph) becomes its own
          <b>..</b> line after the entry text (fix.py fix_aruch).

Deterministic: no randomness, no timestamps. Re-run: python3 convert_doc.py [idx ...]
"""
import csv
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
# Configurable locations (env overrides; defaults assume this folder is KSK/קובץ שיטות קמאי - סקריפטים/)
REPO = os.environ.get('KSK_REPO', os.path.dirname(os.path.dirname(HERE)))
WORK = os.environ.get('KSK_WORK', HERE)  # manifest.json, mapping.json, paras/, work/, out*/ live here
OLD_ROOT = os.environ.get('KSK_OLD_ROOT', os.path.join(
    REPO, 'KSK', 'ספרים', 'אוצריא', 'תלמוד בבלי', 'ראשונים'))  # reference h1/names: the packaged books by default;
# point it at an extracted pre-2026 KSK/ tree for real QA (same <root>/קובץ שיטות קמאי/<seder>/ layout)
AUTHOR = '\u05dc\u05d9\u05e7\u05d5\u05d8 \u05e8\u05d0\u05e9\u05d5\u05e0\u05d9\u05dd'  # line 2 of every book
OLD_DIR = os.path.join(OLD_ROOT, 'קובץ שיטות קמאי')
REPLACE_CSV = os.path.join(HERE, 'replace.csv')  # label fixes (from the old KSK/fix and split/)
OUT = os.path.join(WORK, 'out')

DOC_IDX = [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 18, 25, 27, 28, 29, 30,
           31, 32, 34, 35, 37, 38, 39, 42]

# index -> tractate name exactly as in the old KSK file name
TRACTATE = {
    1: 'בבא בתרא', 2: 'בבא מציעא', 3: 'בבא קמא', 4: 'ביצה', 6: 'ברכות', 7: 'גיטין',
    8: 'הוריות', 9: 'חגיגה', 10: 'חולין', 11: 'יבמות', 12: 'יומא', 14: 'כתובות',
    15: 'מגילה', 16: 'מועד קטן', 18: 'מכות', 25: 'נדה', 27: 'נזיר', 28: 'סוטה',
    29: 'סוכה', 30: 'סנהדרין', 31: 'עבודה זרה', 32: 'עירובין', 34: 'פסחים',
    35: 'קידושין', 37: 'ראש השנה', 38: 'שבועות', 39: 'שבת', 42: 'תענית',
}
CONVENTION = {i: 'A' for i in (1, 2, 3, 4, 6, 7, 11, 14, 35)}
CONVENTION.update({i: 'B' for i in (9, 10, 12, 15, 16, 25, 29, 30, 31, 32, 34, 37, 39, 42)})
CONVENTION.update({i: 'C' for i in (8, 18, 27, 28, 38)})

DAF_WORD = 'דף'
ARUKH_KEY = 'הערוך'
ARUKH_H3 = 'ערוך'
MAX_LABEL = 150          # fix.py: labels >= 150 chars were not made headings

GEM = dict(zip('אבגדהוזחטיכלמנסעפצקרשת',
               [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))
HEB = re.compile(r'[\u05d0-\u05ea]')

# ---------------------------------------------------------------- regexes
# Word picture-field residue, e.g. \raster(85%,85%)="Z580;" -- parentheses/digits are
# sometimes garbled (")85%,85%(", "Z5(8"), and a bare "Z..." reference can remain alone.
RASTER_RE = re.compile(r'\\raster\s*[()][^"=]{0,40}[()]\s*="[^"]{0,12}"')
IMGREF_RE = re.compile(r'"[Zz][0-9()\[\]a-z; ]{1,8}"|\\raster=?(?![\s\S]{0,3}\()')
FINALS = set('ךםןףץ')
QAMATS = '\u05b8'
_WF = None


def word_freq():
    """Corpus frequencies of unpointed tokens (all 28 docs) for the '0' split test."""
    global _WF
    if _WF is None:
        _WF = Counter()
        for i in DOC_IDX:
            p = os.path.join(WORK, 'paras', f'{i}.jsonl')
            if not os.path.exists(p):
                continue
            for l in open(p, encoding='utf-8'):
                t = ''.join(r[0] for r in json.loads(l)['runs'])
                for w in t.split():
                    if '0' in w:
                        continue
                    w = _core(w)
                    if w:
                        _WF[w] += 1
    return _WF


def _core(w):
    w = w.replace('\u00b4', "'")
    w = re.sub(r'[\u0591-\u05c7]', '', w)
    return w.strip('.,:;!?()[]{}—-~ ')


def is_heb(c):
    return '\u05b0' <= c <= '\u05ea'


def fix_zero(t, st):
    """The docs use '0' for two things: a space-like filler (after ')' in enumerations,
    before '—', inside labels, between glued words) and the vowel QAMATS (U+05B8 is
    otherwise completely absent from the corpus; '0' sits right after a letter in
    pointed words and is never adjacent to another vowel)."""
    wf = word_freq()
    out = []
    i = 0
    n = len(t)
    while i < n:
        c = t[i]
        if c != '0':
            out.append(c)
            i += 1
            continue
        j = i
        while j < n and t[j] == '0':
            j += 1
        a = t[i - 1] if i > 0 else ' '
        b = t[j] if j < n else ' '
        if a.isdigit() or b.isdigit() or (a in ' \t' and b in ' \t'):
            out.append(t[i:j])                     # real number / lone zero: keep
            if not (a.isdigit() or b.isdigit()):
                st['zero_lone_kept'] += 1
            i = j
            continue
        if not (is_heb(a) and is_heb(b)) or j - i > 1:
            st['zero_to_space_punct'] += 1
            out.append(' ')
            i = j
            continue
        if a in FINALS:
            st['zero_to_space_after_final'] += 1
            out.append(' ')
            i = j
            continue
        # whole whitespace token around position i
        ts = t.rfind(' ', 0, i) + 1
        te = t.find(' ', j)
        te = n if te == -1 else te
        tok = t[ts:te]
        if re.search(r'[\u05b0-\u05c7]', tok):
            st['zero_to_qamats_pointed_word'] += 1
            out.append(QAMATS)
            i = j
            continue
        parts = _core(tok).split('0')
        k = t[ts:i].count('0')                    # index of this zero inside tok
        left = _core(parts[k]) if k < len(parts) else ''
        right = _core(parts[k + 1]) if k + 1 < len(parts) else ''
        joined = ''.join(parts)
        if (len(left) >= 2 and len(right) >= 2 and wf[left] >= 3 and wf[right] >= 3
                and wf[joined] * 20 < min(wf[left], wf[right])):
            st['zero_to_space_split_words'] += 1
            out.append(' ')
        else:
            st['zero_to_qamats_unpointed_word'] += 1
            out.append(QAMATS)
        i = j
    return ''.join(out)
CTRL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]')
MARK_RE = re.compile(
    r'^\s*(?P<num>[א-ת]{1,2}"[א-ת]|[א-ת]\')\s*ע"(?P<amud>[אב])\s*(?P<punct>[.:])?\s*~?\s*')
INNER_ARUKH_RE = re.compile(r'\[([^\[\]]*הערוך ערך[^\[\]]*)\]')
LABEL_RE = re.compile(r'\s*\[(?P<lab>[^\[\]]+)\]\s*\.?\s*$')


def gematria(s):
    return sum(GEM.get(c, 0) for c in s if c in GEM)


def canon_daf(n):
    """Standard Hebrew numeral without geresh (15=TV, 16=TZ)."""
    out = ''
    for v, c in ((400, 'ת'), (300, 'ש'), (200, 'ר'), (100, 'ק')):
        while n >= v:
            out += c
            n -= v
    if n == 15:
        return out + 'טו'
    if n == 16:
        return out + 'טז'
    for v, c in ((90, 'צ'), (80, 'פ'), (70, 'ע'), (60, 'ס'), (50, 'נ'), (40, 'מ'),
                 (30, 'ל'), (20, 'כ'), (10, 'י')):
        if n >= v:
            out += c
            n -= v
            break
    for v, c in ((9, 'ט'), (8, 'ח'), (7, 'ז'), (6, 'ו'), (5, 'ה'), (4, 'ד'), (3, 'ג'), (2, 'ב'), (1, 'א')):
        if n >= v:
            out += c
            n -= v
            break
    return out


def load_paras(idx):
    p = os.path.join(WORK, 'paras', f'{idx}.jsonl')
    if not os.path.exists(p):
        sys.path.insert(0, HERE)
        import subprocess
        subprocess.check_call([sys.executable, os.path.join(HERE, 'extract.py'), str(idx)], cwd=WORK)
    return [''.join(r[0] for r in json.loads(l)['runs']) for l in open(p, encoding='utf-8')]


def load_replace():
    rows = []
    with open(REPLACE_CSV, encoding='windows-1255', newline='') as f:
        for r in csv.reader(f):
            if len(r) >= 2:
                rows.append((r[0].strip(), r[1].strip()))
    return rows


REPLACE_ROWS = load_replace()


def old_file(idx):
    fs = glob.glob(os.path.join(OLD_DIR, '*', f'קובץ שיטות קמאי על {TRACTATE[idx]}.txt'))
    assert len(fs) == 1, (idx, fs)
    return fs[0]


# ---------------------------------------------------------------- normalization
def normalize(t, st, swap_sq, in_table):
    """Faithful text cleanup of one paragraph. Every change is counted in st."""
    n = len(CTRL_RE.findall(t))
    if n:
        st['ctrl_removed'] += n
        t = CTRL_RE.sub('', t)
    n = len(RASTER_RE.findall(t))
    if n:
        st['raster_field_removed'] += n
        t = RASTER_RE.sub(' ', t)
    n = len(IMGREF_RE.findall(t))
    if n:
        st['bare_image_ref_removed'] += n
        t = IMGREF_RE.sub(' ', t)
    if swap_sq:
        k = t.count('[') + t.count(']')
        if k:
            st['sq_bracket_swapped'] += k
            t = t.translate(str.maketrans('[]', ']['))
    n = t.count('´')
    if n:
        st['acute_to_geresh'] += n
        t = t.replace('´', "'")
    n = t.count("''")
    if n:
        st['double_apos_to_quote'] += n
        t = t.replace("''", '"')
    n = t.count('%')
    if n:
        st['percent_to_hyphen'] += n
        t = t.replace('%', '-')
    if '0' in t:
        if in_table:
            st['zero_in_table_kept'] += t.count('0')
        else:
            t = fix_zero(t, st)
    n = t.count('\t')
    if n:
        st['tab_to_space'] += n
        t = t.replace('\t', ' ')
    n = t.count('\u00a0')
    if n:
        st['nbsp_to_space'] += n
        t = t.replace('\u00a0', ' ')
    n = t.count('<') + t.count('>')
    if n:
        st['angle_escaped'] += n
        t = t.replace('<', '&lt;').replace('>', '&gt;')
    t2 = re.sub(r' {2,}', ' ', t)
    if t2 != t:
        st['space_runs_collapsed'] += 1
    return t2.strip()


def clean_label(lab, st, delta):
    """fix.py h_3(): '' -> ", 0 -> space, strip '[]. '; then replace.csv (labels only)."""
    lab = lab.replace("''", '"').replace('0', ' ')
    lab = re.sub(r' {2,}', ' ', lab).strip('[]. ').strip()
    before = lab
    for k, v in REPLACE_ROWS:
        if k and k in lab:
            lab = lab.replace(k, v)
            st['label_replace_csv_applied'] += 1
    if lab != before:
        st['labels_changed_by_replace_csv'] += 1
        delta.update(letters(lab))
        delta.subtract(letters(before))
    return lab


def letters(s):
    return Counter(HEB.findall(s))


# ---------------------------------------------------------------- tables
def build_tables(items, st):
    """Group consecutive tab-row items into one single-line <table border="1">.
    - ncol = widest row; a shorter row that began with a tab is padded with empty cells
      at the START (its text sat in the later columns), otherwise at the END; a lone
      one-cell row without leading tab inside the table gets colspan=ncol.
    - a one-cell first row without leading tab (and >= 2 more rows) is a title: it stays
      a normal line before the table.
    - a group of a single row is not a table: its cells are joined by a space.
    - a trailing source label in the last cell is moved after </table> so the normal
      passage/label logic turns it into the h3 (labels inside the table stay in place).
    """
    out, tables = [], []
    i = 0
    while i < len(items):
        if items[i][0] != 'row':
            out.append(items[i])
            i += 1
            continue
        j = i
        while j < len(items) and items[j][0] == 'row':
            j += 1
        rows = [(it[1], list(it[2]), it[3]) for it in items[i:j]]
        i = j
        if len(rows) == 1 or all(len(r[1]) == 1 for r in rows):
            for _, cells, _ in rows:
                out.append(('p', ' '.join(cells)))
            st['tab_rows_kept_as_text'] += len(rows)
            continue
        title = None
        if len(rows) >= 3 and len(rows[0][1]) == 1 and not rows[0][0]:
            title = rows.pop(0)[1][0]
            st['table_title_line'] += 1
        # label in last cell of the last row
        tail = ''
        m = LABEL_RE.search(rows[-1][1][-1])
        if m and len(m.group('lab').strip()) < MAX_LABEL:
            tail = ' ' + m.group(0).strip()
            rows[-1][1][-1] = rows[-1][1][-1][:m.start()].rstrip()
            if not rows[-1][1][-1]:
                rows[-1][1].pop()
            st['table_label_moved_after_table'] += 1
        ncol = max(len(r[1]) for r in rows)
        ragged = Counter()
        html = ['<table border="1">']
        for leading, cells, _ in rows:
            n = len(cells)
            if n == ncol:
                tds = [f'<td>{c}</td>' for c in cells]
            elif n == 1 and not leading:
                tds = [f'<td colspan="{ncol}">{cells[0]}</td>']
                ragged['colspan'] += 1
            elif leading:
                tds = ['<td></td>'] * (ncol - n) + [f'<td>{c}</td>' for c in cells]
                ragged['pad_start'] += 1
            else:
                tds = [f'<td>{c}</td>' for c in cells] + ['<td></td>'] * (ncol - n)
                ragged['pad_end'] += 1
            html.append('<tr>' + ''.join(tds) + '</tr>')
        html.append('</table>')
        if title is not None:
            out.append(('p', title))
        out.append(('p', ''.join(html) + tail))
        st['tables'] += 1
        st['table_rows'] += len(rows)
        tables.append(dict(first_para=rows[0][2], rows=len(rows), ncol=ncol,
                           title=title is not None, label_after=bool(tail),
                           ragged=dict(ragged),
                           col_counts=dict(Counter(len(r[1]) for r in rows))))
    return out, tables


# ---------------------------------------------------------------- conversion
def convert(idx):
    st = Counter()
    raw = load_paras(idx)
    title_para = 'מסכת ' + TRACTATE[idx]
    title_alt = {title_para, 'מסכת מו"ק', "מסכת מו''ק"}
    sq_open = sum(1 for t in raw if re.search(r'[\[\]]', t) and re.search(r'[\[\]]', t).group() == '[')
    sq_close = sum(1 for t in raw if re.search(r'[\[\]]', t) and re.search(r'[\[\]]', t).group() == ']')
    swap_sq = sq_close > sq_open

    src_letters = Counter()   # letters of kept source text (for exact conservation check)
    src_words = 0
    items = []                # ('h2', text, (daf, amud)) / ('p', text)
    marks = []
    for pi, t0 in enumerate(raw):
        in_table = t0.count('\t') >= 2
        t = normalize(t0, st, swap_sq, in_table)
        if not t:
            st['empty_para_removed'] += 1
            continue
        if t in title_alt:
            st['title_para_dropped'] += 1
            continue
        if '\t' in t0 and not MARK_RE.match(t):
            # tab-separated row -> table cell list (cells normalized one by one)
            leading = t0.lstrip(' ')[:1] == '\t'
            cells = []
            for c in re.split(r'\t+', t0.strip(' \t')):
                c = normalize(c, st, swap_sq, in_table)
                if c:
                    cells.append(c)
                else:
                    st['table_empty_cell_dropped'] += 1
            if cells:
                items.append(('row', leading, cells, pi))
                for c in cells:
                    src_letters += letters(c)
                    src_words += len(c.split())
                continue
        m = MARK_RE.match(t)
        if m:
            num, amud = m.group('num'), m.group('amud')
            daf = gematria(num)
            letters_src = num.replace('"', '').replace("'", '')
            if letters_src != canon_daf(daf):
                st['daf_noncanonical_spelling'] += 1
            rest = t[m.end():].strip()
            marks.append(dict(para=pi, daf=daf, amud=amud, inline=bool(rest),
                              punct=m.group('punct') or ''))
            items.append(('h2', f'{DAF_WORD} {canon_daf(daf)}{"." if amud == "א" else ":"}', (daf, amud)))
            st['marker_inline' if rest else 'marker_standalone'] += 1
            if rest:
                items.append(('p', rest))
                src_letters += letters(rest)
                src_words += len(rest.split())
            continue
        items.append(('p', t))
        src_letters += letters(t)
        src_words += len(t.split())

    items, tables = build_tables(items, st)

    # ---- passages: text since the previous label, closed by a paragraph with a label
    lines = []
    lbl_delta = Counter()
    buf = []                  # pending items of the current passage

    def split_inner_arukh(text):
        """fix.py fix_aruch(): an Arukh entry label "[HERUKH ERECH X]" inside a paragraph
        ends that entry -> own <b> line; text after it continues on a new line."""
        res = []
        pos = 0
        if text.startswith('<table'):
            return [text]
        for m in INNER_ARUKH_RE.finditer(text):
            seg = text[pos:m.start()].strip().lstrip('.').strip()
            if seg:
                res.append(seg)
            res.append(f'<b>{clean_label(m.group(1), st, lbl_delta)}</b>')
            st['arukh_inner_entry_bold'] += 1
            pos = m.end()
        seg = text[pos:].strip()
        if pos and seg.startswith('.'):
            st['dot_after_inner_arukh_dropped'] += 1
        seg = seg.lstrip('.').strip() if pos else seg
        if seg:
            res.append(seg)
        return res

    prev_arukh = False
    h3_labels = []

    def flush(label, arukh_label, closing_text):
        nonlocal prev_arukh
        lead = []
        body = list(buf)
        while body and body[0][0] == 'h2':
            lead.append(body.pop(0))
        for it in lead:
            lines.append(f'<h2>{it[1]}</h2>')
        # (as in fix.py, an h2 does not break a run of Arukh passages)
        content = [it for it in body] + ([('p', closing_text)] if closing_text else [])
        if arukh_label is not None:
            if not prev_arukh:
                lines.append(f'<h3>{ARUKH_H3}</h3>')
                st['h3_arukh_group'] += 1
            prev_arukh = True
        elif label is not None:
            lines.append(f'<h3>{label}</h3>')
            h3_labels.append(label)
            st['h3_label'] += 1
            prev_arukh = False
        else:
            prev_arukh = False
        if not any(it[0] == 'p' for it in content) and label is not None:
            st['h3_without_body'] += 1
        for it in content:
            if it[0] == 'h2':
                lines.append(f'<h2>{it[1]}</h2>')
                st['h2_inside_passage'] += 1
                # an h2 inside an Arukh passage run breaks the group
            else:
                lines.extend(split_inner_arukh(it[1]))
        if arukh_label is not None:
            lines.append(f'<b>{arukh_label}</b>')
            st['arukh_entry_bold'] += 1
        buf.clear()

    for it in items:
        if it[0] == 'h2':
            buf.append(it)
            continue
        t = it[1]
        m = LABEL_RE.search(t)
        if not m:
            buf.append(it)
            continue
        lab_raw = m.group('lab').strip()
        if len(lab_raw) >= MAX_LABEL:
            st['long_bracket_kept_inline'] += 1
            buf.append(it)
            continue
        before = t[:m.start()].rstrip()
        lab = clean_label(lab_raw, st, lbl_delta)
        if not lab:
            st['empty_label_kept_inline'] += 1
            buf.append(it)
            continue
        if ARUKH_KEY in lab:
            flush(None, lab, before)
        else:
            flush(lab, None, before)
    if buf:
        st['trailing_unlabeled_items'] += sum(1 for x in buf if x[0] == 'p')
        flush(None, None, '')

    old = old_file(idx)
    old_lines = open(old, encoding='utf-8').read().split('\n')
    h1 = old_lines[0]
    assert h1.startswith('<h1>') and h1.endswith('</h1>')
    out_lines = [h1, AUTHOR] + lines
    text = '\n'.join(out_lines) + '\n'
    assert '\r' not in text
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f'{idx}.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)

    # ---- conservation check: letters of body, labels (excluding synthetic headings)
    out_letters = Counter()
    out_words = 0
    for l in lines:
        if l.startswith('<h2>'):
            continue
        if l == f'<h3>{ARUKH_H3}</h3>':
            continue
        s = re.sub(r'<[^>]+>', '', l)
        out_letters += letters(s)
        out_words += len(s.split())
    out_letters.subtract(lbl_delta)  # undo replace.csv edits for the conservation check
    st_out = dict(sorted(st.items()))
    daf_seq = [(m['daf'], m['amud']) for m in marks]
    return dict(idx=idx, tractate=TRACTATE[idx], convention=CONVENTION[idx],
                swap_sq=swap_sq, n_paras=len(raw), n_lines=len(out_lines),
                n_h2=sum(1 for l in lines if l.startswith('<h2>')),
                n_h3=sum(1 for l in lines if l.startswith('<h3>')),
                src_letters=sum(src_letters.values()), out_letters=sum(out_letters.values()),
                letter_diff={k: out_letters[k] - src_letters[k]
                             for k in set(src_letters) | set(out_letters)
                             if out_letters[k] != src_letters[k]},
                src_words=src_words, out_words=out_words,
                stats=st_out, daf_seq=daf_seq, tables=tables,
                marks_inline=sum(1 for m in marks if m['inline']),
                old_file=os.path.relpath(old, REPO),
                name=os.path.basename(old)[:-4])


def main(argv):
    idxs = [int(a) for a in argv] or DOC_IDX
    names_p = os.path.join(OUT, 'names.json')
    names = json.load(open(names_p, encoding='utf-8')) if os.path.exists(names_p) else {}
    summ = {}
    for idx in idxs:
        r = convert(idx)
        names[str(idx)] = r['name']
        with open(os.path.join(OUT, f'{idx}.stats.json'), 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        summ[idx] = {k: r[k] for k in ('convention', 'n_h2', 'n_h3', 'src_letters', 'out_letters')}
        print(idx, r['convention'], 'h2', r['n_h2'], 'h3', r['n_h3'],
              'letters src/out', r['src_letters'], r['out_letters'])
    names = dict(sorted(names.items(), key=lambda kv: int(kv[0])))
    with open(names_p, 'w', encoding='utf-8') as f:
        json.dump(names, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main(sys.argv[1:])
