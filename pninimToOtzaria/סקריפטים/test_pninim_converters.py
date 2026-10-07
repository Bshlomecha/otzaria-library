import os
import tempfile
import unittest

from manipulate import apply_inline, manipulate
from merge_books import merge_book


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


class MergeBooksTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.book = os.path.join(self.dir, 'ספר')

    def test_include_name_with_quotes_and_spaces_is_found(self):
        write(os.path.join(self.book, 'חלק_א', 'חידושי_הרשבא', 'ב'), 'תוכן\n')
        write(os.path.join(self.book, 'index'), 'שם\n+<חלק_א/חידושי_הרשב"א/ב>\n+<חלק_א/חידושי_הרשבא/ ב >\n')
        out = read(merge_book(os.path.join(self.book, 'index')))
        self.assertEqual(out.count('תוכן'), 2)

    def test_missing_include_fails(self):
        write(os.path.join(self.book, 'index'), 'שם\n+<אין_כזה>\n')
        with self.assertRaises(FileNotFoundError):
            merge_book(os.path.join(self.book, 'index'))

    def test_table_border_in_content_is_not_an_include(self):
        write(os.path.join(self.book, 'א'), '+-----+\n| x |\n+=====+\n')
        write(os.path.join(self.book, 'index'), 'שם\n+<א>\n')
        out = read(merge_book(os.path.join(self.book, 'index')))
        self.assertIn('+-----+\n| x |\n+=====+\n', out)

    def test_sub_heading_repeats_after_parent_changes(self):
        for part in ('אשל_אברהם', 'משבצות_זהב'):
            write(os.path.join(self.book, part, 'סימן_א'), part + '\n')
        write(os.path.join(self.book, 'index'), 'שם\n+<אשל_אברהם/סימן_א>\n+<משבצות_זהב/סימן_א>\n')
        out = read(merge_book(os.path.join(self.book, 'index')))
        self.assertEqual(out.count('<h3>סימן א</h3>'), 2)


class ManipulateTest(unittest.TestCase):
    def test_italic_does_not_touch_urls_tags_or_images(self):
        self.assertEqual(apply_inline('ראה https://pninim.org/a/b'), 'ראה https://pninim.org/a/b')
        img = '<img src="data:image/png;base64,ab/cd/ef">'
        self.assertEqual(apply_inline(img), img)
        self.assertEqual(apply_inline('<b>x</b> /נטוי/'), '<b>x</b> <i>נטוי</i>')

    def test_correction_markup_renders_both_readings(self):
        self.assertEqual(apply_inline('אמר ~רבה~ {רבא} כו'), 'אמר (רבה) [רבא] כו')
        self.assertEqual(apply_inline('אמר ~רבה~{רבא}'), 'אמר (רבה) [רבא]')
        self.assertEqual(apply_inline('ולא ~הוא~ אמר'), 'ולא (הוא) אמר')
        self.assertEqual(apply_inline('{צ"ל: כן} עוד'), '[צ"ל: כן] עוד')
        self.assertEqual(apply_inline('שא{ו}ל ויב~ו~א'), 'שא[ו]ל ויב(ו)א')

    def run_manipulate(self, merged):
        d = tempfile.mkdtemp()
        path = os.path.join(d, 'xmerged.txt')
        write(path, merged)
        manipulate(path)
        return read(os.path.join(d, 'x.txt')).split('\n')

    def test_heading_levels_follow_path_heading(self):
        out = self.run_manipulate('שם\n<h4>ב</h4>\n% א\nטקסט\n%% פרק\nעוד 50% מזה\n')
        self.assertEqual(out[1:6], ['<h4>ב</h4>', '<h5>א</h5>', 'טקסט', '<h6>פרק</h6>', 'עוד 50% מזה'])

    def test_twin_heading_removed_in_place(self):
        out = self.run_manipulate('שם\n<h2>א</h2>\nשורה\n<h2>ב</h2>\n% ב\nטקסט\n<h2>א</h2>\n')
        self.assertEqual(out[1:6], ['<h2>א</h2>', 'שורה', '<h2>ב</h2>', 'טקסט', '<h2>א</h2>'])


if __name__ == '__main__':
    unittest.main()
