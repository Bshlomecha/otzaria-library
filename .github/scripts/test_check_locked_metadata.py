import contextlib
import io
import json
import subprocess
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


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout.decode()


class GitLine2Test(unittest.TestCase):
    """--git-rev: the CI checkout has no book files, so line2 is read from git."""

    OTHER = "MoreBooks/ספרים/אוצריא/הלכה/אחר.txt"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.repo = Fixture(Path(self.dir.name))
        self.repo.write(self.OTHER, "<h1>אחר</h1>\nרבי אלמוני\nטקסט ארוך דיו\n" * 3)
        root = self.repo.root
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "gate@example.invalid")
        git(root, "config", "user.name", "gate")
        git(root, "config", "commit.gpgsign", "false")
        self.rows = (("line2", BOOK, "רבי פלוני", ""), ("line2", self.OTHER, "רבי אלמוני", ""))
        self.repo.write(gate.LOCK_PATH, lock_file(*self.rows))
        self.base = self.commit("base")

    def tearDown(self):
        self.dir.cleanup()

    def commit(self, message):
        git(self.repo.root, "add", "-A")
        git(self.repo.root, "commit", "-q", "-m", message)
        return git(self.repo.root, "rev-parse", "HEAD").strip()

    def run_git_mode(self, *rows, since=None):
        if rows:
            self.repo.write(gate.LOCK_PATH, lock_file(*rows))
        args = ["--git-rev", "HEAD"] + (["--since", since] if since else [])
        return self.repo.run(*(rows or self.rows), args=args)

    def test_a_changed_book_is_compared_and_an_unchanged_one_is_not_read(self):
        self.repo.write(BOOK, "<h1>ספר</h1>\nרבי אחר\nטקסט\n")
        (self.repo.root / self.OTHER).unlink()  # gone from the working tree, still in git
        git(self.repo.root, "add", "-A")
        git(self.repo.root, "checkout", "-q", "HEAD", "--", self.OTHER)
        self.commit("edit")
        (self.repo.root / self.OTHER).unlink()
        code, out = self.run_git_mode(since=self.base)
        self.assertEqual(code, 1, out)
        self.assertIn(f"locked_metadata.tsv:2: line2 '{BOOK}' is locked to 'רבי פלוני', now 'רבי אחר'", out)
        self.assertIn("1 changed books compared", out)

    def test_working_tree_book_files_are_not_needed(self):
        for path in (BOOK, self.OTHER):
            (self.repo.root / path).unlink()
        code, out = self.run_git_mode(since=self.base)
        self.assertEqual(code, 0, out)

    def test_an_exact_move_is_a_note_and_a_move_with_an_edit_fails(self):
        moved = self.OTHER.replace("הלכה", "מוסר")
        (self.repo.root / moved).parent.mkdir(parents=True)
        git(self.repo.root, "mv", self.OTHER, moved)
        self.commit("move")
        code, out = self.run_git_mode(since=self.base)
        self.assertEqual(code, 0, out)
        self.assertIn("MOVED:", out)
        self.repo.write(moved, "<h1>אחר</h1>\nרבי אלמוני\nטקסט אחר לגמרי\n")
        self.commit("edit")
        code, out = self.run_git_mode(since=self.base)
        self.assertEqual(code, 1, out)
        self.assertIn("MISSING:", out)

    def test_an_exact_move_out_of_the_packaged_roots_fails(self):
        moved = "extraBooks/ספרים/אוצריא/הלכה/אחר.txt"
        (self.repo.root / moved).parent.mkdir(parents=True)
        git(self.repo.root, "mv", self.OTHER, moved)
        self.commit("discard")
        code, out = self.run_git_mode(since=self.base)
        self.assertEqual(code, 1, out)
        self.assertIn("MISSING:", out)

    def test_a_new_lock_row_is_compared_even_when_its_book_did_not_change(self):
        rows = (("line2", BOOK, "רבי פלוני", ""), ("line2", self.OTHER, "ערך אחר", ""))
        self.repo.write(gate.LOCK_PATH, lock_file(*rows))
        self.commit("relock")
        code, out = self.run_git_mode(*rows, since=self.base)
        self.assertEqual(code, 1, out)
        self.assertIn(f"line2 '{self.OTHER}'", out)

    def test_without_a_usable_base_only_paths_are_checked(self):
        self.repo.write(BOOK, "<h1>ספר</h1>\nרבי אחר\n")
        self.commit("edit")
        code, out = self.run_git_mode(since="0" * 40)
        self.assertEqual(code, 0, out)
        self.assertIn("only the paths were checked", out)
        rows = (("line2", "MoreBooks/ספרים/אוצריא/אין.txt", "x", ""),)
        code, out = self.run_git_mode(*rows)
        self.assertEqual(code, 1, out)
        self.assertIn("does not exist in HEAD", out)


class RepositoryLockTest(unittest.TestCase):
    """The committed lock file parses (the values themselves are checked by the workflow step)."""

    def test_the_lock_file_loads(self):
        path = Path(__file__).resolve().parents[1] / "data" / "locked_metadata.tsv"
        if not path.is_file():
            self.skipTest(f"{path} is not checked out")
        self.assertTrue(gate.load_locks(path))


if __name__ == "__main__":
    unittest.main()
