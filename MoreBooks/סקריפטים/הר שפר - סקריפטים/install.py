"""מתקין את "הר שפר" (מהדורת תשפ"ה) בעץ הריפו ומעדכן את המרשמים.

--src הוא תיקיית הפלט של assemble_book.py (הר שפר.txt, הערות על הר שפר.txt, הר שפר_links.json).
בלי --apply לא נכתב דבר.

הספר נשמר באותו נתיב יחסי כמו עותק דיקטה הקודם (תלמוד בבלי/אחרונים/הר שפר.txt):
MoreBooks מאוחר ב־BOOK_ROOTS ולכן דורס אותו בארכיון. הרשומות הקיימות של "הר שפר" נשארות
(metadata.json, ForDB/book_info.csv); מתעדכנים רק Sourcefolder ב־ForDB/all_metadata.json
ושורת התיאור ב־ForDB/sefaria_metadata_changes.csv.
"""
import argparse
import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path

# MoreBooks/סקריפטים/<ספר>/install.py: שורש הריפו נמצא שלוש תיקיות מעל
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".github" / "scripts"))
from book_info_writer import plan_registration, apply_registration
from validate_fordb_book_names import db_title as normalize_book_title

REPO = str(REPO_ROOT)
BOOK_DIR = os.path.join(REPO, 'MoreBooks/ספרים/אוצריא/תלמוד בבלי/אחרונים')
LINKS_DIR = os.path.join(REPO, 'MoreBooks/links')
CATEGORY = os.path.relpath(BOOK_DIR, os.path.join(REPO, 'MoreBooks/ספרים/אוצריא'))
TITLE = 'הר שפר'
NOTES_TITLE = 'הערות על ' + TITLE
AUTHOR = 'שמואל פירר'
GENERATION = 'אחרונים'

SHORT_DESC = ('חידושים ופלפולים על מסכת הוריות, ובצירוף חידושי תורה על סוגיות הש"ס ומדרשים — '
              'מאת הגאון רבי שמואל פירר אב"ד קראס (גליציה). מהדורה חדשה.')
LONG_DESC = ('ספרו של הגאון רבי שמואל פירר הי"ד, אב"ד קראס, על מסכת הוריות: פלפולים מקיפים על סוגיות '
             'המסכת לפי סדר הדפים, ובצירוף חידושי תורה על סוגיות הש"ס ומדרשים ותשובות בהלכה. '
             'במהדורה החדשה (תשפ"ה) נוספו פתח דבר ותולדות חיי המחבר, חלוקה לקטעים ולכותרות, '
             'ומאות מראי מקומות.')

DESC_CSV_HEADER = ['categoryPath', 'title', 'author', 'heShortDesc', 'heDesc', 'heDescNew']


def normalize_hebrew_label(raw):
    """Mirror of normalizeHebrewLabel in SeforimLibrary (the title key of sefaria_metadata_changes.csv)."""
    s = raw.strip()
    s = s.replace('“', '"').replace('”', '"')
    s = s.replace('‘', "'").replace('’', "'")
    s = s.replace('"', '״').replace("''", '״')
    s = s.replace('׳׳', '״').replace('`', '׳')
    return re.sub(r'\s+', ' ', s).strip()


def upsert_description(rows, title, category, author, short, long_):
    hits = [i for i, r in enumerate(rows) if i and len(r) > 1 and r[1].strip() == title]
    if not hits:
        rows.append([category or '', title, author or '', short or '', '', long_ or ''])
        return 'add'
    row = rows[hits[-1]]
    old = list(row)
    row += [''] * (len(DESC_CSV_HEADER) - len(row))
    for idx, val in ((0, category), (2, author), (3, short), (5, long_)):
        if val:
            row[idx] = val
    return 'update' if row != old else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, type=Path, help='the output directory of assemble_book.py')
    ap.add_argument('--apply', action='store_true', help='write into the repo (default is a dry run)')
    a = ap.parse_args()

    files = {'book': a.src / f'{TITLE}.txt', 'notes': a.src / f'{NOTES_TITLE}.txt',
             'links': a.src / f'{TITLE}_links.json'}
    for k, p in files.items():
        if not p.is_file():
            raise SystemExit(f'--src is missing {p.name}')

    meta_path = os.path.join(REPO, 'metadata.json')
    meta = json.load(open(meta_path, encoding='utf-8'))
    have = {m['title'] for m in meta}
    all_path = os.path.join(REPO, 'ForDB/all_metadata.json')
    all_text = open(all_path, encoding='utf-8').read()
    all_meta = json.loads(all_text)
    all_have = {m['title'] for m in all_meta}
    # a merged companion stops being a book: it must have no metadata row at all
    if NOTES_TITLE in have or NOTES_TITLE in all_have:
        raise SystemExit('companion notes book must not have a metadata row')
    # הזהות הקיימת ב־book_info.csv היא (הר שפר, מחבר ריק, אחרונים) — לא מוסיפים זהות שנייה
    csv_plan = plan_registration(REPO, [[normalize_book_title(TITLE), '', GENERATION, '', '', '']])
    desc_path = os.path.join(REPO, 'ForDB/sefaria_metadata_changes.csv')
    with open(desc_path, encoding='utf-8', newline='') as f:
        descs = list(csv.reader(f))
    if not descs or descs[0] != DESC_CSV_HEADER:
        raise SystemExit('%s: unexpected header' % desc_path)
    desc_change = upsert_description(descs, normalize_hebrew_label(TITLE), CATEGORY, AUTHOR, SHORT_DESC, LONG_DESC)

    entry = next((m for m in all_meta if m['title'] == TITLE), None)
    sf_change = bool(entry) and entry.get('Sourcefolder') != 'MoreBooks'
    print('target:', BOOK_DIR)
    print('metadata.json row exists: %s   all_metadata row exists: %s' % (TITLE in have, TITLE in all_have))
    print('all_metadata Sourcefolder -> MoreBooks: %s' % sf_change)
    print('desc csv: %s' % desc_change)
    if not a.apply:
        print('\ndry run -- nothing written. Re-run with --apply.')
        return

    os.makedirs(BOOK_DIR, exist_ok=True)
    os.makedirs(LINKS_DIR, exist_ok=True)
    shutil.copyfile(files['book'], os.path.join(BOOK_DIR, files['book'].name))
    shutil.copyfile(files['notes'], os.path.join(BOOK_DIR, files['notes'].name))
    shutil.copyfile(files['links'], os.path.join(LINKS_DIR, files['links'].name))
    if TITLE not in have:
        meta.append({'title': TITLE, 'author': AUTHOR, 'pubDate': None, 'pubPlace': None,
                     'compPlace': None, 'compDate': None, 'תיאור_חדש': None, 'heShortDesc': None,
                     'heDesc': None, 'Unnamed: 9': None, 'order': None})
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write('[\n' + ',\n'.join(json.dumps(m, ensure_ascii=False, separators=(',', ':'))
                                       for m in meta) + '\n]\n')
    if sf_change:
        # עריכה כירורגית של הרשומה בלבד: שאר הקובץ לא נכתב מחדש
        i = all_text.index('"title": "%s",' % TITLE)
        j = all_text.index('"Sourcefolder":', i)
        k = all_text.index('\n', j)
        all_text = all_text[:j] + '"Sourcefolder": "MoreBooks"' + all_text[k:]
        with open(all_path, 'w', encoding='utf-8') as f:
            f.write(all_text)
    apply_registration(REPO, csv_plan)
    if desc_change:
        with open(desc_path, 'w', encoding='utf-8', newline='') as f:
            csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n').writerows(descs)
    print('\nwrote book, notes and links')


if __name__ == '__main__':
    main()
