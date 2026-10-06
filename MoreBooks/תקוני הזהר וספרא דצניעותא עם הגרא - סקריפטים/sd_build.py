#!/usr/bin/env python3
"""ספרא דצניעותא עם ביאור הגרא — עדכון הקובץ הקיים מה-docx המתוקן (תשרי תשפ"ז).

הקובץ הקיים במאגר נבנה מאותו docx (מהדורת אלול תשפ"ה) ותוקן ביד ב-git.
לכן לא ממירים מחדש: כל פסקת docx מוצמדת לשורה הקיימת שלה (התאמה מלאה
בטקסט בלי רווחים), ובשורה הקיימת:
  1. מוחלים שינויי טקסט אמיתיים מה-docx (רשימה מפורשת, נבדקת ביד — --show).
  2. מוכנס <sup>N</sup> במקום כל הפניית הערת שוליים.
ההערות עצמן נכתבות ל-"הערות על <ספר>.txt" ומקושרות ב-footnotes (מיזוג
HearotCompanionMerge → הערות קופצות).

    python3 sd_build.py --docx-dir <unzipped> --old <txt> --out <dir> [--show]
"""
import argparse
import difflib
import html
import json
import os
import re
import sys

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docxfmt import W, Styles, esc, plain, segments  # noqa: E402

TITLE = 'ספרא דצניעותא עם ביאור הגרא'
NTITLE = 'הערות על ' + TITLE
HEAD_RX = re.compile(r'^<h([1-6])>(.*)</h\1>\s*$')
FNCH = ''


def old_plain(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s))


def norm_new(segs):
    """טקסט הפסקה עם FNCH במקום כל הפניה, ורשימת מזהי ההערות לפי הסדר."""
    out, ids = [], []
    for s in segs:
        if s[0] == 't':
            out.append(s[1])
        elif s[0] == 'br':
            out.append(' ')
        elif s[0] == 'fn':
            out.append(FNCH)
            ids.append(s[1])
    t = ''.join(out).replace('’', "'").replace('‘', "'")
    return t, ids


def key(s):
    return re.sub(r'\s+', '', s.replace(FNCH, '')).replace('’', "'")


def note_html(fn, styles):
    """הערת שוליים → HTML של שורה אחת (פסקאות מחוברות ב-<br>)."""
    paras = []
    for p in fn.iter(W + 'p'):
        segs = [s for s in segments(p, styles) if s[0] == 't' and not s[2]['sup']]
        parts = []
        for _, t, f in segs:
            if not t:
                continue
            parts.append((t, f['bold'], f['sz'] <= 20))
        # איחוד ריצות עם אותו עיצוב
        merged = []
        for t, b, sm in parts:
            if merged and merged[-1][1:] == (b, sm):
                merged[-1] = (merged[-1][0] + t, b, sm)
            elif merged and not t.strip():
                merged[-1] = (merged[-1][0] + t,) + merged[-1][1:]
            else:
                merged.append((t, b, sm))
        h = []
        for t, b, sm in merged:
            lead = t[:len(t) - len(t.lstrip())]
            trail = t[len(t.rstrip()):]
            core = esc(t.strip())
            if not core:
                h.append(' ')
                continue
            if sm:
                core = '<small>%s</small>' % core
            if b:
                core = '<b>%s</b>' % core
            h.append(lead + core + trail)
        s = re.sub(r'\s+', ' ', ''.join(h)).strip()
        s = re.sub(r'</b>(\s*)<b>', r'\1', s)
        s = re.sub(r'</small>(\s*)<small>', r'\1', s)
        if s:
            paras.append(s)
    return '<br>'.join(paras).replace('’', "'").replace('‘', "'")


def html_index_map(h):
    """אינדקס תו-טקסט → אינדקס ב-HTML (הקובץ בלי ישויות &)."""
    assert '&' not in h
    idx = []
    i = 0
    while i < len(h):
        if h[i] == '<':
            j = h.index('>', i)
            i = j + 1
            continue
        idx.append(i)
        i += 1
    return idx


def insert_pos(h, idx, p):
    """מקום הכנסה לפני תו-טקסט p: אחרי התו הקודם וכל תגי הסגירה שאחריו,
    לפני תגי פתיחה (כדי שהסמן לא יירש עיצוב של הציטוט שאחריו)."""
    if p == 0:
        return 0
    q = idx[p - 1] + 1
    while q < len(h) and h.startswith('</', q):
        q = h.index('>', q) + 1
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--docx-dir', required=True)
    ap.add_argument('--old', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--show', action='store_true')
    a = ap.parse_args()

    styles = Styles(a.docx_dir)
    body = etree.parse(a.docx_dir + '/word/document.xml').getroot().find(W + 'body')
    paras = list(body.iter(W + 'p'))
    newp = [norm_new(segments(p, styles)) for p in paras]
    fx = etree.parse(a.docx_dir + '/word/footnotes.xml').getroot()
    notes = {f.get(W + 'id'): note_html(f, styles) for f in fx.iter(W + 'footnote')
             if int(f.get(W + 'id')) > 1}

    old = open(a.old, encoding='utf-8').read().split('\n')
    assert old[-1] == ''
    old = old[:-1]

    # הצמדת שורות לפסקאות
    ok = [key(old_plain(l)) for l in old]
    nk = [key(t) for t, _ in newp]
    sm = difflib.SequenceMatcher(None, ok, nk, autojunk=False)
    pairs = {}
    for t, i1, i2, j1, j2 in sm.get_opcodes():
        if t == 'equal':
            for k in range(i2 - i1):
                pairs[i1 + k] = j1 + k
    unpaired_fn = [j for j, (t, ids) in enumerate(newp) if ids and j not in pairs.values()]
    assert not unpaired_fn, unpaired_fn

    out = list(old)
    changes = []
    fn_order = []          # (old line idx, fn id)
    for i, j in sorted(pairs.items()):
        h = old[i]
        if HEAD_RX.match(h):
            assert not newp[j][1]
            continue
        a_txt = old_plain(h)
        n_txt, ids = newp[j]
        clean = n_txt.replace(FNCH, '')
        fpos = []          # אינדקסים ב-clean
        c = 0
        for ch in n_txt:
            if ch == FNCH:
                fpos.append(c)
            else:
                c += 1
        ops = difflib.SequenceMatcher(None, a_txt, clean, autojunk=False).get_opcodes()
        # שינויי טקסט שאינם רווח סביב סמן הערה
        for t, i1, i2, j1, j2 in ops:
            if t == 'equal':
                continue
            seg_old, seg_new = a_txt[i1:i2], clean[j1:j2]
            near_fn = any(j1 - 1 <= q <= j2 + 1 for q in fpos)
            if not (seg_old + seg_new).strip() and near_fn:
                continue
            changes.append((i + 1, t, a_txt[max(0, i1 - 15):i1], seg_old, seg_new, a_txt[i2:i2 + 15]))

        def map_q(q):
            for t, i1, i2, j1, j2 in ops:
                if t == 'equal' and j1 <= q < j2:
                    return i1 + q - j1
                if t in ('replace', 'insert') and j1 <= q < j2:
                    return i1
            return len(a_txt)
        idx = html_index_map(h)
        ins = []
        for q, fid in zip(fpos, ids):
            ins.append((map_q(q), fid))
        # הכנסה מהסוף להתחלה; המספור נקבע בסדר הופעה אחר כך
        for p, fid in sorted(ins, key=lambda x: -x[0]):
            pos = insert_pos(h, idx, p)
            h = h[:pos] + FNCH + fid + FNCH + h[pos:]
        out[i] = h
        fn_order.extend((i, fid) for _, fid in sorted(ins, key=lambda x: x[0]))

    if a.show:
        for c in changes:
            print('L%d %s |%s[%s→%s]%s|' % c)
        print('changes', len(changes), 'footnotes', len(fn_order))
        return

    # מספור, ושורות ההערות לפי מסלול הכותרות של הבסיס
    nlines = ['<h1>%s</h1>' % ('הערות על ספרא דצניעותא עם ביאור הגר"א'), '']
    links = []
    n = 0
    path = {}          # רמה → כותרת נוכחית בבסיס
    written = {}       # רמה → כותרת שנכתבה בהערות
    seen_ids = set()
    for i, h in enumerate(out):
        m = HEAD_RX.match(h)
        if m:
            lvl = int(m.group(1))
            path[lvl] = h
            for k in list(path):
                if k > lvl:
                    del path[k]
            continue
        if FNCH not in h:
            continue

        def rep(mm):
            nonlocal n
            fid = mm.group(1)
            assert fid not in seen_ids, fid
            seen_ids.add(fid)
            n += 1
            # כותרות: מ-h2 ומטה (ה-h1 של הבסיס אינו נכתב שוב)
            lv = [k for k in sorted(path) if k >= 2]
            for k in lv:
                if written.get(k) != path[k]:
                    nlines.append(path[k])
                    written[k] = path[k]
                    for z in list(written):
                        if z > k:
                            del written[z]
            body = notes[fid]
            assert body, fid
            nlines.append('<sup>%d</sup> %s' % (n, body))
            links.append({'line_index_1': i + 1, 'heRef_2': 'הערות',
                          'path_2': NTITLE + '.txt', 'line_index_2': len(nlines),
                          'Conection Type': 'footnotes'})
            return '<sup>%d</sup>' % n
        h = re.sub(FNCH + r'(\d+)' + FNCH, rep, h)
        # רווח כפול לפני הסמן (שם עמדה ההפניה ב-docx) → רווח אחד מכל צד
        h = re.sub(r'  (<sup>\d+</sup>)(?=\S)', r' \1 ', h)
        # רווח שעמד במקום ההפניה לפני סימן פיסוק ("כו' ." ב-docx הישן) → צמוד
        h = re.sub(r' (<sup>\d+</sup>)(?=[.,:;)\]])', r'\1', h)
        out[i] = h

    # תיקוני הטקסט המאושרים (ר' --show): "התהו" → "התוהו" בשתי הכותרות
    for i, h in enumerate(out):
        if HEAD_RX.match(h) and 'עולם התהו והתיקון' in h:
            out[i] = h.replace('עולם התהו והתיקון', 'עולם התוהו והתיקון')

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, TITLE + '.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    with open(os.path.join(a.out, NTITLE + '.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(nlines) + '\n')
    with open(os.path.join(a.out, TITLE + '_links.json'), 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('base lines', len(out), 'notes', n, 'note lines', len(nlines),
          'unused notes', sorted(set(notes) - seen_ids, key=int))


if __name__ == '__main__':
    main()
