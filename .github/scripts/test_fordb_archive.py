import hashlib
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import fordb_archive as archive

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout.decode()


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        for path in archive.SHIPPED | archive.NOT_SHIPPED:
            self.write(path, f"{path}\n")
        self.write("ForDB/.DS_Store", "finder")

    def tearDown(self):
        self.dir.cleanup()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def build(self, name="out.zip"):
        out = self.root / name
        archive.build(self.root, out)
        return out

    def test_ships_exactly_the_consumed_files_in_byte_order(self):
        with zipfile.ZipFile(self.build()) as zf:
            names = zf.namelist()
            self.assertEqual(names, sorted(archive.SHIPPED, key=str.encode))
            for info in zf.infolist():
                self.assertEqual((info.date_time, info.compress_type), ((1980, 1, 1, 0, 0, 0), zipfile.ZIP_STORED))

    def test_the_digest_depends_only_on_names_and_bytes(self):
        first = hashlib.sha256(self.build("a.zip").read_bytes()).hexdigest()
        self.write("ForDB/README.md", "עריכה\n")
        self.assertEqual(hashlib.sha256(self.build("b.zip").read_bytes()).hexdigest(), first)
        self.write("ForDB/book_moves.csv", "שונה\n")
        self.assertNotEqual(hashlib.sha256(self.build("c.zip").read_bytes()).hexdigest(), first)

    def test_an_unknown_or_missing_file_fails(self):
        self.write("ForDB/new_table.csv", "x\n")
        with self.assertRaisesRegex(SystemExit, r"without a runtime validator=\['ForDB/new_table.csv'\]"):
            self.build()
        (self.root / "ForDB/new_table.csv").unlink()
        (self.root / "ForDB/book_moves.csv").unlink()
        with self.assertRaisesRegex(SystemExit, r"missing=\['ForDB/book_moves.csv'\]"):
            self.build()

    def test_symlinks_are_refused(self):
        (self.root / "ForDB/link.csv").symlink_to(self.root / "ForDB/book_moves.csv")
        with self.assertRaisesRegex(SystemExit, "symlinks"):
            self.build()

    def test_same_content_reads_trees_and_ignores_unshipped_files(self):
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "a@example.invalid")
        git(self.root, "config", "user.name", "a")
        git(self.root, "config", "commit.gpgsign", "false")

        def commit():
            git(self.root, "add", "-A")
            git(self.root, "commit", "-q", "-m", "x")
            return git(self.root, "rev-parse", "HEAD").strip()

        first = commit()
        self.write("ForDB/README.md", "עריכה\n")
        self.write("other.txt", "x\n")
        second = commit()
        self.write("ForDB/book_moves.csv", "שונה\n")
        third = commit()
        same = archive.main(["--repo", str(self.root), "same-content", first, second])
        differ = archive.main(["--repo", str(self.root), "same-content", second, third])
        self.assertEqual((same, differ), (0, archive.DIFFERENT))
        with self.assertRaises(subprocess.CalledProcessError):
            archive.main(["--repo", str(self.root), "same-content", "0" * 40, third])


class RepositoryArchiveTest(unittest.TestCase):
    def test_the_committed_fordb_folder_is_covered(self):
        if not (REPO / "ForDB").is_dir():
            self.skipTest("ForDB is not checked out")
        archive.check_coverage(archive.archive_paths(REPO))

    def test_both_workflows_build_through_this_module(self):
        for name, out in (("validate-fordb-book-names.yml", "$ARCHIVE_NAME"), ("update-fordb.yml", "$ARCHIVE_NAME")):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn(f'python3 .github/scripts/fordb_archive.py build "{out}"', text, name)
            self.assertNotIn("zipfile.ZipFile(", text, name)


if __name__ == "__main__":
    unittest.main()
