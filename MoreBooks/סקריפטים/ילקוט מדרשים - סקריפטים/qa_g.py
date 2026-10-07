"""בדיקת build_g.py: כל אות במקור נמצאת בספר, כל הערה בספר הנלווה, וכל קישור מצביע נכון.

    python3 qa_g.py SRC_DIR OUT_DIR
"""
import json
import os
import re
import sys

from build import COPYRIGHT
from build_g import BOOKS, SUFFIX, load_doc

src, out = sys.argv[1], sys.argv[2]
folder = os.path.join(out, 'חלק ג')
letters = lambda s: re.sub(r'[^א-ת0-9]', '', re.sub(r'<[^>]+>', '', s))
bad = 0
for title, sub, files in BOOKS:
    bt = title + SUFFIX
    ct = 'הערות במספרים על ' + bt
    base = open(os.path.join(folder, bt + '.txt'), encoding='utf-8').read().split('\n')[:-1]
    comp = open(os.path.join(folder, ct + '.txt'), encoding='utf-8').read().split('\n')[:-1]
    links = json.load(open(os.path.join(out, 'links', bt + '_links.json'), encoding='utf-8'))
    assert base[0] == '<h1>%s</h1>' % title and base[2] == COPYRIGHT and comp[2] == COPYRIGHT
    # 1. טקסט: אותיות המקור (פחות שורות 'drop' ושינויי כותרת) == אותיות הספר
    src_main, src_notes = '', []
    for fname, roles in files:
        main, notes = load_doc(os.path.join(src, fname + '.doc'))
        for para in main.split('\r'):
            plain = re.sub(r'\s+', ' ', para.replace('\x02', '')).strip()
            role = roles.get(plain, '')
            if role == 'drop':
                continue
            if role.startswith('h') and ':' in role:
                para = role.split(':', 1)[1]
            # מילת עמוד הבא (קטשווורד)
            para = re.sub(r'\x0b[\t ]*[^\s\x0b]+[\t ]*(?=\x0b|$)', '', para)
            src_main += para
        src_notes += notes
    got = letters(re.sub(r'<sup>\d+</sup>', '', '\n'.join(base[3:])))
    want = letters(src_main)
    if got != want:
        bad += 1
        i = next(k for k in range(min(len(got), len(want))) if got[k] != want[k])
        print('TEXT', title, len(got), len(want), got[i - 20:i + 20], '|', want[i - 20:i + 20])
    # 2. הערות: לפי הסדר, תוכן זהה
    cnotes = [l for l in comp[3:] if l.startswith('<sup>')]
    if len(cnotes) != len(src_notes):
        bad += 1
        print('NOTES count', title, len(cnotes), len(src_notes))
    for k, (c, s) in enumerate(zip(cnotes, src_notes), 1):
        if not c.startswith('<sup>%d</sup> ' % k) or letters(c.split('</sup>', 1)[1]) != letters(s):
            bad += 1
            print('NOTE', title, k)
    # 3. קישורים: כל סמן בספר מקושר פעם אחת, לשורה הנכונה
    marks = [(i + 1, int(m)) for i, l in enumerate(base) for m in re.findall(r'<sup>(\d+)</sup>', l)]
    if sorted(m for _, m in marks) != list(range(1, len(src_notes) + 1)):
        bad += 1
        print('MARKS', title)
    if len(links) != len(marks):
        bad += 1
        print('LINKS count', title, len(links), len(marks))
    for rec, (bl, n) in zip(links, marks):
        ok = (rec['line_index_1'] == bl and rec['heRef_2'] == '%s %d' % (ct, n)
              and rec['path_2'] == ct + '.txt' and rec['Conection Type'] == 'footnotes'
              and comp[rec['line_index_2'] - 1].startswith('<sup>%d</sup> ' % n)
              and not base[bl - 1].startswith('<h'))
        if not ok:
            bad += 1
            print('LINK', title, rec)
    # 4. רמות כותרות רציפות, ושורות הנלווה: כותרת או הערה בלבד
    lv = 1
    for l in base[3:] + comp[3:]:
        m = re.match(r'<h(\d)>', l)
        if m:
            if int(m.group(1)) > lv + 1:
                bad += 1
                print('LEVEL', title, l)
            lv = int(m.group(1))
    for l in comp[3:]:
        if not re.match(r'<h\d>|<sup>\d+</sup> ', l):
            bad += 1
            print('COMP line', title, l[:60])
    print('%-32s OK lines=%d notes=%d' % (title, len(base), len(cnotes)))
print('ERRORS', bad)
