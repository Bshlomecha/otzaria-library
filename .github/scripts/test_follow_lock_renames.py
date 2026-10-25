import json
import tempfile
import unittest
from pathlib import Path

import check_locked_metadata as gate
import follow_lock_renames as follow

HEADER = "kind\tkey\tvalue\tnote\n"


def lock_text(*rows):
    return HEADER + "# comment\n" + "".join("\t".join(row) + "\n" for row in rows)


class FollowRenamesTest(unittest.TestCase):
    def test_title_kinds_follow_the_rename(self):
        text = lock_text(
            ("author", "ספר", "רבי פלוני", "n"),
            ("sefaria_short", "ספר", "קצר", "n"),
            ("sefaria_long", "ספר", "ארוך", "n"),
            ("author", "אחר", "רבי אלמוני", "n"),
        )
        after, changed = follow.follow_renames(text, {"ספר": "ספר ב"})
        self.assertEqual(changed, 3)
        self.assertEqual(after, text.replace("\tספר\t", "\tספר ב\t"))

    def test_sefaria_author_and_line2_are_not_renamed(self):
        text = lock_text(
            ("sefaria_author", "ספר", "רבי פלוני", "n"),
            ("line2", "MoreBooks/ספרים/אוצריא/ספר.txt", "רבי פלוני", "n"),
        )
        after, changed = follow.follow_renames(text, {"ספר": "ספר ב"})
        self.assertEqual((after, changed), (text.rstrip("\n") + "\n", 0))

    def test_existing_row_for_the_new_title_wins(self):
        text = lock_text(("author", "ישן", "רבי א", "n"), ("author", "חדש", "רבי א", "n"))
        after, changed = follow.follow_renames(text, {"ישן": "חדש"})
        self.assertEqual(changed, 1)
        self.assertEqual(after, lock_text(("author", "חדש", "רבי א", "n")).rstrip("\n") + "\n")

    def test_escaped_keys_round_trip(self):
        text = lock_text(("author", "א\\tב", "רבי א", "n"))
        after, _ = follow.follow_renames(text, {"א\tב": "ג\\ד"})
        self.assertIn("\tג\\\\ד\t", after)

    def test_main_rewrites_the_lock_and_lists_it_as_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github/data").mkdir(parents=True)
            lock_path = root / gate.LOCK_PATH
            lock_path.write_text(lock_text(("author", "ספר", "רבי פלוני", "n")), encoding="utf-8")
            (root / "fordb_touched.txt").write_bytes("ForDB/book_info.csv\0".encode())
            (root / "fordb_renamed.json").write_text(
                json.dumps([{"old": "ספר", "new": "ספר ב", "commit": "x", "changes": []}], ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(follow.main(["--repo", str(root)]), 0)
            self.assertIn("author\tספר ב\tרבי פלוני", lock_path.read_text(encoding="utf-8"))
            touched = (root / "fordb_touched.txt").read_bytes().decode().split("\0")
            self.assertEqual(touched, ["ForDB/book_info.csv", gate.LOCK_PATH, ""])
            # the lock now checks out against a metadata.json that carries the new title
            (root / "metadata.json").write_text(json.dumps([{"title": "ספר ב", "author": "רבי פלוני"}], ensure_ascii=False), encoding="utf-8")
            locks = gate.load_locks(lock_path)
            self.assertEqual(gate.check(locks, root), ([], 1))

    def test_main_without_a_report_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(follow.main(["--repo", tmp]), 0)

    def test_main_leaves_the_touched_list_alone_when_no_row_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github/data").mkdir(parents=True)
            (root / gate.LOCK_PATH).write_text(lock_text(("author", "אחר", "רבי א", "n")), encoding="utf-8")
            (root / "fordb_renamed.json").write_text(json.dumps([{"old": "ספר", "new": "ספר ב"}], ensure_ascii=False), encoding="utf-8")
            self.assertEqual(follow.main(["--repo", str(root)]), 0)
            self.assertFalse((root / "fordb_touched.txt").exists())


if __name__ == "__main__":
    unittest.main()
