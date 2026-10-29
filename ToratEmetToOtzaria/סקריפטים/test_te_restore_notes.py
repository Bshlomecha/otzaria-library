"""Tests for te_restore_notes.py (no Torat Emet files needed). Run: python3 -m unittest -v test_te_restore_notes"""
import collections
import unittest

import te_restore_notes as T


def restore(line, note):
    return T.restore_line(line, T.rules(note), collections.Counter())


class RestoreLine(unittest.TestCase):
    def test_bolds_the_yod_the_temp_file_lost(self):
        line = "<b>(1680)</b> עוד פירש <b>רש''</b>י, וב<b>רש''</b>י שב<b>ע</b>י<b>ן</b> י<b>עקב</b> כתב."
        note = 'עוד פירש <b>רש"י</b>, וב<b>רש"י</b> שב<b>עין</b> <b>יעקב</b> כתב.'
        new = restore(line, note)[0]
        self.assertEqual(new, '<b>(1680)</b> עוד פירש <b>רש"י</b>, וב<b>רש"י</b> שב<b>עין</b> <b>יעקב</b> כתב.')

    def test_prefix_letter_stays_plain(self):
        line = '<b>(1)</b> ה<b>טור</b> כתב.'
        self.assertEqual(restore(line, 'ה<b>טור</b> כתב.')[0], line)

    def test_never_removes_a_bold(self):
        line = '<b>(1)</b> <b>הטור</b> כתב.'
        self.assertEqual(restore(line, 'ה<b>טור</b> כתב.')[0], line)

    def test_other_tags_and_hand_fixes_survive(self):
        line = '<b>(1)</b> <small>הערה ארוכה למדי כדי שהדמיון יישאר גבוה</small> <b>ז</b>י<b>מן</b> ב.'
        new = restore(line, '<small>הערה ארוכה למדי כדי שהדמיון יישאר גבוה</small> <b>זימן</b> ב')[0]
        self.assertEqual(new, '<b>(1)</b> <small>הערה ארוכה למדי כדי שהדמיון יישאר גבוה</small> <b>זימן</b> ב.')

    def test_quote_mark_split_from_its_letters_by_a_tag(self):
        line = "<b>(1)</b> גרס <b>''</b>כשחרש<b>''</b>."
        self.assertEqual(restore(line, 'גרס <b>"</b>כשחרש<b>"</b>.')[0], '<b>(1)</b> גרס <b>"</b>כשחרש<b>"</b>.')

    def test_bold_stuck_to_a_quotation_mark_is_not_copied(self):
        line = "<b>(1)</b> לשון <b>''</b>גבורות<b>''</b> ובסימן ק<b>''</b>ד ועוד."
        note = 'לשון <b>"ג</b>בורות<b>"</b> ובסימן ק<b>י"</b>ד ועוד.'
        self.assertEqual(restore(line, note)[0], '<b>(1)</b> לשון <b>"</b>גבורות<b>"</b> ובסימן ק<b>"</b>ד ועוד.')

    def test_real_double_apostrophe_is_kept(self):
        line = "<b>(1)</b> וכו'' ועוד."
        self.assertEqual(restore(line, "וכו'' ועוד.")[0], line)

    def test_other_text_lends_nothing(self):
        self.assertIsNone(restore('<b>(1)</b> טקסט אחד לגמרי.', '<b>אחר</b> לחלוטין ושונה מהראשון.'))

    def test_rule_tokens_of_the_notes_book(self):
        line = '<b>(1)</b> א) זקן <b>גבורת אר</b>י?'
        new = restore(line, 'אSE זקן <b>גבורת ארי</b><QM>')[0]
        self.assertEqual(new, '<b>(1)</b> א) זקן <b>גבורת ארי</b>?')

    def test_second_run_changes_nothing(self):
        line = "<b>(1)</b> וב<b>רש''</b>י שב<b>ע</b>י<b>ן</b>."
        note = 'וב<b>רש"י</b> שב<b>עין</b>.'
        once = restore(line, note)[0]
        self.assertEqual(restore(once, note)[0], once)


class FillGaps(unittest.TestCase):
    def test_final_and_middle_gaps(self):
        self.assertEqual(T.fill_gaps('ה<b>מאיר</b>י כתב, <b>ז</b>י<b>מן</b> <b>בק</b>י<b>נה</b>'),
                         'ה<b>מאירי</b> כתב, <b>זימן</b> <b>בקינה</b>')

    def test_word_start_and_quote_cases_are_left(self):
        for s in ('<b>רב</b> י<b>עקב</b>', 'ק<b>י"</b>ד', '<b>הגר</b>י"<b>ז</b>', '<b>טור</b>'):
            self.assertEqual(T.fill_gaps(s), s)

    def test_second_run(self):
        once = T.fill_gaps('<b>עבד עבר</b>י <b>נמ</b>')
        self.assertEqual(T.fill_gaps(once), once)


if __name__ == '__main__':
    unittest.main()
