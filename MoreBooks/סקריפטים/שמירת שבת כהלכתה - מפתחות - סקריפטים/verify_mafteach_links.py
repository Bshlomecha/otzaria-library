#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""בודק שכל קישור ב"שמירת שבת כהלכתה - מפתחות" עדיין נוחת במקום הנכון.

הקישורים כתובים בגוף הספר כ־<a href="otzaria://inline-link?path=…&index=N&ref=…">, והם
מצביעים על מספר שורה קבוע (1-based) ב"שמירת שבת כהלכתה - א". שום CI אינו מעדכן אותם,
ולכן כל עריכה שמוסיפה או מוחקת שורה בספר הבסיס מזיזה אותם. הפרמטר ref מתאר את היעד
("שמירת שבת כהלכתה, [מבוא להלכות שבת, ]פרק X סעיף Y" / "סעיפים Y-Z" / "הערה Y"),
והסקריפט מוודא שהשורה N היא אכן אותו סעיף (או נושאת את סמן ההערה) באותו פרק.

הרצה משורש המאגר:  python3 "MoreBooks/שמירת שבת כהלכתה - מפתחות - סקריפטים/verify_mafteach_links.py"
יוצא בקוד 1 אם נמצאה שורה שזזה.
"""
import os
import re
import sys
from urllib.parse import parse_qs, unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
DIR = os.path.join(REPO, 'MoreBooks', 'ספרים', 'אוצריא', 'הלכה', 'מחברי זמננו')
INDEX = os.path.join(DIR, 'שמירת שבת כהלכתה - מפתחות.txt')
BASE_TITLE = 'שמירת שבת כהלכתה - א'
BASE = os.path.join(DIR, BASE_TITLE + '.txt')

GV = dict(zip('אבגדהוזחטיכלמנסעפצקרשת', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90,
                                            100, 200, 300, 400]))
HREF = re.compile(r'<a href="(otzaria://inline-link\?[^"]*)">([^<]*)</a>')
HEAD = re.compile(r'^<h([1-6])>(.*?)</h\1>')
SEIF = re.compile(r'^<b><big>([א-ת]+\**)\.</big></b>')
REF = re.compile(r'^שמירת שבת כהלכתה, (מבוא להלכות שבת, )?פרק ([א-ת]+) '
                 r'(?:סעיף ([א-ת]+\**)|סעיפים ([א-ת]+\**)-([א-ת]+\**)|הערה ([א-ת]+\**))$')


def gem(s):
    return sum(GV[c] for c in s if c in GV)


def base_map(lines):
    """line (1-based) -> (part, chapter-number, seif-label or None)"""
    out, part, ch, seif = {}, None, None, None
    for n, line in enumerate(lines, 1):
        m = HEAD.match(line)
        if m:
            lvl, txt = int(m.group(1)), m.group(2)
            mc = re.match(r'פרק ([א-ת]+)', txt)
            if lvl == 2 and txt.startswith('מבוא'):
                part, ch = 'mavo', None
            elif lvl in (2, 3) and mc:
                part = 'main' if lvl == 2 else part
                ch, seif = gem(mc.group(1)), None
            elif lvl == 2:
                part, ch = None, None
            out[n] = (part, ch, None, True)
            continue
        m = SEIF.match(line)
        if m:
            seif = m.group(1)
        out[n] = (part, ch, seif if m else None, False)
    return out


def main():
    base = open(BASE, encoding='utf-8').read().split('\n')
    bmap = base_map(base)
    problems, total = [], 0
    for ln, line in enumerate(open(INDEX, encoding='utf-8').read().split('\n'), 1):
        for href, text in HREF.findall(line):
            total += 1
            q = parse_qs(urlsplit(href).query)
            path, idx, ref = unquote(q['path'][0]), int(q['index'][0]), unquote(q['ref'][0])
            m = REF.match(ref)
            err = None
            if path != BASE_TITLE + '.txt':
                err = 'path %s' % path
            elif not m:
                err = 'ref לא מפוענח'
            elif not 1 <= idx <= len(base):
                err = 'index מחוץ לספר'
            else:
                part = 'mavo' if m.group(1) else 'main'
                ch = gem(m.group(2))
                p, c, seif_here, is_head = bmap[idx]
                target = base[idx - 1]
                if is_head:
                    err = 'היעד הוא כותרת'
                elif (p, c) != (part, ch):
                    err = 'היעד בפרק אחר'
                elif m.group(6):
                    if '<sup>(%s)</sup>' % m.group(6) not in target:
                        err = 'סמן ההערה (%s) אינו בשורה' % m.group(6)
                else:
                    want = m.group(3) or m.group(4)
                    if seif_here != want:
                        err = 'השורה אינה פותחת את סעיף %s' % want
            if err:
                problems.append('%d: "%s" -> %s שורה %d: %s' % (ln, text, ref, idx, err))
    print('נבדקו %d קישורים; בעיות: %d' % (total, len(problems)))
    for p in problems[:200]:
        print('  ' + p)
    return 1 if problems or total == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
