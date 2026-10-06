#!/usr/bin/env python3
"""תקוני הזהר מסודר על פי הגר"א + ביאור הגר"א — מתוך "תקוני זוהר עם ביאור הגר''א - לאוצריא.docx".

מבנה הקלט: גוף ה-docx הוא נוסח התיקונים (מסודר מחדש על פי הגהות הגר"א), וביאור
הגר"א כולו יושב בהערות השוליים — הערה לכל דיבור המתחיל, הדיבור מודגש (bCs).

פלט:
  תקוני הזהר מסודר על פי הגרא.txt      — הבסיס, שורה לכל פסקה, בלי סמני הערות
  ביאור הגרא על תקוני הזהר.txt         — שורה לכל פסקת הערה, תחת אותן כותרות
  תקוני הזהר מסודר על פי הגרא_links.json — בשם הבסיס, commentary (כמו וילנא)

עיצוב (אפקטיבי, ר' docxfmt): bCs → <b>; גודל ≤10pt → <small>; אפור → color:gray;
תמונה → <img> data-URI. שורה עם יותר מתמונה אחת מפוצלת לפני כל תמונה נוספת
(מלכודת ההיפוך RTL: שתי "תיבות" בשורה מתחלפות במקומן).

    python3 tz_build.py --docx-dir <unzipped> --out <dir>
"""
import argparse
import base64
import json
import os
import re
import sys

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docxfmt import W, Styles, esc, pstyle, segments  # noqa: E402

BASE = 'תקוני הזהר מסודר על פי הגרא'
BASE_H1 = 'תקוני הזהר מסודר על פי הגר"א'
COMM = 'ביאור הגרא על תקוני הזהר'
COMM_H1 = 'ביאור הגר"א על תקוני הזהר'
COMM_AUTHOR = 'רבי אליהו בן שלמה זלמן מווילנא'   # כמו "ביאור הגרא על תיקונים מזוהר חדש"
GREY = {'A6A6A6', '808080', '7F7F7F', 'BFBFBF', 'ACB9CA', '8496B0'}

# פסקאות בסגנון כותרת שאינן כותרות: גוף טקסט (עם הפניות להערות) / ריקות / חתימה
NOT_HEADING_BODY = {1441, 1655}
DROP = {2457, 2458}
PLAIN_LINE = {2456}                 # "תם ונשלם – שבח לאל בורא עולם:"
# תתי-פרקים: ילדי "תקונים מזהר חדש" ונספח "מאמר קו המדה"
H3_RANGES = [(2027, 2455), (2460, 10 ** 9)]


def rels(root, part):
    x = etree.parse(root + '/word/_rels/%s.xml.rels' % part).getroot()
    out = {}
    for r in x:
        out[r.get('Id')] = r.get('Target')
    return out


def img_tag(root, target):
    path = os.path.join(root, 'word', target)
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}[ext]
    data = base64.b64encode(open(path, 'rb').read()).decode()
    return '<img src="data:%s;base64,%s" alt="ציור">' % (mime, data)


def render(segs, imgsrc):
    """סגמנטים → רשימת שורות HTML (פיצול לפני כל תמונה שנייה ואילך),
    ולכל שורה רשימת מזהי ההערות שבה."""
    lines = [[[], []]]          # [parts, fn ids]
    n_img = 0
    cur = None                  # (b, small, grey, u)
    buf = []

    def flush():
        nonlocal buf, cur
        if buf:
            t = ''.join(buf)
            b, sm, g, u = cur
            lead = t[:len(t) - len(t.lstrip())]
            trail = t[len(t.rstrip()):]
            core = esc(t.strip())
            if core:
                if u:
                    core = '<u>%s</u>' % core
                if sm:
                    core = '<small>%s</small>' % core
                if g:
                    core = '<span style="color:gray">%s</span>' % core
                if b:
                    core = '<b>%s</b>' % core
                lines[-1][0].append(lead + core + trail)
            else:
                lines[-1][0].append(t)
        buf = []

    for s in segs:
        if s[0] == 't':
            f = s[2]
            k = (f['bold'], f['sz'] <= 20, (f['color'] or '').upper() in GREY, f['u'])
            if not s[1].strip() and cur is not None:
                buf.append(s[1])          # רווח — לא שובר את התג
                continue
            if k != cur:
                flush()
                cur = k
            buf.append(s[1])
        elif s[0] == 'fn':
            flush()
            lines[-1][1].append(s[1])
            lines[-1][0].append(' ')
        elif s[0] == 'br':
            flush()
            lines[-1][0].append('<br>')
        elif s[0] == 'img':
            flush()
            n_img += 1
            if n_img > 1:
                lines.append([[], []])
            lines[-1][0].append(imgsrc(s[1]))
    flush()
    out = []
    for parts, fns in lines:
        h = ''.join(parts)
        h = re.sub(r'\s+', ' ', h).strip()
        h = re.sub(r'</b>(\s*)<b>', r'\1', h)
        h = re.sub(r'^(?:<br>\s*)+|(?:\s*<br>)+$', '', h)
        out.append((h, fns))
    return out


def head_text(segs):
    t = ''.join(s[1] for s in segs if s[0] == 't')
    t = re.sub(r'\s+', ' ', t).strip()
    return esc(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--docx-dir', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    root = a.docx_dir
    st = Styles(root)
    imgcache = {}

    def imgsrc_for(part):
        rl = rels(root, part)

        def imgsrc(rid):
            if rl[rid] not in imgcache:
                imgcache[rl[rid]] = img_tag(root, rl[rid])
            return imgcache[rl[rid]]
        return imgsrc
    note_img, body_img = imgsrc_for('footnotes'), imgsrc_for('document')

    # הערות השוליים
    fx = etree.parse(root + '/word/footnotes.xml').getroot()
    notes = {}
    for f in fx.iter(W + 'footnote'):
        fid = f.get(W + 'id')
        if int(fid) <= 1:
            continue
        paras = []
        for p in f.iter(W + 'p'):
            segs = [s for s in segments(p, st) if s[0] != 'fnref']
            for h, fns in render(segs, note_img):
                assert not fns
                if h:
                    paras.append(h)
        notes[fid] = paras

    body = etree.parse(root + '/word/document.xml').getroot().find(W + 'body')
    ps = list(body.iter(W + 'p'))
    base = ['<h1>%s</h1>' % BASE_H1, '']
    comm = ['<h1>%s</h1>' % COMM_H1, COMM_AUTHOR]
    links = []
    path = {}       # רמה → כותרת בבסיס
    written = {}    # רמה → כותרת שנכתבה בביאור
    used = []
    for i, p in enumerate(ps):
        if i == 0 or i in DROP:
            continue          # כותרת הספר → h1
        name = st.name(pstyle(p)) if pstyle(p) else ''
        segs = segments(p, st)
        if name == 'heading 2' and i not in NOT_HEADING_BODY and i not in PLAIN_LINE:
            assert not any(s[0] == 'fn' for s in segs), i
            lvl = 3 if any(x <= i <= y for x, y in H3_RANGES) else 2
            h = '<h%d>%s</h%d>' % (lvl, head_text(segs), lvl)
            assert head_text(segs), i
            base.append(h)
            path[lvl] = h
            for k in list(path):
                if k > lvl:
                    del path[k]
            continue
        for h, fns in render(segs, body_img):
            if not h:
                assert not fns, i
                continue
            if i in PLAIN_LINE:
                h = '<b>%s</b>' % re.sub(r'<[^>]+>', '', h)
            base.append(h)
            bl = len(base)
            for fid in fns:
                used.append(fid)
                for k in sorted(path):
                    if written.get(k) != path[k]:
                        comm.append(path[k])
                        written[k] = path[k]
                        for z in list(written):
                            if z > k:
                                del written[z]
                for np_ in notes[fid]:
                    comm.append(np_)
                    links.append({'line_index_1': bl, 'line_index_2': len(comm),
                                  'heRef_2': 'ביאור הגר"א', 'path_2': COMM + '.txt',
                                  'Conection Type': 'commentary'})
    assert len(used) == len(set(used))
    missing = sorted(set(notes) - set(used), key=int)
    empty = [f for f in used if not notes[f]]
    os.makedirs(a.out, exist_ok=True)
    for t, lines in ((BASE, base), (COMM, comm)):
        with open(os.path.join(a.out, t + '.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    with open(os.path.join(a.out, BASE + '_links.json'), 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('base lines', len(base), 'comm lines', len(comm), 'links', len(links),
          'notes used', len(used), 'unused', missing, 'empty', empty, 'images', len(imgcache))


if __name__ == '__main__':
    main()
