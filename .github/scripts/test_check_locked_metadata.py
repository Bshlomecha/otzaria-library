import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import check_locked_metadata as gate

BOOK = "MoreBooks/ספרים/אוצריא/הלכה/ספר.txt"


def lock_file(*rows):
    return "kind\tkey\tvalue\tnote\n" + "".join("\t".join(row) + "\n" for row in rows)


class Fixture:
    """A tiny repository tree: metadata.json, the two ForDB CSVs and one book."""

    def __init__(self, root: Path):
        self.root = root
        self.write("metadata.json", json.dumps([
            {"title": "ספר", "author": "רבי פלוני"},
            {"title": "כפול", "author": "רבי אלמוני"},
            {"title": "כפול", "author": "רבי אלמוני"},
        ], ensure_ascii=False))
        self.write("ForDB/sefaria_author_changes.csv", "שם בספריא,שם קנוני\nפלוני,רבי פלוני\n")
        self.write(
            "ForDB/sefaria_metadata_changes.csv",
            "categoryPath,title,author,heShortDesc,heDesc,heDescNew\n"
            'א,ספר ב,,קצר,ישן,"ארוך, בשתי\nשורות"\n',
        )
        self.write(BOOK, "<h1>ספר</h1>\nרבי פלוני\nטקסט\n")

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")

    def run(self, *rows, args=()):
        self.write(gate.LOCK_PATH, lock_file(*rows))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = gate.main(["--repo", str(self.root), *args])
        return code, out.getvalue()


ALL_ROWS = (
    ("author", "ספר", "רבי פלוני", "PR #1"),
    ("author", "כפול", "רבי אלמוני", ""),
    ("line2", BOOK, "רבי פלוני", ""),
    ("sefaria_author", "פלוני", "רבי פלוני", ""),
    ("sefaria_short", "ספר ב", "קצר", ""),
    ("sefaria_long", "ספר ב", "ארוך, בשתי\\nשורות", ""),
)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.repo = Fixture(Path(self.dir.name))

    def tearDown(self):
        self.dir.cleanup()

    def test_every_kind_matches(self):
        code, out = self.repo.run(*ALL_ROWS)
        self.assertEqual(code, 0, out)
        self.assertIn("6 locked values checked", out)

    def test_changed_author_fails(self):
        self.repo.write("metadata.json", json.dumps([{"title": "ספר", "author": "פלוני"}], ensure_ascii=False))
        code, out = self.repo.run(ALL_ROWS[0])
        self.assertEqual(code, 1)
        self.assertIn("CHANGED:", out)
        self.assertIn("'פלוני'", out)

    def test_every_duplicate_title_must_match(self):
        self.repo.write("metadata.json", json.dumps([
            {"title": "כפול", "author": "רבי אלמוני"},
            {"title": "כפול", "author": None},
        ], ensure_ascii=False))
        code, out = self.repo.run(ALL_ROWS[1])
        self.assertEqual(code, 1)
        self.assertIn("now nothing", out)

    def test_changed_line2_fails(self):
        self.repo.write(BOOK, "<h1>ספר</h1>\nפלוני\nטקסט\n")
        code, out = self.repo.run(ALL_ROWS[2])
        self.assertEqual(code, 1)
        self.assertIn("CHANGED:", out)

    def test_line2_ignores_crlf(self):
        self.repo.write(BOOK, "<h1>ספר</h1>\r\nרבי פלוני\r\nטקסט\r\n")
        self.assertEqual(self.repo.run(ALL_ROWS[2])[0], 0)

    def test_changed_sefaria_values_fail(self):
        self.repo.write("ForDB/sefaria_author_changes.csv", "שם בספריא,שם קנוני\nפלוני,פלוני\n")
        self.repo.write(
            "ForDB/sefaria_metadata_changes.csv",
            "categoryPath,title,author,heShortDesc,heDesc,heDescNew\nא,ספר ב,,אחר,ישן,אחר\n",
        )
        code, out = self.repo.run(*ALL_ROWS[3:])
        self.assertEqual(code, 1)
        self.assertEqual(out.count("CHANGED:"), 3)

    def test_missing_keys_fail(self):
        (self.repo.root / BOOK).unlink()
        code, out = self.repo.run(
            ("author", "אין כזה", "x", ""),
            ALL_ROWS[2],
            ("sefaria_author", "אין כזה", "x", ""),
            ("sefaria_short", "אין כזה", "x", ""),
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.count("MISSING:"), 4)

    def test_skip_leaves_a_kind_unchecked(self):
        (self.repo.root / BOOK).unlink()
        code, out = self.repo.run(*ALL_ROWS, args=("--skip", "line2"))
        self.assertEqual(code, 0, out)
        self.assertIn("1 skipped (line2)", out)

    def test_bad_lock_files(self):
        for rows in (
            [("author", "ספר", "רבי פלוני")],  # three columns
            [("nope", "ספר", "x", "")],  # unknown kind
            [("author", "", "x", "")],  # empty key
            [ALL_ROWS[0], ALL_ROWS[0]],  # duplicate
            [("author", "ספר", "\\x", "")],  # unknown escape
        ):
            with self.subTest(rows=rows):
                self.assertEqual(self.repo.run(*rows)[0], 2)

    def test_bad_header(self):
        self.repo.write(gate.LOCK_PATH, "kind\tkey\tvalue\n")
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.assertEqual(gate.main(["--repo", str(self.repo.root)]), 2)

    def test_comments_and_blank_lines(self):
        self.repo.write(gate.LOCK_PATH, lock_file(("# הערה",), ("",), ALL_ROWS[0]))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gate.main(["--repo", str(self.repo.root)]), 0)


class SecondLineTest(unittest.TestCase):
    def test_file_and_text_agree(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "b.txt"
            for text in ("", "א", "א\n", "א\nב", "א\nב\n", "א\r\nב\r\nג", "א\n\nג", "א\nב\rג\n"):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8", newline="")
                    self.assertEqual(gate.second_line(path), gate.second_line_of(text))


class EscapeTest(unittest.TestCase):
    def test_round_trip(self):
        for text in ("a\tb", "a\nb", "a\r\nb", "a\\nb", "\\"):
            with self.subTest(text=text):
                self.assertEqual(gate.unescape(gate.escape(text), "t:1"), text)


class RepositoryLockTest(unittest.TestCase):
    """The committed lock file parses (the values themselves are checked by the workflow step)."""

    def test_the_lock_file_loads(self):
        path = Path(__file__).resolve().parents[1] / "data" / "locked_metadata.tsv"
        if not path.is_file():
            self.skipTest(f"{path} is not checked out")
        self.assertTrue(gate.load_locks(path))


if __name__ == "__main__":
    unittest.main()
