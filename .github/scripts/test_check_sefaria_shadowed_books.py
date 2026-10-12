import contextlib
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_sefaria_shadowed_books as gate

MORE = "MoreBooks/ספרים/אוצריא/"
DICTA = "DictaToOtzaria/ערוך/ספרים/אוצריא/"
SEFARIA_API = "sefariaToOtzaria/sefaria_api/ספרים/אוצריא/"
KSK = "KSK/ספרים/אוצריא/"


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def repo_with(root, paths):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "gate@example.invalid")
    git(root, "config", "user.name", "gate")
    git(root, "config", "commit.gpgsign", "false")
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")


def files(*paths):
    return gate.library_files(list(paths))


def covered(file_list, herefs, pending=(), files_blacklist=(), source_blacklist=("sefariaToOtzaria",)):
    return gate.covered_files(
        file_list, set(herefs), set(pending), frozenset(files_blacklist), frozenset(source_blacklist)
    )


class MatchingRuleTest(unittest.TestCase):
    def test_title_is_the_normalized_file_stem(self):
        f, = files(MORE + "שות/הגהות הב\"ח.txt")
        self.assertEqual(f.title, "הגהות הב״ח")
        self.assertEqual([c.file.archive_path for c in covered([f], {"הגהות הב״ח"})], ["שות/הגהות הב\"ח.txt"])

    def test_heref_must_match_exactly(self):
        f, = files(MORE + "א/הגהות הב\"ח.txt")
        # The generator compares with SQLite '=': no quote folding on the Sefaria side.
        self.assertEqual(covered([f], {'הגהות הב"ח', "הגהות הבח", "הגהות הב״ח "}), [])

    def test_quote_variants_and_whitespace_fold_like_the_generator(self):
        f, = files(MORE + "א/מהרי''ק  ”חדש”.txt")
        self.assertEqual(f.title, "מהרי״ק ״חדש״")

    def test_tanach_special_case(self):
        f, = files(MORE + "א/תנך.txt")
        self.assertEqual(f.title, "תנ״ך")

    def test_library_root_files_are_never_imported(self):
        self.assertEqual(covered(files(MORE + "ספר.txt"), {"ספר"}), [])

    def test_only_txt_counts(self):
        self.assertEqual(covered(files(MORE + "א/ספר.pdf", MORE + "א/ספר.TXT"), {"ספר"}), [])

    def test_files_outside_packaged_roots_are_ignored(self):
        self.assertEqual(
            covered(files("extraBooks/ספרים/אוצריא/א/ספר.txt", "DictaToOtzaria/לא ערוך/ספרים/אוצריא/א/ספר.txt"), {"ספר"}),
            [],
        )

    def test_files_blacklist_is_the_exact_file_name(self):
        f = files(MORE + "א/ספר.txt", MORE + "ב/ספר אחר.txt")
        self.assertEqual(
            [c.file.archive_path for c in covered(f, {"ספר", "ספר אחר"}, files_blacklist={"ספר.txt"})],
            ["ב/ספר אחר.txt"],
        )

    def test_source_blacklist(self):
        self.assertEqual(covered(files(SEFARIA_API + "א/ספר.txt"), {"ספר"}), [])

    def test_duplicate_archive_path_is_one_file(self):
        f = files(DICTA + "א/ספר.txt", MORE + "א/ספר.txt", KSK + "א/ספר.txt")
        self.assertEqual(len(f), 1)
        # Last root in BOOK_ROOTS order is the copy in the archive...
        self.assertEqual(f[0].repo_path, KSK + "א/ספר.txt")
        # ...while the manifest source is the first key in sorted order.
        self.assertEqual(f[0].source, "DictaToOtzaria")

    def test_source_of_a_shared_path_decides_the_source_blacklist(self):
        # "MoreBooks/..." sorts before "sefariaToOtzaria/...", so the source is MoreBooks.
        f = files(SEFARIA_API + "א/ספר.txt", MORE + "א/ספר.txt")
        self.assertEqual(f[0].source, "MoreBooks")
        self.assertEqual(len(covered(f, {"ספר"})), 1)

    def test_same_title_in_two_folders_reports_both(self):
        f = files(MORE + "א/ספר.txt", DICTA + "ב/ספר.txt")
        self.assertEqual(len(covered(f, {"ספר"})), 2)

    def test_pending_titles_are_marked(self):
        f = files(MORE + "א/ישן.txt", MORE + "א/חדש.txt")
        result = {c.file.title: c.pending for c in covered(f, {"ישן"}, pending={"חדש", "ישן"})}
        self.assertEqual(result, {"ישן": False, "חדש": True})

    def test_pending_titles_are_the_export_delta(self):
        built = {"A": "א", "B": "ב"}
        latest = {"A": "א", "B": "ב2", "C": "ג", "D": ""}
        self.assertEqual(gate.pending_export_titles(latest, built), {"ב2", "ג"})


class BlacklistFilesTest(unittest.TestCase):
    def test_resource_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "files-blacklist.txt"
            path.write_text("# comment\n\n  ספר.txt  \n", encoding="utf-8")
            self.assertEqual(gate.load_files_blacklist(path), frozenset({"ספר.txt"}))

    def test_empty_source_blacklist_falls_back_like_the_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source-blacklist.txt"
            path.write_text("# only a comment\n", encoding="utf-8")
            self.assertEqual(gate.load_source_blacklist(path), gate.SOURCE_BLACKLIST_FALLBACK)
            self.assertEqual(gate.load_files_blacklist(Path(tmp) / "missing.txt"), frozenset())


class SefariaBooksBlacklistTest(unittest.TestCase):
    def test_title_key_folds_like_the_generator(self):
        self.assertEqual(gate.normalize_title_key('  Maaseh_Rokeach\ton  "Mishnah"  '), "maaseh rokeach on mishnah")
        self.assertEqual(gate.normalize_title_key("הגהות הב״ח"), gate.normalize_title_key("הגהות הב\"ח"))
        self.assertIsNone(gate.normalize_title_key("   "))

    def test_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books_blacklist.txt"
            path.write_text("﻿# comment\n\n  מעשה רוקח  \nספר \\\"א\\\"\n", encoding="utf-8")
            self.assertEqual(gate.load_sefaria_books_blacklist(path), frozenset({"מעשה רוקח", "ספר א"}))

    def test_matches_hebrew_or_english_title(self):
        keys = frozenset({"ספר א", "book b"})
        titles = {"Book B": "ספר ב", "Book C": "ספר ג"}
        self.assertEqual(
            gate.blacklisted_titles({'ספר א', "ספר ב", "ספר ג"}, keys, titles), {"ספר א", "ספר ב"}
        )


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        repo_with(self.root, [MORE + "א/ספר.txt", MORE + "א/אחר.txt", SEFARIA_API + "א/חסום.txt"])
        self.data = Path(self.tmp.name)
        (self.data / "files.txt").write_text("", encoding="utf-8")
        (self.data / "sources.txt").write_text("sefariaToOtzaria\n", encoding="utf-8")
        self.baseline = self.data / "baseline.txt"

    def run_check(self, herefs, *extra):
        (self.data / "herefs.txt").write_text("".join(t + "\n" for t in herefs), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = gate.main([
                "check", "--repo", str(self.root),
                "--sefaria-herefs", str(self.data / "herefs.txt"),
                "--files-blacklist", str(self.data / "files.txt"),
                "--source-blacklist", str(self.data / "sources.txt"),
                "--baseline", str(self.baseline), *extra,
            ])
        return code, out.getvalue()

    def test_write_then_match(self):
        self.assertEqual(self.run_check(["ספר", "חסום"], "--write-baseline")[0], 0)
        self.assertEqual(gate.read_list(self.baseline), ["א/ספר.txt"])
        code, out = self.run_check(["ספר", "חסום"])
        self.assertEqual(code, 0, out)

    def test_newly_covered_fails_with_remediation(self):
        self.baseline.write_text(gate.BASELINE_HEADER, encoding="utf-8")
        code, out = self.run_check(["ספר"])
        self.assertEqual(code, 1)
        self.assertIn("NEWLY COVERED: " + MORE + "א/ספר.txt", out)
        self.assertIn("books_blacklist.txt", out)

    def test_stale_baseline_entry_fails(self):
        self.baseline.write_text(gate.BASELINE_HEADER + "א/ספר.txt\n", encoding="utf-8")
        code, out = self.run_check(["משהו אחר"])
        self.assertEqual(code, 1)
        self.assertIn("NO LONGER COVERED: baseline entry 'א/ספר.txt'", out)

    def test_pending_export_title_fails(self):
        self.baseline.write_text(gate.BASELINE_HEADER, encoding="utf-8")
        (self.data / "built.json").write_text(json.dumps({"X": "ישן"}), encoding="utf-8")
        (self.data / "latest.json").write_text(json.dumps({"X": "ישן", "Y": "אחר"}), encoding="utf-8")
        code, out = self.run_check(
            ["ישן"], "--export-titles", str(self.data / "latest.json"),
            "--built-export-titles", str(self.data / "built.json"),
        )
        self.assertEqual(code, 1)
        self.assertIn("the newest Sefaria export adds a book titled 'אחר'", out)

    def test_next_build_books_blacklist_uncovers_the_file(self):
        self.baseline.write_text(gate.BASELINE_HEADER, encoding="utf-8")
        blacklist = self.data / "books_blacklist.txt"
        blacklist.write_text("# replaced by the Otzaria book\nספר\n", encoding="utf-8")
        code, out = self.run_check(["ספר"], "--sefaria-books-blacklist", str(blacklist))
        self.assertEqual(code, 0, out)
        self.assertIn("ignored 1 Sefaria titles", out)

    def test_books_blacklist_also_drops_pending_titles_by_english_name(self):
        self.baseline.write_text(gate.BASELINE_HEADER, encoding="utf-8")
        (self.data / "built.json").write_text(json.dumps({"X": "ישן"}), encoding="utf-8")
        (self.data / "latest.json").write_text(json.dumps({"X": "ישן", "Other": "אחר"}), encoding="utf-8")
        blacklist = self.data / "books_blacklist.txt"
        blacklist.write_text("Other\n", encoding="utf-8")
        code, out = self.run_check(
            ["ישן"], "--export-titles", str(self.data / "latest.json"),
            "--built-export-titles", str(self.data / "built.json"),
            "--sefaria-books-blacklist", str(blacklist),
        )
        self.assertEqual(code, 0, out)

    def test_missing_baseline_and_bad_inputs_exit_2(self):
        self.assertEqual(self.run_check(["ספר"])[0], 2)
        self.baseline.write_text("א/ספר.txt\nא/ספר.txt\n", encoding="utf-8")
        self.assertEqual(self.run_check(["ספר"])[0], 2)
        self.assertEqual(self.run_check([])[0], 2)
        self.assertEqual(self.run_check(["ספר"], "--export-titles", "x.json")[0], 2)

    def test_extract_herefs_takes_only_sefaria_books(self):
        db = self.data / "seforim.db"
        with sqlite3.connect(db) as conn:
            conn.executescript(
                "CREATE TABLE source (id INTEGER PRIMARY KEY, name TEXT);"
                "CREATE TABLE book (id INTEGER PRIMARY KEY, sourceId INTEGER, title TEXT, heRef TEXT);"
                "INSERT INTO source VALUES (1, 'Sefaria'), (2, 'MoreBooks');"
                "INSERT INTO book VALUES (1, 1, 'כותרת תצוגה', 'ב'), (2, 1, 'ג', NULL),"
                " (3, 2, 'ד', 'ד'), (4, 1, 'א', 'א');"
            )
        conn.close()
        out = self.data / "herefs.txt"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(["extract-herefs", "--db", str(db), "--output", str(out)]), 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "א\nב\n")


if __name__ == "__main__":
    unittest.main()
