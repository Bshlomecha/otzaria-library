"""check_author_mirrors: heAuthors / authorName מול metadata.json, לספרי המאגר בלבד, ואזהרה בלבד."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from book_info_writer import HEADER, encode_rows
import check_author_mirrors as mirrors


def write_repo(tmp, metadata, fordb, book_info, canonical=None):
    root = Path(tmp)
    (root / 'ForDB').mkdir()
    (root / 'metadata.json').write_text(
        '[\n' + ',\n'.join(json.dumps(m, ensure_ascii=False, separators=(',', ':')) for m in metadata) + '\n]\n',
        encoding='utf-8')
    (root / 'ForDB/all_metadata.json').write_text(json.dumps(fordb, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'ForDB/book_info.csv').write_text(encode_rows([HEADER, *book_info]), encoding='utf-8')
    if canonical is not None:
        (root / 'all_metadata_with_file_paths.json').write_text(
            json.dumps(canonical, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return str(root)


class AuthorMirrorsTest(unittest.TestCase):
    def test_reports_stale_local_copies_and_ignores_noise_blank_and_sefaria(self):
        metadata = [{'title': 'א', 'author': 'רבי משה סופר'},
                    {'title': 'ב', 'author': 'רבי יעקב'},
                    {'title': 'ג', 'author': 'רבי שלמה'},
                    {'title': 'ספריא', 'author': 'צורה ישנה שאינה נצרכת'},
                    {'title': 'שניים', 'authors': ['ראשון', 'שני']}]
        fordb = [{'title': 'א', 'heAuthors': ['רבי משה ב"ר שמואל סופר'], 'Sourcefolder': 'Dicta'},
                 {'title': 'ב', 'heAuthors': ['רבי יַעֲקב‏'], 'Sourcefolder': 'Dicta'},
                 {'title': 'ג', 'heAuthors': None, 'Sourcefolder': 'MoreBooks'},
                 {'title': 'שניים', 'heAuthors': ['ראשון', 'שני'], 'Sourcefolder': 'Dicta'}]
        book_info = [['א', 'רבי משה סופר', 'אחרונים', '', '', ''],
                     ['ב', 'יעקב', 'אחרונים', '', '', ''],
                     ['ג', '', 'אחרונים', '', '', ''],
                     ['ספריא', 'שם אחר', 'אחרונים', '', '', '']]
        canonical = [{'title': 'ספריא', 'Sourcefolder': 'sefaria'}, {'title': 'א', 'Sourcefolder': 'Dicta'}]
        with tempfile.TemporaryDirectory() as tmp:
            root = write_repo(tmp, metadata, fordb, book_info, canonical)
            self.assertEqual(mirrors.find_mismatches(root), [
                ('ForDB/all_metadata.json', 'א', 'רבי משה ב"ר שמואל סופר', 'רבי משה סופר'),
                ('ForDB/all_metadata.json', 'ג', '', 'רבי שלמה'),
                ('ForDB/book_info.csv', 'ב', 'יעקב', 'רבי יעקב'),
            ])
            out = io.StringIO()
            self.assertEqual(mirrors.main(root, out), 0)
            self.assertEqual(out.getvalue().count('::warning file='), 3)
            self.assertIn('ForDB/all_metadata.json: 2, ForDB/book_info.csv: 1', out.getvalue())

    def test_gershayim_are_not_folded(self):
        metadata = [{'title': 'א', 'author': 'רמב"ן'}]
        fordb = [{'title': 'א', 'heAuthors': ['רמב״ן'], 'Sourcefolder': 'Dicta'}]
        with tempfile.TemporaryDirectory() as tmp:
            root = write_repo(tmp, metadata, fordb, [])
            self.assertEqual(len(mirrors.find_mismatches(root)), 1)

    def test_broken_input_warns_and_never_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            self.assertEqual(mirrors.main(tmp, out), 0)
            self.assertIn('::warning title=Author mirrors::check skipped', out.getvalue())


if __name__ == '__main__':
    unittest.main()
