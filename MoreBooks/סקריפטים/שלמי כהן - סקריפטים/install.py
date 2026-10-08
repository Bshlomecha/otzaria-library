"""Place the converted Shlomei Cohen volumes into the otzaria-library tree and register them.

--src is the output directory of convert.py (it holds ספרים/... and links/).
Without --apply nothing is written.
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
BOOK_DIR = os.path.join(
    REPO, 'MoreBooks/ספרים/אוצריא/תלמוד בבלי/מראי מקומות/שלמי כהן')
LINKS_DIR = os.path.join(REPO, 'MoreBooks/links')
# the book folder under the packaged root -- the (informational) categoryPath
# column of ForDB/sefaria_metadata_changes.csv
CATEGORY = os.path.relpath(
    BOOK_DIR, os.path.join(REPO, 'MoreBooks/ספרים/אוצריא'))
SERIES = 'שלמי כהן'
AUTHOR = 'שלמה כהנוב'
GENERATION = 'מחברי זמננו'
NOTES_PREFIX = 'הערות על '

# מסכת -> הערה על חומר שחסר בקבצי המקור (נבדק מול רצף כותרות הדפים, ראו README.md)
GAPS = {
    'כריתות': 'הכרך מסתיים בדף כד עמוד ב; סוף המסכת (דפים כה–כח) חסר.',
    'יבמות': 'דפים קז–קח חסרים.',
    'פסחים': 'חסרים הדפים עז–צא ועמוד א של דף צב.',
    'נדרים': 'עמוד א של דף סד חסר.',
    'סוכה': 'עמוד ב של דף י חסר.',
    'תמורה': 'דף ה ועמוד א של דף ו חסרים.',
}
TRACTATES = ['בבא בתרא', 'בבא מציעא', 'בבא קמא', 'בכורות', 'גיטין', 'יבמות', 'כריתות', 'כתובות',
             'מכות', 'נדרים', 'סוכה', 'ערכין', 'פסחים', 'קידושין', 'תמורה']


def short_desc(tractate):
    return f'ציונים ומראי מקומות על מסכת {tractate}, מדברי הראשונים והאחרונים, על כל דף ודף.'


def long_desc(tractate):
    text = (f'ציונים ומראי מקומות ביסודות הסוגיות ועד לפרטי כל סוגיה על מסכת {tractate}. '
            'אוצר מלא וגדוש מדברי הראשונים והאחרונים, הפוסקים ורבותינו ראשי הישיבות, '
            'ערוך בתמצית ובבהירות על כל דף ודף. נכתב עבור חבורת הדף בישיבת מיר ירושלים.')
    gap = GAPS.get(tractate)
    return f'{text} {gap}' if gap else text


# Descriptions never go into metadata.json: the generator reads it through
# BookMetadata, which has no heDesc field, so they would be silently dropped.
# ForDB/sefaria_metadata_changes.csv is the one path a description takes into
# seforim.db, for every book.
DESC_CSV_HEADER = ['categoryPath', 'title', 'author', 'heShortDesc', 'heDesc',
                   'heDescNew']


def normalize_hebrew_label(raw):
    """Mirror of normalizeHebrewLabel in SeforimLibrary: the book's title in
    seforim.db, and so the key of sefaria_metadata_changes.csv's title column."""
    s = raw.strip()
    s = s.replace('“', '"').replace('”', '"')
    s = s.replace('‘', "'").replace('’', "'")
    s = s.replace('"', '״').replace("''", '״')
    s = s.replace('׳׳', '״').replace('`', '׳')
    return re.sub(r'\s+', ' ', s).strip()


def upsert_description(rows, title, category, author, short, long_):
    """Put one book's row into the parsed sefaria_metadata_changes.csv rows.

    The consumer reads by position: title (col 2, exact match), heShortDesc
    (col 4) -> book.heShortDesc, heDescNew (col 6) -> book.heDesc. Col 5 is
    Sefaria's original text and stays empty for our books. An empty cell means
    "keep what is there", so an empty value never overwrites a filled one.
    Returns 'add', 'update', or None when the row already says all of it."""
    hits = [i for i, r in enumerate(rows)
            if i and len(r) > 1 and r[1].strip() == title]
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
    ap.add_argument('--src', required=True, type=Path,
                    help='the output directory of convert.py')
    ap.add_argument('--apply', action='store_true',
                    help='write into the repo (default is a dry run)')
    a = ap.parse_args()

    src_books = a.src / 'ספרים/אוצריא/תלמוד בבלי/מראי מקומות/שלמי כהן'
    src_links = a.src / 'links'
    books = sorted(p.name for p in src_books.glob('*.txt'))
    links = sorted(p.name for p in src_links.glob('*_links.json'))
    base_titles = [f'{SERIES} {t}' for t in TRACTATES]
    expected_books = sorted([f'{t}.txt' for t in base_titles] + [f'{NOTES_PREFIX}{t}.txt' for t in base_titles])
    expected_links = sorted(f'{t}_links.json' for t in base_titles)
    if books != expected_books or links != expected_links:
        raise SystemExit('--src does not hold exactly the 15 volumes, their notes and links:\n'
                         f'  books missing {sorted(set(expected_books) - set(books))} extra {sorted(set(books) - set(expected_books))}\n'
                         f'  links missing {sorted(set(expected_links) - set(links))} extra {sorted(set(links) - set(expected_links))}')

    # a stale --src silently overwrites good volumes with an older build
    if os.path.isdir(BOOK_DIR):
        missing = sorted(set(os.listdir(BOOK_DIR)) - set(books))
        if missing:
            raise SystemExit('%s already holds volumes absent from --src -- '
                             'stale build directory?\n  %s'
                             % (BOOK_DIR, '\n  '.join(missing)))

    meta_path = os.path.join(REPO, 'metadata.json')
    meta = json.load(open(meta_path, encoding='utf-8'))
    have = {m['title'] for m in meta}
    all_path = os.path.join(REPO, 'ForDB/all_metadata.json')
    all_meta = json.load(open(all_path, encoding='utf-8'))
    all_have = {m['title'] for m in all_meta}
    # a merged companion stops being a book: it must have no metadata row at all
    note_titles = {f'{NOTES_PREFIX}{t}' for t in base_titles}
    stray = sorted((have | all_have) & note_titles)
    if stray:
        raise SystemExit('companion notes books must not have metadata rows: %s' % stray)
    csv_plan = plan_registration(REPO, [[normalize_book_title(t), AUTHOR, GENERATION, '', '', ''] for t in base_titles])
    gen_titles = {r[0] for r in csv.reader(open(os.path.join(REPO, 'ForDB/book_info.csv'), encoding='utf-8', newline='')) if r}
    desc_path = os.path.join(REPO, 'ForDB/sefaria_metadata_changes.csv')
    with open(desc_path, encoding='utf-8', newline='') as f:
        descs = list(csv.reader(f))
    if not descs or descs[0] != DESC_CSV_HEADER:
        raise SystemExit('%s: unexpected header' % desc_path)

    print('target: %s' % BOOK_DIR)
    for t in base_titles:
        print('  %-28s metadata=%s  all_metadata=%s  book_info=%s'
              % (t, t in have, t in all_have, t in gen_titles))

    new_meta = [{'title': t, 'author': AUTHOR, 'pubDate': None,
                 'pubPlace': None, 'compPlace': None, 'compDate': None,
                 'תיאור_חדש': None, 'heShortDesc': None,
                 'heDesc': None, 'Unnamed: 9': None, 'order': None}
                for t in base_titles if t not in have]
    desc_changes = [upsert_description(descs, normalize_hebrew_label(f'{SERIES} {t}'), CATEGORY, AUTHOR,
                                       short_desc(t), long_desc(t))
                    for t in TRACTATES]
    new_all = [{'title': t, 'heAuthors': [AUTHOR], 'Sourcefolder': 'MoreBooks'}
               for t in base_titles if t not in all_have]
    new_gen = [t for t in base_titles if normalize_book_title(t) not in gen_titles]
    print('\nmetadata.json rows to add:     %d' % len(new_meta))
    print('all_metadata.json rows to add: %d' % len(new_all))
    print('book_info.csv rows to add:     %d' % len(new_gen))
    print('books to write:                %d' % len(books))
    print('links to write:                %d' % len(links))
    print('desc csv rows add/update:      %d/%d'
          % (desc_changes.count('add'), desc_changes.count('update')))

    if not a.apply:
        print('\ndry run -- nothing written. Re-run with --apply.')
        return

    os.makedirs(BOOK_DIR, exist_ok=True)
    os.makedirs(LINKS_DIR, exist_ok=True)
    for f in books:
        shutil.copyfile(src_books / f, os.path.join(BOOK_DIR, f))
    for f in links:
        shutil.copyfile(src_links / f, os.path.join(LINKS_DIR, f))
    # Each registry keeps its own on-disk shape; re-encoding one differently
    # rewrites every line of a file with thousands of rows
    # (sefaria_metadata_changes.csv: LF, every field quoted).
    if new_meta:
        meta.extend(new_meta)
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write('[\n' + ',\n'.join(
                json.dumps(m, ensure_ascii=False, separators=(',', ':'))
                for m in meta) + '\n]\n')
    if new_all:
        all_meta.extend(new_all)
        with open(all_path, 'w', encoding='utf-8') as f:
            json.dump(all_meta, f, ensure_ascii=False, indent=2)
            f.write('\n')
    apply_registration(REPO, csv_plan)
    if any(desc_changes):
        with open(desc_path, 'w', encoding='utf-8', newline='') as f:
            csv.writer(f, quoting=csv.QUOTE_ALL,
                       lineterminator='\n').writerows(descs)
    print('\nwrote %d books and %d links files, registered %d titles'
          % (len(books), len(links), len(new_meta)))


if __name__ == '__main__':
    main()
