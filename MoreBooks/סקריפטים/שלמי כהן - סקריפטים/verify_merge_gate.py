#!/usr/bin/env python3
"""פורט של חוזה המיזוג של SeforimLibrary (Generator.buildHearotMergePlans + HearotCompanionMerge.mergeLines).

כישלון של תנאי אחד מפיל את הכרך כולו *בשקט* (ספר ההערות נשאר עצמאי) - ADDING_BOOKS.md סעיף 3.
הבדיקה כאן מדמה את המיזוג ומוודאת שכל הערה נשתלת במקום הסמן שלה (anchored in place), ואף אחת לא מצורפת לסוף.
הרצה: python3 -I verify_merge_gate.py --root <MoreBooks>
"""
import argparse
import json
import re
import sys
from pathlib import Path

NOTE_SMALL_SUP = re.compile(r'^﻿?<small><sup>([^<]+)</sup>\s*')
NOTE_SUP = re.compile(r'^﻿?<sup(?:\s[^>]*)?>([^<]+)</sup>\s*')
NOTE_BARE = re.compile(r'^﻿?(\d+)\s+')
HEADING = re.compile(r'^﻿?<h[1-6]', re.I)
PREFIX = 'הערות על '


def parse_leading(note):
    m = NOTE_SMALL_SUP.match(note)
    if m:
        rest = note[m.end():].rstrip()
        return (m.group(1), rest[:-len('</small>')].rstrip()) if rest.endswith('</small>') else None
    m = NOTE_SUP.match(note)
    if m:
        return m.group(1), note[m.end():]
    m = NOTE_BARE.match(note)
    if m:
        return m.group(1), note[m.end():]
    return None


def find_anchor(line, token, consumed):
    esc = re.escape(token)
    pats = [re.compile(f'<sup>{esc}</sup>'), re.compile(f'<sup\\s[^>]*>{esc}</sup>'),
            re.compile(f'<small\\s[^>]*>\\s*{esc}\\s*</small>')]
    hits = [m.span() for p in pats for m in p.finditer(line)]
    hits = [h for h in hits if all(not (c[0] < h[1] and h[0] < c[1]) for c in consumed)]
    return min(hits, key=lambda h: h[0]) if hits else None


def check_pair(base_path: Path, notes_path: Path, links_path: Path):
    errs = []
    base = base_path.read_text(encoding='utf-8').lstrip('﻿').split('\n')
    notes = notes_path.read_text(encoding='utf-8').lstrip('﻿').split('\n')
    if base and base[-1] == '':
        base.pop()
    if notes and notes[-1] == '':
        notes.pop()
    links = json.loads(links_path.read_text(encoding='utf-8'))
    title = notes_path.stem
    if not title.startswith(PREFIX) or title.startswith('הערות על חברותא'):
        errs.append(f'שם ספר ההערות אינו ניתן למיזוג: {title}')
    if title != PREFIX + base_path.stem:
        errs.append(f'שם ספר ההערות אינו "הערות על " + שם הבסיס: {title}')
    seen = set()
    entries = []
    for e in links:
        if e.get('path_2') != title + '.txt':
            errs.append(f'path_2 שגוי: {e.get("path_2")}')
        if e.get('Conection Type') != 'footnotes':
            errs.append(f'סוג קישור: {e.get("Conection Type")}')
        if 'ref_2' in e or 'ref_1' in e:
            errs.append('ref_1/ref_2 אסורים בקישור למקומי')
        if any(k in e for k in ('line_index_1_end', 'line_index_2_end', 'start', 'end')):
            errs.append('קישור טווח/עוגן-מילה')
        key = (e['line_index_1'], e['line_index_2'])
        if key in seen:
            errs.append(f'קישור כפול {key}')
        seen.add(key)
        entries.append(e)
    if any(not (1 <= e['line_index_1'] <= len(base)) or not (1 <= e['line_index_2'] <= len(notes)) for e in entries):
        errs.append('אינדקס מחוץ לטווח')
        return errs, 0, 0
    referenced = {e['line_index_2'] - 1 for e in entries}
    unlinked = [j + 1 for j, l in enumerate(notes) if j not in referenced and l.strip() and not HEADING.match(l)]
    if unlinked:
        errs.append(f'{len(unlinked)} שורות הערה בלי קישור (ראשונות: {unlinked[:5]})')
    for j in referenced:
        n = notes[j]
        if not n.strip():
            errs.append(f'הערה ריקה מקושרת: {j + 1}')
        elif re.search(r'</?i[ >]', n):
            errs.append(f'<i> בהערה {j + 1}')
        elif HEADING.match(n):
            errs.append(f'הערה-כותרת מקושרת: {j + 1}')
    by_line = {}
    for e in sorted(entries, key=lambda e: e['line_index_2']):
        by_line.setdefault(e['line_index_1'] - 1, []).append(notes[e['line_index_2'] - 1])
    inplace = appended = 0
    for idx, ns in by_line.items():
        line = base[idx]
        if 'class="footnote' in line:
            errs.append(f'שורת בסיס {idx + 1} כבר נושאת הערות מוטבעות')
            continue
        if HEADING.match(line):
            errs.append(f'קישור לשורת כותרת בבסיס: {idx + 1}')
        consumed = []
        for n in ns:
            p = parse_leading(n)
            a = find_anchor(line, p[0], consumed) if p else None
            if p and a:
                consumed.append(a)
                inplace += 1
            else:
                appended += 1
                errs.append(f'הערה בלי עוגן בשורה {idx + 1}: {n[:40]}')
                break
    return errs, inplace, appended


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, type=Path, help='שורש MoreBooks')
    args = ap.parse_args(argv)
    cat = args.root / 'ספרים/אוצריא/תלמוד בבלי/מראי מקומות/שלמי כהן'
    bad = 0
    for base in sorted(p for p in cat.glob('שלמי כהן *.txt')):
        notes = cat / (PREFIX + base.name)
        links = args.root / 'links' / (base.stem + '_links.json')
        errs, ip, ap_ = check_pair(base, notes, links)
        print(f'{base.stem}: נשתלו במקומן {ip}, צורפו לסוף {ap_}', 'תקין' if not errs else '!! ' + '; '.join(errs[:5]))
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
