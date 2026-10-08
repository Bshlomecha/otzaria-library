#!/usr/bin/env python3
"""בדיקת שימור: כל טוקן במקור (docx) קיים בפלט, ולהפך - בגוף הספר ובהערות, לכל מסכת.

מקור הטוקנים: אותו קורא docx של convert.py, אך הבדיקה אינה תלויה בלוגיקת הסידור/האיחוי:
משווה multiset של מילים (בלי תגים, בלי סמני הערה). הבדלים מותרים רק כשהם מוצהרים:
  - שורות כריכה (בס"ד ...), שבר תווים בסוף קובץ, כותרת 'פרק' שבורה - מוסרים בכוונה.
הרצה: python3 -I verify_conversion.py --src <תיקיית שלמי כהן> --out <MoreBooks>
"""
import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert as C  # noqa: E402

TAG = re.compile(r'<[^>]+>')
BIDI = C.BIDI


def toks(html):
    return BIDI.sub('', TAG.sub('', re.sub(r'<br\s*/?>', ' ', html))).split()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--only', nargs='*')
    args = ap.parse_args(argv)
    bad = 0
    for dirname, name in C.ALL_TRACTATES:
        if args.only and name not in args.only:
            continue
        src_body, src_notes, fn_used = collections.Counter(), collections.Counter(), 0
        docs = C.tractate_docs(args.src, dirname, name)
        # מקור: כל הפסקאות מכל הקבצים (בלי עותקים זהים), מעבר ל-merge: כך חפיפה שנמחקה בטעות תתגלה
        seen, uniq = set(), []
        for d in docs:
            sig = tuple((r, t) for r, _p, t in d.items)
            if sig not in seen:
                seen.add(sig)
                uniq.append(d)
        for d in uniq:
            for role, parts, plain in d.items:
                if role == 'cover':
                    continue
                src_body.update(toks(''.join(p[1] for p in parts if p[0] == 't')))
                for p in parts:
                    if p[0] == 'fn':
                        body = d.footnotes.get(p[1], '')
                        if body.strip():
                            src_notes.update(toks(body))
                            fn_used += 1
        title = f'{C.SERIES} {name}'
        d = args.out / C.CATEGORY
        lines = (d / f'{title}.txt').read_text(encoding='utf-8').split('\n')
        notes = (d / f'הערות על {title}.txt').read_text(encoding='utf-8').split('\n')
        lines = [l for l in lines[3:] if l]   # בלי h1 / מחבר / בס"ד
        notes = [l for l in notes if l]
        out_body, out_notes = collections.Counter(), collections.Counter()
        for l in lines:
            out_body.update(toks(re.sub(r'<sup>\d+</sup>', '', l)))
        for l in notes:
            out_notes.update(toks(re.sub(r'^<sup>\d+</sup> ', '', l)))
        db, dn = src_body - out_body, out_body - src_body
        # מותר: כותרות-דף כפולות שנמחקו בחיבורי קבצים, וכותרת 'פרק' שבורה
        dafish = re.compile(r'^(דף|פרק|[א-ת"׳\']+[.:])$')
        db = collections.Counter({t: c for t, c in db.items() if not dafish.match(t)})
        # מותר: תווית דף בלי נקודה/נקודתיים שהושלמה ('דף מו' -> 'דף מו.')
        fixed = [t for t in db if t + '.' in dn or t + ':' in dn]
        for t in fixed:
            for suffix in ('.', ':'):
                if t + suffix in dn:
                    dn[t + suffix] -= 1
                    break
            db[t] -= 1
        db, dn = +db, +dn
        nb, nn = src_notes - out_notes, out_notes - src_notes
        ok = not (db or dn or nb or nn) and fn_used == len(notes)
        print(f'{name}: גוף {sum(out_body.values())} טוקנים, הערות {len(notes)}/{fn_used} '
              f'{"תקין" if ok else "!! הבדלים"}')
        if not ok:
            bad += 1
            for lab, cnt in (('חסר בגוף', db), ('עודף בגוף', dn), ('חסר בהערות', nb), ('עודף בהערות', nn)):
                if cnt:
                    print(f'   {lab}: {sum(cnt.values())} - {list(cnt.items())[:8]}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
