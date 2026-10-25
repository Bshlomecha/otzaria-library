import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_locked_metadata as gate
import update_locked_metadata as tool

BOOK = "MoreBooks/ספרים/אוצריא/הלכה/ספר.txt"
OTHER = "MoreBooks/ספרים/אוצריא/הלכה/ספר אחר.txt"
CSV_HEADER = "categoryPath,title,author,heShortDesc,heDesc,heDescNew\n"


def lock_text(*rows):
    return "kind\tkey\tvalue\tnote\n# הערה\n" + "".join("\t".join(r) + "\n" for r in rows)


def tree(files):
    return lambda path: files.get(path)


def metadata(*pairs):
    return json.dumps([{"title": t, "author": a} for t, a in pairs], ensure_ascii=False)


class ChangedValuesTest(unittest.TestCase):
    def test_tables_and_line2(self):
        old = tree({
            gate.METADATA_JSON: metadata(("ספר", "רבי א"), ("קבוע", "רבי ב")),
            gate.SEFARIA_AUTHOR_CSV: "שם בספריא,שם קנוני\nא,רבי א\n",
            gate.SEFARIA_METADATA_CSV: CSV_HEADER + "x,ספר ב,,קצר,,ארוך\n",
            BOOK: "כותרת\nרבי א\nטקסט\n",
        })
        new = tree({
            gate.METADATA_JSON: metadata(("ספר", "רבי ג"), ("קבוע", "רבי ב"), ("חדש", "רבי ד")),
            gate.SEFARIA_AUTHOR_CSV: "שם בספריא,שם קנוני\nא,רבי א\nב,רבי ב\n",
            gate.SEFARIA_METADATA_CSV: CSV_HEADER + "x,ספר ב,,קצר חדש,,ארוך\n",
            BOOK: "כותרת\nרבי ג\nטקסט אחר\n",
            OTHER: "כותרת\nרבי ד\n",
        })
        paths = [gate.METADATA_JSON, gate.SEFARIA_AUTHOR_CSV, gate.SEFARIA_METADATA_CSV, BOOK, OTHER]
        self.assertEqual(tool.changed_values(old, new, paths), {
            ("author", "ספר"): "רבי ג",
            ("author", "חדש"): "רבי ד",
            ("sefaria_author", "ב"): "רבי ב",
            ("sefaria_short", "ספר ב"): "קצר חדש",
            ("line2", BOOK): "רבי ג",
            ("line2", OTHER): "רבי ד",
        })

    def test_only_changed_files_are_compared(self):
        old = tree({gate.METADATA_JSON: metadata(("ספר", "רבי א"))})
        new = tree({gate.METADATA_JSON: metadata(("ספר", "רבי ג"))})
        self.assertEqual(tool.changed_values(old, new, []), {})

    def test_gone_keys_and_body_only_changes(self):
        old = tree({BOOK: "כותרת\nרבי א\nטקסט\n", gate.METADATA_JSON: metadata(("ספר", "רבי א"))})
        new = tree({OTHER: "כותרת\nרבי א\nטקסט אחר\n", gate.METADATA_JSON: metadata(("אחר", "רבי א"))})
        changed = tool.changed_values(old, new, [BOOK, OTHER, gate.METADATA_JSON])
        self.assertIsNone(changed["line2", BOOK])
        self.assertIsNone(changed["author", "ספר"])
        self.assertEqual(changed["line2", OTHER], "רבי א")  # a new file is a new value
        body_only = tool.changed_values(tree({BOOK: "א\nב\nג\n"}), tree({BOOK: "א\nב\nד\n"}), [BOOK])
        self.assertEqual(body_only, {})

    def test_disagreeing_titles_are_left_alone(self):
        old = tree({gate.METADATA_JSON: metadata(("כפול", "רבי א"), ("כפול", "רבי א"))})
        new = tree({gate.METADATA_JSON: metadata(("כפול", "רבי א"), ("כפול", "רבי ב"))})
        self.assertEqual(tool.changed_values(old, new, [gate.METADATA_JSON]), {})


class ApplyUpdatesTest(unittest.TestCase):
    ROWS = (
        ("author", "א", "ישן", "PR #1"),
        ("author", "ג", "ישן", "PR #1"),
        ("line2", BOOK, "ישן", "PR #1"),
    )

    def apply(self, updates, **kw):
        kw = {"add_new": True, "drop_missing": False, "note": "PR #2", **kw}
        return tool.apply_updates(lock_text(*self.ROWS), updates, **kw)

    def test_update_in_place_and_insert_sorted(self):
        text, stats = self.apply({("author", "ג"): "חדש", ("author", "ב"): "חדש", ("sefaria_author", "ז"): "ש"})
        rows = [l.split("\t")[:3] for l in text.split("\n")[2:] if l]
        self.assertEqual(rows, [
            ["author", "א", "ישן"], ["author", "ב", "חדש"], ["author", "ג", "חדש"],
            ["line2", BOOK, "ישן"], ["sefaria_author", "ז", "ש"],
        ])
        self.assertEqual((stats["updated"], stats["added"]), (1, 2))
        self.assertIn("\tPR #2", text.split("\n")[4])
        self.assertTrue(text.startswith("kind\tkey\tvalue\tnote\n# הערה\n"))

    def test_without_add_new_only_existing_rows_change(self):
        text, stats = self.apply({("author", "ב"): "חדש"}, add_new=False)
        self.assertEqual(text, lock_text(*self.ROWS))
        self.assertEqual(stats["added"], 0)

    def test_missing_keys(self):
        kept, stats = self.apply({("author", "א"): None})
        self.assertEqual((kept, stats["kept_missing"]), (lock_text(*self.ROWS), 1))
        dropped, stats = self.apply({("author", "א"): None}, drop_missing=True)
        self.assertNotIn("author\tא\t", dropped)
        self.assertEqual(stats["dropped"], 1)

    def test_escapes_grey_and_non_book_paths(self):
        text, stats = self.apply({
            ("sefaria_long", "ת"): "שורה\nשנייה",
            ("sefaria_short", "ת"): "אפור" + chr(0x2062),
            ("line2", "MoreBooks/links/x.txt"): "y",
        })
        self.assertIn("sefaria_long\tת\tשורה\\nשנייה\tPR #2", text)
        self.assertEqual((stats["added"], stats["skipped"]), (1, 2))

    def test_empty_values_and_unpackaged_books_are_not_added(self):
        text, stats = self.apply({
            ("sefaria_short", "ריק"): "",
            ("line2", "extraBooks/SefariaToOtzria/ספרים/אוצריא/x.txt"): "y",
            ("line2", "DictaToOtzaria/לא ערוך/ספרים/אוצריא/x.txt"): "y",
            ("line2", OTHER): "רבי",
        })
        self.assertEqual((stats["added"], stats["skipped"]), (1, 3))
        self.assertIn(f"line2\t{OTHER}\tרבי", text)

    def test_unchanged_value_is_a_no_op(self):
        text, stats = self.apply({("author", "א"): "ישן"})
        self.assertEqual((text, stats["updated"]), (lock_text(*self.ROWS), 0))


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")

    def run_tool(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = tool.main(["--repo", str(self.root), *args])
        return code, out.getvalue()

    def check(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            return gate.main(["--repo", str(self.root)])

    def test_key_mode_unlocks_and_the_gate_passes_again(self):
        self.write(gate.METADATA_JSON, metadata(("ספר", "רבי ג")))
        self.write(BOOK, "כותרת\nרבי ג\n")
        self.write(gate.LOCK_PATH, lock_text(("author", "ספר", "רבי א", ""), ("line2", BOOK, "רבי א", "")))
        self.assertEqual(self.check(), 1)
        code, out = self.run_tool("--key", "author:ספר", "--key", "line2:" + BOOK, "--note", "תיקון")
        self.assertEqual(code, 0, out)
        self.assertIn("updated 2", out)
        self.assertEqual(self.check(), 0)

    def test_bad_key(self):
        self.write(gate.LOCK_PATH, lock_text())
        self.assertEqual(self.run_tool("--key", "nope:x")[0], 2)
        self.assertEqual(self.run_tool("--key", "author")[0], 2)

    def test_all_changed_vs_ref(self):
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "gate@example.invalid")
        git(self.root, "config", "user.name", "gate")
        git(self.root, "config", "commit.gpgsign", "false")
        self.write(gate.METADATA_JSON, metadata(("ספר", "רבי א"), ("אחר", "רבי ב")))
        self.write(BOOK, "כותרת\nרבי א\n")
        self.write(gate.LOCK_PATH, lock_text(("author", "ספר", "רבי א", ""), ("line2", BOOK, "רבי א", "")))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        self.write(gate.METADATA_JSON, metadata(("ספר", "רבי ג"), ("אחר", "רבי ד")))
        self.write(BOOK, "כותרת\nרבי ג\n")
        self.assertEqual(self.check(), 1)
        code, out = self.run_tool("--all-changed-vs", "HEAD", "--add-new")
        self.assertEqual(code, 0, out)
        self.assertIn("updated 2, added 1", out)
        self.assertEqual(self.check(), 0)
        self.assertIn("author\tאחר\tרבי ד", (self.root / gate.LOCK_PATH).read_text(encoding="utf-8"))
        # a second run finds nothing to do
        self.assertIn("updated 0, added 0", self.run_tool("--all-changed-vs", "HEAD", "--add-new")[1])

    def init_repo(self):
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "gate@example.invalid")
        git(self.root, "config", "user.name", "gate")
        git(self.root, "config", "commit.gpgsign", "false")

    def commit(self, message):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def test_a_branch_behind_ref_locks_only_its_own_changes(self):
        self.init_repo()
        self.write(gate.METADATA_JSON, metadata(("א", "רבי א"), ("ד", "צורה ישנה")))
        self.write(gate.LOCK_PATH, lock_text(("author", "א", "רבי א", "")))
        self.commit("base")
        git(self.root, "checkout", "-q", "-b", "branch")
        git(self.root, "checkout", "-q", "main")
        self.write(gate.METADATA_JSON, metadata(("א", "רבי א"), ("ד", "רבי ד המתוקן")))
        self.commit("main fixes ד")
        git(self.root, "checkout", "-q", "branch")
        self.write(gate.METADATA_JSON, metadata(("א", "רבי א החדש"), ("ד", "צורה ישנה")))
        code, out = self.run_tool("--all-changed-vs", "main", "--add-new")
        self.assertEqual(code, 0, out)
        self.assertIn("updated 1, added 0", out)
        self.assertNotIn("author\tד\t", (self.root / gate.LOCK_PATH).read_text(encoding="utf-8"))

    def test_an_untracked_new_book_is_locked(self):
        self.init_repo()
        self.write(gate.METADATA_JSON, metadata(("א", "רבי א")))
        self.write(gate.LOCK_PATH, lock_text())
        self.commit("base")
        self.write(OTHER, "כותרת\nרבי חדש\n")
        code, out = self.run_tool("--all-changed-vs", "HEAD", "--add-new")
        self.assertEqual(code, 0, out)
        self.assertIn(f"line2\t{OTHER}\tרבי חדש", (self.root / gate.LOCK_PATH).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
