"""השלמת "ליקוטים והוספות למדרש חופת אליהו" (חלק א) מתוך קובץ חלק ג.

הקטע שמשורה 893 בספר חלק א הוא נוסח חלק ג (במהדורה המאוחדת של המו"ל), אבל חסרים בו:
  - "פתח דבר" (הערה 1, שבחלק א הייתה רק "לא הדפסתי בזה מחוסר מקום");
  - סמן הערה בסוף סעיף [מ] (רבנו הקדוש ואנטונינוס) והערתו;
  - הסעיפים שהמחבר העתיק "כאן שנית" עם הערות חדשות: [ג], [ט] (אחרי [נד]) ו־[כג]-[כז]
    (אחרי [יט]), כל קבוצה עם מפריד אחריה כמו בדפוס.
הסקריפט מכניס אותם, ממספר מחדש את ההערות של הקטע לפי חלק ג (1-135), ובונה מחדש את
הקישורים של הקטע. הערות שכבר היו בחלק א נשארות בנוסח חלק א (שם הוסרו בכוונה הפניות
לעמודי הדפוס של חלק ג). רץ פעם אחת: אם הקטע כבר מושלם הוא נעצר.

    python3 patch_hupa.py SRC_DIR REPO_ROOT
"""
import json
import os
import re
import subprocess
import sys
import tempfile

from build_g import SEP, convert_file, render_chars

FILE = 'הוספות למדרש חופת אליהו'
BOOK = 'מדרש חופת אליהו (ילקוט מדרשים)'
COMP = 'הערות במספרים על ' + BOOK
START = 893            # שורת הכותרת הממורכזת של קטע חלק ג
COMP_START = 105       # הערה 1 של הקטע בספר ההערות
ORNAMENT = SEP % '☙ ☙ ☙ ❧ ❧ ❧'
# מספר הערה בחלק א -> מספר בחלק ג
OLD2NEW = {**{n: n for n in range(1, 76)}, **{n: n + 1 for n in range(76, 120)},
           120: 125, 121: 126, 122: 127, 123: 128, 124: 135}
NEW_NOTES = {1, 76, 121, 122, 123, 124, 129, 130, 131, 132, 133, 134}
# (אחרי שורה בחלק א, פסקאות חלק ג להכנסה)
INSERTS = [(934, [42, 43]), (944, [55, 56, 57, 58, 59])]
CITE = re.compile(r'\((?:שם|(?:[א-ת"\'.]+ ){1,2}[א-ת"\'.]+,? ?[א-ת"\' -]*)\)')

letters = lambda s: re.sub(r'[^א-ת]', '', re.sub(r'<[^>]+>', '', s))
sups = lambda s: re.findall(r'<sup>(\d+)</sup>', s)


def main(src, root):
    folder = os.path.join(root, 'MoreBooks/ספרים/אוצריא/מדרש/אגדה/ילקוט מדרשים/חלק א')
    bpath = os.path.join(folder, BOOK + '.txt')
    cpath = os.path.join(folder, COMP + '.txt')
    lpath = os.path.join(root, 'MoreBooks/links', BOOK + '_links.json')
    base = open(bpath, encoding='utf-8').read().split('\n')[:-1]
    comp = open(cpath, encoding='utf-8').read().split('\n')[:-1]
    links = json.load(open(lpath, encoding='utf-8'))
    assert len(base) == 946 and sups(base[START - 1]) == ['1'] and sups(base[-2]) == ['124'], \
        'הקטע כבר שונה'
    assert comp[COMP_START - 1].startswith('<sup>1</sup> את הפתח דבר לא הדפסתי')
    assert all(r['path_2'] == COMP + '.txt' for r in links if r['line_index_1'] >= START)
    # חלק ג, מעובד כמו בשאר הספרים של חלק ג
    html_dir = tempfile.mkdtemp()
    subprocess.run(['textutil', '-convert', 'html', '-output',
                    os.path.join(html_dir, FILE + '.html'),
                    os.path.join(src, FILE + '.doc')], check=True, capture_output=True)
    items, notes = convert_file(src, FILE, {}, html_dir)
    counter = [0]
    paras = []
    for kind, payload, extra in items:
        assert kind == 'line'
        if extra == 'sep':
            paras.append(SEP % payload)
            continue
        text = render_chars(payload, [], counter)
        paras.append(SEP % text if extra == 'center' else text)
    assert counter[0] == len(notes) == 135 and len(paras) == 63

    def renumber(line):
        return re.sub(r'<sup>(\d+)</sup>', lambda m: '<sup>%d</sup>' % OLD2NEW[int(m.group(1))],
                      line)

    def inserted(k):
        """פסקה k של חלק ג; אם הנוסח זהה לשורה קיימת בחלק א - בעיצוב של חלק א."""
        new = paras[k]
        nums = sups(new)
        for old in base[:START - 1]:
            if letters(old) == letters(new) and len(sups(old)) == len(nums):
                pos = lambda s: [len(letters(x)) for x in re.split(r'<sup>\d+</sup>', s)[:-1]]
                if pos(old) == pos(new):
                    it = iter(nums)
                    return re.sub(r'<sup>\d+</sup>', lambda m: '<sup>%s</sup>' % next(it), old)
        return CITE.sub(lambda m: '<small>%s</small>' % m.group(0), new)

    seg = []
    for no, line in enumerate(base[START - 1:], START):
        line = renumber(line)
        if no == 916:                       # סוף [מ]: הסמן שנשמט בחלק א
            assert line.endswith('גמליאל.')
            line = line[:-1] + '<sup>76</sup>.'
        seg.append(line)
        for after, ks in INSERTS:
            if no == after:
                assert base[no - 1] == ORNAMENT
                seg += [inserted(k) for k in ks] + [ORNAMENT]
    order = [int(n) for l in seg for n in sups(l)]
    assert order == list(range(1, 136)), order

    old_notes = comp[COMP_START - 1:]
    assert len(old_notes) == 124
    by_new = {}
    for l in old_notes:
        m = re.match(r'<sup>(\d+)</sup> ', l)
        by_new[OLD2NEW[int(m.group(1))]] = l[m.end():]
    assert 'והוא<b>שמלכות' in by_new[75]          # מילים דבוקות בחלק א; בחלק ג: "והוא, שמלכות"
    by_new[75] = by_new[75].replace('והוא<b>שמלכות', 'והוא, <b>שמלכות')
    assert set(by_new) | NEW_NOTES == set(range(1, 136)) and not set(by_new) & NEW_NOTES - {1}
    cseg = ['<sup>%d</sup> %s' % (n, notes[n - 1].strip() if n in NEW_NOTES else by_new[n])
            for n in range(1, 136)]

    base = base[:START - 1] + seg
    comp = comp[:COMP_START - 1] + cseg
    links = [r for r in links if r['line_index_1'] < START]
    for i, l in enumerate(base[START - 1:], START):
        for n in sups(l):
            links.append({'line_index_1': i, 'heRef_2': '%s %s' % (COMP, n),
                          'path_2': COMP + '.txt', 'line_index_2': COMP_START + int(n) - 1,
                          'Conection Type': 'footnotes'})
    with open(bpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(base) + '\n')
    with open(cpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(comp) + '\n')
    with open(lpath, 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=1)
    print('base lines %d, notes %d, links %d' % (len(base), len(comp), len(links)))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
