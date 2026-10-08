"""בדיקות ליחידות הלוגיקה של convert.py, על מסמכים סינתטיים (בלי קובצי המקור)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert as C  # noqa: E402


class FakeDoc:
    def __init__(self, name, items, footnotes=None):
        self.name = name
        self.items = items
        self.footnotes = footnotes or {}


def t(html, small=False):
    return ('t', html, small)


def para(html, small=False, *fn):
    return ('normal', [t(html, small)] + [('fn', f) for f in fn], html)


def head(role, text, *fn):
    return (role, [t(text)] + [('fn', f) for f in fn], text)


class GematriaTest(unittest.TestCase):
    def test_roundtrip_every_daf_of_the_talmud(self):
        for n in range(1, 177):
            self.assertEqual(C.daf_key('דף ' + C.gematria(n) + '.'), (n, 0), n)
            self.assertEqual(C.daf_key('דף ' + C.gematria(n) + ':'), (n, 1), n)

    def test_fifteen_and_sixteen_avoid_divine_names(self):
        self.assertEqual(C.gematria(15), 'טו')
        self.assertEqual(C.gematria(116), 'קטז')

    def test_daf_key_rejects_a_label_without_side(self):
        self.assertIsNone(C.daf_key('דף יז'))


class CoverTest(unittest.TestCase):
    def test_covers(self):
        for s in ('בס"ד', 'בס"ד כריתות פרקים ג\' וד\' דף יא: - כ:', 'בס"ד שלמי כהן ציוני סוגיות תמורה יד. - כא:'):
            self.assertTrue(C.COVER_RE.match(s), s)

    def test_a_paragraph_that_merely_starts_with_bsd_is_not_a_cover(self):
        self.assertIsNone(C.COVER_RE.match('בס"ד איירי ביובל'))


class DafLabelTest(unittest.TestCase):
    def labels(self, *texts):
        items = [('daf', [t(x)], x) for x in texts]
        C.fix_daf_labels('x', items)
        return [i[2] for i in items]

    def test_side_comes_from_the_next_heading(self):
        self.assertEqual(self.labels('דף יז', 'דף יז:'), ['דף יז.', 'דף יז:'])
        self.assertEqual(self.labels('דף סב', 'דף סג.'), ['דף סב:', 'דף סג.'])
        self.assertEqual(self.labels('7', 'דף צ:'), ['דף צ.', 'דף צ:'])

    def test_inconsistent_label_is_an_error(self):
        with self.assertRaises(C.ConvertError):
            self.labels('דף יז', 'דף כ:')


class BuildBookTest(unittest.TestCase):
    def test_overlap_swap_numbering_and_heading_footnotes(self):
        a = FakeDoc('a', [
            head('daf', 'דף ב.'), head('chapter', 'פרק א'),
            para('ראשון', False, '1'),
            head('daf', 'דף ב:'), para('חצי ראשון'),
        ], {'1': 'הערה <b>א</b>'})
        b = FakeDoc('b', [
            ('cover', [], 'בס"ד'),
            head('daf', 'דף ב:'), para('חצי שני', True, '1'),
            head('topic', 'נושא', '2'), para('אחרון'),
        ], {'1': 'הערה ב', '2': 'הערת כותרת'})
        log = []
        book = C.build_book('מסכת', [a, b], log.append)
        self.assertEqual(book.lines, [
            '<h1>שלמי כהן מסכת</h1>', C.AUTHOR, C.BSD_LINE,
            '<h2>פרק א</h2>', '<h3>דף ב.</h3>', 'ראשון<sup>1</sup>',
            '<h3>דף ב:</h3>', 'חצי ראשון', '<small>חצי שני</small><sup>2</sup>',
            '<h4>נושא</h4>', '<sup>3</sup>אחרון',
        ])
        self.assertEqual(book.notes, ['<sup>1</sup> הערה <b>א</b>', '<sup>2</sup> הערה ב', '<sup>3</sup> הערת כותרת'])
        self.assertEqual(book.links, [(6, 1), (9, 2), (11, 3)])
        self.assertEqual(C.check_book('מסכת', book), [])

    def test_empty_footnote_is_dropped_with_its_marker(self):
        d = FakeDoc('a', [head('daf', 'דף ב.'), para('טקסט', False, '1')], {'1': ' '})
        book = C.build_book('מסכת', [d], lambda s: None)
        self.assertEqual(book.lines[-1], 'טקסט')
        self.assertEqual((book.notes, book.links, book.dropped_empty_notes), ([], [], 1))

    def test_check_book_rejects_italic_in_a_note(self):
        d = FakeDoc('a', [head('daf', 'דף ב.'), para('טקסט', False, '1')], {'1': 'x <i>y</i>'})
        book = C.build_book('מסכת', [d], lambda s: None)
        self.assertTrue(any('<i>' in e for e in C.check_book('מסכת', book)))


class FootnoteSpacingTest(unittest.TestCase):
    def test_space_around_a_marker_is_kept(self):
        # 'יחלוקו' + סמן + ' ' + '[דנחשב': המרווח אחרי הסמן חייב לשרוד (הוא מצטרף לריצה הקטנה שאחריו)
        parts = C.Docx._parts([
            ('t', 'יחלוקו', (False,) * 4, False), ('fn', '1'),
            ('t', ' ', (False,) * 4, False), ('t', '[דנחשב', (False,) * 4, True),
        ])
        self.assertEqual(parts, [('t', 'יחלוקו', False), ('fn', '1'), ('t', ' [דנחשב', True)])
        out = ''.join(p[1] if p[0] == 't' else '|' for p in parts)
        self.assertEqual(out, 'יחלוקו| [דנחשב')


if __name__ == '__main__':
    unittest.main()
