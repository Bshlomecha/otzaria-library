"""Synthetic tests for split_long_lines.py (no real books)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import split_long_lines as sl

WORDS = 'alpha beta gamma delta '  # 23 visible chars


def text_of(chars: int) -> str:
    return (WORDS * (chars // len(WORDS) + 1))[:chars]


def long_line(chars: int = 70_000, br_every: int = 0) -> str:
    if not br_every:
        return text_of(chars)
    parts, done = [], 0
    while done < chars:
        n = min(br_every, chars - done)
        parts.append(text_of(n))
        done += n
    return '<br>'.join(parts)


class SplitRules(unittest.TestCase):
    def test_short_and_heading_lines_are_not_split(self):
        self.assertFalse(sl.needs_split(text_of(1000)))
        self.assertFalse(sl.needs_split('<h2>' + text_of(60_000) + '</h2>'))

    def test_pieces_rejoin_byte_for_byte_and_respect_sizes(self):
        line = long_line(95_000)
        sp, why = sl.split_line(line)
        self.assertIsNone(why)
        self.assertEqual(sl.rejoin(sp, line), line)
        for p in sp.pieces:
            self.assertGreaterEqual(sl.visible_len(p.content), sl.MIN_TAIL_CHARS)
            self.assertLessEqual(sl.visible_len(p.content), sl.MAX_CHARS)

    def test_no_piece_keeps_the_cut_space(self):
        line = long_line(95_000)
        sp, _ = sl.split_line(line)
        for p in sp.pieces:
            self.assertEqual(p.content, p.content.strip())
        self.assertEqual(sl.rejoin(sp, line), line)

    def test_br_wins_over_space_and_is_dropped_at_the_cut(self):
        line = long_line(60_000, br_every=21_000)
        sp, _ = sl.split_line(line)
        self.assertTrue(all(k == sl.BR for k in sp.kinds))
        self.assertFalse(any(p.content.endswith('<br>') or p.content.startswith('<br>') for p in sp.pieces))
        self.assertEqual(sl.rejoin(sp, line), line)

    def test_colon_then_period_preferred_over_plain_space(self):
        line = text_of(22_000) + ': ' + text_of(2_000) + '. ' + text_of(40_000)
        sp, _ = sl.split_line(line)
        self.assertEqual(sp.kinds[0], sl.COLON)
        self.assertTrue(sp.pieces[0].content.endswith(':'))

    def test_never_cuts_inside_an_inner_tag(self):
        inner = '<b>' + text_of(40_000) + '</b>'
        line = text_of(15_000) + ' ' + inner + ' ' + text_of(15_000)
        sp, why = sl.split_line(line)
        if sp is not None:
            for p in sp.pieces:
                self.assertEqual(p.content.count('<b>'), p.content.count('</b>'))
        else:
            self.assertEqual(why, 'no-cut-in-window')

    def test_whole_line_wrapper_is_closed_and_reopened(self):
        line = '<span style="x">' + long_line(70_000) + '</span>'
        sp, _ = sl.split_line(line)
        self.assertGreater(len(sp.pieces), 1)
        for k, p in enumerate(sp.pieces):
            self.assertTrue(p.content.startswith('<span style="x">'))
            self.assertTrue(p.content.endswith('</span>'))
        self.assertEqual(sl.rejoin(sp, line), line)

    def test_footnote_wrapper_is_not_split(self):
        line = '<i class="footnote">' + long_line(70_000) + '</i>'
        self.assertIsNone(sl.split_line(line)[0])

    def test_no_piece_starts_with_a_heading(self):
        line = text_of(21_000) + ' ' + '<h3>x</h3>' + text_of(50_000)
        sp, _ = sl.split_line(line)
        self.assertFalse(any(sl.is_heading(p.content) for p in sp.pieces))

    def test_forbidden_ranges_block_cuts(self):
        line = long_line(70_000)
        free, _ = sl.split_line(line)
        first_cut = free.pieces[0].src_end
        blocked, _ = sl.split_line(line, forbidden=[(first_cut - 50, first_cut + 50)])
        self.assertNotEqual(blocked.pieces[0].src_end, first_cut)

    def test_merge_proof_on_marker_pieces(self):
        line = text_of(10_000) + ' <sup>1</sup> ' + text_of(30_000) + ' <sup>2</sup> ' + text_of(30_000)
        sp, _ = sl.split_line(line)
        notes = ['<sup>1</sup> one', '<sup>2</sup> two', 'unanchored']
        placed = sl.note_pieces(line, sp, notes)
        self.assertEqual(placed[0], 0)
        self.assertEqual(placed[2], len(sp.pieces) - 1)
        self.assertTrue(sl.merge_is_preserved(line, sp, notes, placed))


ROOT = 'MoreBooks/ספרים/אוצריא/cat'
LINKS = 'MoreBooks/links'


class RepoRun(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.git('init', '-q')
        self.git('config', 'user.email', 't@example.com')
        self.git('config', 'user.name', 't')
        self.write('manual_links_sync.json', json.dumps({'links_roots': [{'path': LINKS, 'expected_state': 'present'}]}))
        self.long = text_of(10_000) + ' <sup>1</sup> ' + text_of(20_000) + ' <sup>2</sup> ' + text_of(40_000)
        self.write(ROOT + '/Base.txt', '\n'.join(['<h1>Base</h1>', 'short', self.long, 'after', '']))
        self.write(ROOT + '/' + sl.COMPANION_PREFIX + 'Base.txt', '\n'.join(['<sup>1</sup> n1', '<sup>2</sup> n2']))
        self.write(ROOT + '/Other.txt', 'x\ny\n')
        base_links = [
            {'line_index_1': 4, 'line_index_2': 1, 'heRef_2': 'r', 'path_2': 'Other.txt', 'Conection Type': 'commentary'},
            {'line_index_1': 3, 'line_index_2': 2, 'heRef_2': 'r', 'path_2': 'Other.txt', 'Conection Type': 'source'},
            {'line_index_1': 3, 'line_index_2': 1, 'heRef_2': 'r',
             'path_2': sl.COMPANION_PREFIX + 'Base.txt', 'Conection Type': 'footnotes'},
            {'line_index_1': 3, 'line_index_2': 2, 'heRef_2': 'r',
             'path_2': sl.COMPANION_PREFIX + 'Base.txt', 'Conection Type': 'footnotes'},
        ]
        other_links = [
            {'line_index_1': 1.0, 'line_index_2': 3.0, 'heRef_2': 'r', 'path_2': 'Base.txt', 'Conection Type': 'reference'},
            {'line_index_1': 2, 'line_index_2': 2, 'line_index_2_end': 4, 'heRef_2': 'r', 'path_2': 'Base.txt',
             'Conection Type': 'reference'},
        ]
        self.write(LINKS + '/Base_links.json', json.dumps(base_links, ensure_ascii=False, indent=2))
        self.write(LINKS + '/Other_links.json', json.dumps(other_links, ensure_ascii=False, indent=1) + '\n')
        self.write('MoreBooks/alt_toc/Base_alt_toc.json', json.dumps(
            [{'key': 'K', 'nodes': [{'heTitle': 'a', 'line': 2, 'children': [{'heTitle': 'b', 'line': 4}]}]}],
            ensure_ascii=False, indent=2))
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(['git', '-C', self.repo, *args], check=True, capture_output=True).stdout

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)

    def read_json(self, rel):
        with open(os.path.join(self.repo, rel), encoding='utf-8') as f:
            return json.load(f)

    def test_apply_remaps_every_reference_and_is_idempotent(self):
        stats, errors, books = sl.run(self.repo, sl.Config(), apply=True)
        self.assertEqual(errors, 0)
        n = len(books['Base'].split[2].pieces)
        self.assertEqual(n, 4)
        lines = sl.read_bytes(os.path.join(self.repo, ROOT + '/Base.txt')).decode('utf-8').split('\n')
        self.assertEqual(len(lines), 5 + n - 1)
        self.assertEqual(lines[3 + n - 1], 'after')

        base = self.read_json(LINKS + '/Base_links.json')
        self.assertEqual(base[0]['line_index_1'], 4 + n - 1)                      # shifted
        self.assertEqual((base[1]['line_index_1'], base[1]['line_index_1_end']), (3, 3 + n - 1))  # whole line -> range
        self.assertEqual(list(base[1])[:2], ['line_index_1', 'line_index_1_end'])
        self.assertEqual((base[2]['line_index_1'], base[3]['line_index_1']), (3, 4))  # notes follow their markers
        self.assertNotIn('line_index_1_end', base[2])

        other = self.read_json(LINKS + '/Other_links.json')
        self.assertEqual((other[0]['line_index_2'], other[0]['line_index_2_end']), (3.0, 3.0 + n - 1))
        self.assertIsInstance(other[0]['line_index_2'], float)
        self.assertEqual((other[1]['line_index_2'], other[1]['line_index_2_end']), (2, 4 + n - 1))
        raw = sl.read_bytes(os.path.join(self.repo, LINKS + '/Other_links.json'))
        self.assertTrue(raw.endswith(b'}\n]\n') and b'\r' not in raw)            # style and trailing LF kept

        alt = self.read_json('MoreBooks/alt_toc/Base_alt_toc.json')
        self.assertEqual(alt[0]['nodes'][0]['children'][0]['line'], 4 + n - 1)

        again, errors, _ = sl.run(self.repo, sl.Config(), apply=True)
        self.assertEqual((errors, again['split_lines'], again['records_changed']), (0, 0, 0))

    def test_first_piece_policy(self):
        sl.run(self.repo, sl.Config(), whole_line='first', apply=True)
        base = self.read_json(LINKS + '/Base_links.json')
        self.assertEqual(base[1]['line_index_1'], 3)
        self.assertNotIn('line_index_1_end', base[1])

    def test_roots_filter(self):
        stats, _, _ = sl.run(self.repo, sl.Config(), roots=('National-LibraryToOtzaria',))
        self.assertEqual(stats['split_lines'], 0)

    def test_check_changed_flags_only_changed_books(self):
        head = self.git('rev-parse', 'HEAD').decode().strip()
        self.assertEqual(sl.check_changed(self.repo, head, sl.Config()), 0)
        self.write(ROOT + '/Other.txt', 'x\n' + long_line(70_000) + '\n')
        self.git('commit', '-qam', 'long')
        self.assertEqual(sl.check_changed(self.repo, head, sl.Config()), 1)
        sl.run(self.repo, sl.Config(), apply=True)
        self.git('commit', '-qam', 'split')
        self.assertEqual(sl.check_changed(self.repo, head, sl.Config()), 0)


if __name__ == '__main__':
    unittest.main()
