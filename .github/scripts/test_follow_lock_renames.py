import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_locked_metadata as gate
import follow_lock_renames as follow

HEADER = "kind\tkey\tvalue\tnote\n"
BOOK = "MoreBooks/ספרים/אוצריא/הלכה/ספר.txt"
MOVED = "MoreBooks/ספרים/אוצריא/מוסר/ספר.txt"


def lock_text(*rows):
    return HEADER + "# comment\n" + "".join("\t".join(row) + "\n" for row in rows)


def titles(author=None, csv=None):
    renames = {kind: {} for kind in follow.KIND_FILES}
    renames["author"] = author or {}
    renames["sefaria_short"] = renames["sefaria_long"] = csv or {}
    renames["line2"] = {}
    return renames


def renamed(file, old, new):
    return {"file": file, "kind": "renamed", "detail": f"{old} -> {new}", "from": old, "to": new}


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout.decode()


class FollowRenamesTest(unittest.TestCase):
    def test_title_kinds_follow_the_rename(self):
        text = lock_text(
            ("author", "ספר", "רבי פלוני", "n"),
            ("sefaria_short", "ספר", "קצר", "n"),
            ("sefaria_long", "ספר", "ארוך", "n"),
            ("author", "אחר", "רבי אלמוני", "n"),
        )
        after, changed, warnings = follow.follow_renames(text, titles({"ספר": "ספר ב"}, {"ספר": "ספר ב"}))
        self.assertEqual((changed, warnings), (3, []))
        self.assertEqual(after, lock_text(
            ("author", "אחר", "רבי אלמוני", "n"),
            ("author", "ספר ב", "רבי פלוני", "n"),
            ("sefaria_short", "ספר ב", "קצר", "n"),
            ("sefaria_long", "ספר ב", "ארוך", "n"),
        ))

    def test_each_kind_follows_the_spelling_of_its_own_file(self):
        # metadata.json keeps the file name; the CSV is written in the DB spelling (״).
        text = lock_text(
            ("author", "חידושי מהרי''ק", "רבי יוסף קולון", "n"),
            ("sefaria_short", "חידושי מהרי״ק", "קצר", "n"),
        )
        after, changed, _ = follow.follow_renames(text, titles(
            {"חידושי מהרי''ק": "חידושי ופירושי מהרי''ק"}, {"חידושי מהרי״ק": "חידושי ופירושי מהרי״ק"}))
        self.assertEqual(changed, 2)
        self.assertIn("author\tחידושי ופירושי מהרי''ק\t", after)
        self.assertIn("sefaria_short\tחידושי ופירושי מהרי״ק\t", after)

    def test_sefaria_author_is_never_renamed(self):
        text = lock_text(("sefaria_author", "ספר", "רבי פלוני", "n"))
        after, changed, _ = follow.follow_renames(text, titles({"ספר": "ספר ב"}, {"ספר": "ספר ב"}))
        self.assertEqual((after, changed), (text, 0))

    def test_existing_row_with_the_same_value_absorbs_the_old_one(self):
        text = lock_text(("author", "ישן", "רבי א", "n"), ("author", "חדש", "רבי א", "n"))
        after, changed, warnings = follow.follow_renames(text, titles({"ישן": "חדש"}))
        self.assertEqual((changed, warnings), (1, []))
        self.assertEqual(after, lock_text(("author", "חדש", "רבי א", "n")))

    def test_existing_row_with_another_value_keeps_both_and_warns(self):
        text = lock_text(("author", "ישן", "רבי א", "n"), ("author", "חדש", "רבי ב", "n"))
        after, changed, warnings = follow.follow_renames(text, titles({"ישן": "חדש"}))
        self.assertEqual((after, changed), (text, 0))
        self.assertEqual(len(warnings), 1)

    def test_a_chain_moves_every_row(self):
        text = lock_text(("author", "א", "רבי א", "n"), ("author", "ב", "רבי ב", "n"))
        after, changed, warnings = follow.follow_renames(text, titles({"א": "ב", "ב": "ג"}))
        self.assertEqual((changed, warnings), (2, []))
        self.assertEqual(after, lock_text(("author", "ב", "רבי א", "n"), ("author", "ג", "רבי ב", "n")))
        self.assertEqual(len(gate.parse_locks(after, "lock")), 2)

    def test_two_rows_into_one_key_with_different_values_stay(self):
        text = lock_text(("author", "א", "רבי א", "n"), ("author", "ב", "רבי ב", "n"))
        after, changed, warnings = follow.follow_renames(text, titles({"א": "ג", "ב": "ג"}))
        self.assertEqual((after, changed, len(warnings)), (text, 0, 2))

    def test_two_rows_into_one_key_with_the_same_value_become_one(self):
        text = lock_text(("author", "א", "רבי א", "n"), ("author", "ב", "רבי א", "n"))
        after, changed, _ = follow.follow_renames(text, titles({"א": "ג", "ב": "ג"}))
        self.assertEqual((after, changed), (lock_text(("author", "ג", "רבי א", "n")), 2))

    def test_crlf_rows_keep_their_line_ending(self):
        text = lock_text(("author", "א", "רבי א", "n")).replace("\n", "\r\n")
        after, _, _ = follow.follow_renames(text, titles({"א": "ב"}))
        self.assertIn("author\tב\tרבי א\tn\r\n", after)

    def test_escaped_keys_round_trip(self):
        text = lock_text(("author", "א\\tב", "רבי א", "n"))
        after, _, _ = follow.follow_renames(text, titles({"א\tב": "ג\\ד"}))
        self.assertIn("\tג\\\\ד\t", after)

    def test_report_values_come_from_the_changes_actually_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "r.json"
            report.write_text(json.dumps([
                {"old": "מהרי''ק", "new": "מהרי''ק חדש", "changes": [
                    renamed("metadata.json", "מהרי''ק", "מהרי''ק חדש"),
                    renamed("ForDB/sefaria_metadata_changes.csv", "מהרי״ק", "מהרי״ק חדש"),
                    {"file": "ForDB/book_info.csv", "kind": "renamed", "detail": "x -> y", "from": "x", "to": "y"},
                ]},
                # kept back by the validator: nothing was written, so nothing follows
                {"old": "שמור", "new": "שמור ב", "changes": [
                    {"file": "metadata.json", "kind": "kept_conflict", "detail": "שמור"}]},
            ], ensure_ascii=False), encoding="utf-8")
            renames = follow.read_title_renames(report)
        self.assertEqual(renames["author"], {"מהרי''ק": "מהרי''ק חדש"})
        self.assertEqual(renames["sefaria_short"], {"מהרי״ק": "מהרי״ק חדש"})
        self.assertEqual(renames["sefaria_long"], renames["sefaria_short"])


class MainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / ".github/data").mkdir(parents=True)

    def tearDown(self):
        self.dir.cleanup()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")

    def test_rewrites_the_lock_and_lists_it_as_touched(self):
        lock_path = self.root / gate.LOCK_PATH
        lock_path.write_text(lock_text(("author", "ספר", "רבי פלוני", "n")), encoding="utf-8")
        (self.root / "fordb_touched.txt").write_bytes("ForDB/book_info.csv\0".encode())
        (self.root / "fordb_commit_message.txt").write_text("validator\n", encoding="utf-8")
        self.write("fordb_renamed.json", json.dumps(
            [{"old": "ספר", "new": "ספר ב", "commit": "x", "changes": [renamed("metadata.json", "ספר", "ספר ב")]}],
            ensure_ascii=False))
        self.assertEqual(follow.main(["--repo", str(self.root)]), 0)
        self.assertIn("author\tספר ב\tרבי פלוני", lock_path.read_text(encoding="utf-8"))
        touched = (self.root / "fordb_touched.txt").read_bytes().decode().split("\0")
        self.assertEqual(touched, ["ForDB/book_info.csv", gate.LOCK_PATH, ""])
        self.assertEqual((self.root / "fordb_commit_message.txt").read_text(encoding="utf-8"), "validator\n")
        self.write("metadata.json", json.dumps([{"title": "ספר ב", "author": "רבי פלוני"}], ensure_ascii=False))
        self.assertEqual(gate.check(gate.load_locks(lock_path), self.root), ([], 1))

    def test_without_a_report_or_base_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(follow.main(["--repo", tmp]), 0)

    def test_leaves_the_touched_list_alone_when_no_row_matches(self):
        (self.root / gate.LOCK_PATH).write_text(lock_text(("author", "אחר", "רבי א", "n")), encoding="utf-8")
        self.write("fordb_renamed.json", json.dumps(
            [{"old": "ספר", "new": "ספר ב", "changes": [renamed("metadata.json", "ספר", "ספר ב")]}], ensure_ascii=False))
        self.assertEqual(follow.main(["--repo", str(self.root)]), 0)
        self.assertFalse((self.root / "fordb_touched.txt").exists())

    def init_git(self):
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "lock@example.invalid")
        git(self.root, "config", "user.name", "lock")
        git(self.root, "config", "commit.gpgsign", "false")

    def commit(self, message):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)
        return git(self.root, "rev-parse", "HEAD").strip()

    def test_line2_follows_an_exact_move_and_not_a_move_with_an_edit(self):
        self.init_git()
        edited = "MoreBooks/ספרים/אוצריא/הלכה/ספר ערוך.txt"
        self.write(BOOK, "<h1>ספר</h1>\nרבי פלוני\nטקסט ארוך דיו\n" * 3)
        self.write(edited, "<h1>ספר ערוך</h1>\nרבי אלמוני\nטקסט\n" * 3)
        self.write(gate.LOCK_PATH, lock_text(("line2", BOOK, "רבי פלוני", "n"), ("line2", edited, "רבי אלמוני", "n")))
        base = self.commit("base")
        (self.root / MOVED).parent.mkdir(parents=True)
        git(self.root, "mv", BOOK, MOVED)
        git(self.root, "mv", edited, edited.replace("הלכה", "מוסר"))
        self.write(edited.replace("הלכה", "מוסר"), "<h1>ספר ערוך</h1>\nרבי אלמוני\nטקסט אחר\n" * 3)
        self.commit("move")
        self.assertEqual(follow.main(["--repo", str(self.root), "--base", base]), 0)
        text = (self.root / gate.LOCK_PATH).read_text(encoding="utf-8")
        self.assertIn(f"line2\t{MOVED}\tרבי פלוני", text)
        self.assertIn(f"line2\t{edited}\t", text)  # left for a human: the gate reports it
        self.assertEqual((self.root / "fordb_commit_message.txt").read_text(encoding="utf-8"),
                         "ci(lock): follow moved book files in the metadata lock\n")
        problems, _ = gate.check(gate.load_locks(self.root / gate.LOCK_PATH), self.root, git_rev="HEAD", bases=[base])
        self.assertEqual(len(problems), 1)
        self.assertIn("MISSING", problems[0])


if __name__ == "__main__":
    unittest.main()
