"""הכנסת ה"פתיחה" של חלק א לראש מדרש חופת אליהו, מתוך "קובץ 1 .doc".

build.py השמיט את הפתיחה (פסוק הירושלמי "ואמר רבי אבהו, כתיב משפחות סופרים" והמבוא
הכללי "ספר 'ילקוט מדרשים - אוצר מדרשי חז"ל'"), ולכן הערות המבוא בספר ההערות התחילו
ב־15. הסקריפט מכניס אותה לפני "שם הספר וזמנו", כמו בסדר הדפוס, עם הערותיה 1-14
ב־`הערות במספרים על` (תחת `<h2>פתיחה</h2>`, לפני הערה 15), ומזיז את כל הקישורים
שאחרי נקודת ההכנסה. העיצוב (מודגש, אותיות קטנות) נלקח מה־.doc כמו ב־build_g.py;
מראה המקום של הפסוק עובר ל־<small>. רץ פעם אחת: אם הפתיחה כבר בספר הוא נעצר.

    python3 -I patch_petiha.py "~/Downloads/מדרשים/ילקוט מדרשים א/קובץ 1 .doc" ../../..
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_g import SEP, fmt, load_doc, load_html, merge_para, norm, render_chars, \
    split_soft_breaks  # noqa: E402

BOOK = 'מדרש חופת אליהו (ילקוט מדרשים)'
COMP = 'הערות במספרים על ' + BOOK
AT = 4                 # שורת "<h2>שם הספר וזמנו</h2>" בספר ובספר ההערות
HEAD = '<h2>פתיחה</h2>'
NEXT = '<h2>שם הספר וזמנו</h2>'
CITE = re.compile(r'^\([^()]+\)$')        # מראה מקום בשורה משלו

sups = lambda s: re.findall(r'<sup>(\d+)</sup>', s)


def main(doc, root):
    folder = os.path.join(root, 'MoreBooks/ספרים/אוצריא/מדרש/אגדה/ילקוט מדרשים/חלק א')
    bpath = os.path.join(folder, BOOK + '.txt')
    cpath = os.path.join(folder, COMP + '.txt')
    lpath = os.path.join(root, 'MoreBooks/links', BOOK + '_links.json')
    base = open(bpath, encoding='utf-8').read().split('\n')[:-1]
    comp = open(cpath, encoding='utf-8').read().split('\n')[:-1]
    links = json.load(open(lpath, encoding='utf-8'))
    assert HEAD not in base and HEAD not in comp, 'הפתיחה כבר הוכנסה'
    assert base[AT - 1] == NEXT and comp[AT - 1] == NEXT
    assert comp[AT].startswith('<sup>15</sup> ')
    assert not any(n in map(str, range(1, 15)) for l in base[:131] for n in sups(l))

    # ה־.doc, כמו convert_file ב־build_g.py
    html = os.path.join(tempfile.mkdtemp(), 'k1.html')
    subprocess.run(['textutil', '-convert', 'html', '-output', html, doc],
                   check=True, capture_output=True)
    dmain, notes = load_doc(doc)
    hparas = load_html(html)
    dparas = dmain.split('\r')
    if dparas[-1] == '':
        dparas.pop()
    assert len(notes) == 17
    plain = [re.sub(r'\s+', ' ', d.replace('\x02', '')).strip() for d in dparas]
    first = plain.index('פתיחה')
    last = plain.index('שם הספר וזמנו.')
    assert plain[first + 2].startswith('ואמר רבי אבהו, כתיב משפחות סופרים')
    counter = [0]
    new = [HEAD]
    for k in range(first + 1, last):
        dp, hp = dparas[k], hparas[k]
        assert norm(dp) == norm(''.join(c[0] for c in hp['chars'])), k
        if not norm(dp) and '\x02' not in dp:
            continue
        chars = merge_para(dp, hp, keep_small=not hp['center'])
        for seg in split_soft_breaks(chars):
            text = render_chars(seg, [], counter)
            if CITE.match(text):
                text = '<small>%s</small>' % text
            new.append(SEP % text if hp['center'] else text)
    assert counter[0] == 14
    assert [int(n) for l in new for n in sups(l)] == list(range(1, 15))

    # ההערות: פסקאות ה־HTML שאחרי הטקסט הראשי, כמו ב־convert_file
    rest = hparas[len(dparas):]
    j = 0
    fnotes = []
    for raw in notes:
        out = []
        for para in raw.split('\r'):
            if not norm(para):
                continue
            while norm(''.join(c[0] for c in rest[j]['chars'])) != norm(para):
                j += 1
            out.append(fmt(merge_para(para.replace('\x02', ''), rest[j], keep_small=False)))
            j += 1
        fnotes.append('<br>'.join(out))
    # הערות 15-17 כבר בספר, מהמקור של אוצריא: אותו נוסח בדיוק = אותו עיצוב
    assert ['<sup>%d</sup> %s' % (n, fnotes[n - 1]) for n in (15, 16, 17)] == comp[AT:AT + 3]
    cnew = [HEAD] + ['<sup>%d</sup> %s' % (n, fnotes[n - 1]) for n in range(1, 15)]

    nb, nc = len(new), len(cnew)
    for r in links:
        if r['line_index_1'] >= AT:
            r['line_index_1'] += nb
        if r['path_2'] == COMP + '.txt' and r['line_index_2'] >= AT:
            r['line_index_2'] += nc
    recs = []
    for i, l in enumerate(new, AT):
        for n in sups(l):
            recs.append({'line_index_1': i, 'heRef_2': '%s %s' % (COMP, n),
                         'path_2': COMP + '.txt', 'line_index_2': AT + int(n),
                         'Conection Type': 'footnotes'})
    base = base[:AT - 1] + new + base[AT - 1:]
    comp = comp[:AT - 1] + cnew + comp[AT - 1:]
    links = recs + links
    with open(bpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(base) + '\n')
    with open(cpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(comp) + '\n')
    with open(lpath, 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=1)
    print('inserted base %d lines, notes %d lines; base %d, notes %d, links %d'
          % (nb, nc, len(base), len(comp), len(links)))


if __name__ == '__main__':
    main(os.path.expanduser(sys.argv[1]), sys.argv[2])
