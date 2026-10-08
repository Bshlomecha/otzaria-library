import tempfile
import unittest
from pathlib import Path

from to_otzaria import convert_html

HEAD = '<p><strong>ספר</strong></p>\n<p>מחבר</p>\n<p>דפוס</p>\n'


def convert(body):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'x.html'
        p.write_text(HEAD + body, encoding='utf-8')
        return convert_html(p)[0]


def note(a, b, n):
    return f'<a id="fnref{a}" href="#fnref{b}" role="doc-noteref"><sup>{n}</sup></a>'


class ToOtzariaTest(unittest.TestCase):
    def test_note_definition_before_its_call_keeps_roles(self):
        out = convert(f'<p>{note("1_2", "1_1", 1)} הערה</p>\n<p>גוף {note("1_1", "1_2", 1)} המשך</p>\n')
        self.assertIn('<small style="color: gray;"><sup>1</sup> הערה</small>', out)
        self.assertIn('גוף <sup style="color: gray;">1</sup> המשך', out)
        self.assertNotIn('<small style="color: gray;">גוף', out)

    def test_bold_and_italic_without_padding(self):
        out = convert('<p><strong>ויאמר</strong> משה <em>כך</em></p>\n')
        self.assertIn('\n<b>ויאמר</b> משה <i>כך</i>', out)
        self.assertNotIn('  ', out)

    def test_generated_table_of_contents_is_dropped(self):
        out = convert('<section id="a"><h1>א</h1>\n<p><ul>\n<ul> <li><a href="#a">א</a></li></ul></ul></p>\n<p>טקסט</p></section>\n')
        self.assertNotIn('<li>', out)
        self.assertIn('<h2>א</h2>\nטקסט', out)

    def test_correction_markup_renders_both_readings(self):
        out = convert('<p>אמר <del>רבה</del><ins>רבא</ins> ולא <del>הוא</del> כן</p>\n')
        self.assertIn('אמר (רבה) [רבא] ולא (הוא) כן', out)
        self.assertIn('שאול ויבא', convert('<p>שא<ins>ו</ins>ל ויב<del>ו</del>א</p>\n'))


if __name__ == '__main__':
    unittest.main()
