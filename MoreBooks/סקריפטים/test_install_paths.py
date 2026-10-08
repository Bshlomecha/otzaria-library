"""כל install.py תחת MoreBooks/סקריפטים נטען לבד ומוצא את שורש הריפו ואת יעדיו הקיימים.

הסקריפטים קובעים את הנתיבים לפי מיקום הקובץ, ולכן העברת תיקייה שוברת אותם בשקט;
יעד שאינו קיים בעץ הריפו יוצר בהרצה חוזרת עותק כפול של הספר במקום להחליפו.
"""
import importlib.util
import os
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
BOOKS_ROOT = "MoreBooks/ספרים/אוצריא"


def load_install_scripts():
    for i, path in enumerate(sorted(HERE.glob("*/install.py"))):
        spec = importlib.util.spec_from_file_location(f"morebooks_install_{i}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield path, module


def repo_tree():
    """קבצי ותיקיות BOOKS_ROOT לפי עץ ה-HEAD (ה-CI מושך sparse, בלי תוכן הספרים)."""
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", BOOKS_ROOT],
        cwd=REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    files = {f for f in out.split("\0") if f}
    dirs = {str(Path(*Path(f).parts[:n]).as_posix()) for f in files for n in range(1, len(Path(f).parts))}
    return files, dirs


def tree_relpath(path):
    return Path(os.path.relpath(os.path.abspath(path), REPO_ROOT)).as_posix()


class InstallPathsTest(unittest.TestCase):
    def test_every_install_script_resolves_the_repo(self):
        scripts = list(load_install_scripts())
        self.assertTrue(scripts)
        for path, module in scripts:
            with self.subTest(script=path.parent.name):
                self.assertEqual(Path(module.REPO).resolve(), REPO_ROOT)
                self.assertTrue((Path(module.REPO) / ".github" / "scripts" / "book_info_writer.py").is_file())
                links_dir = getattr(module, "LINKS_DIR", None)
                if links_dir:
                    self.assertEqual(Path(links_dir).resolve(), REPO_ROOT / "MoreBooks" / "links")

    def test_every_book_target_exists_in_repo_tree(self):
        files, dirs = repo_tree()
        self.assertTrue(files)
        for path, module in load_install_scripts():
            # כל קבוע נתיב (BOOK_DIR, TANAKH...) שמצביע לתוך תיקיית הספרים
            for name, value in vars(module).items():
                if not (name.isupper() and isinstance(value, str)):
                    continue
                rel = tree_relpath(value)
                if name not in ("BOOK_DIR", "TANAKH") and not rel.startswith(BOOKS_ROOT + "/"):
                    continue
                with self.subTest(script=path.parent.name, constant=name):
                    self.assertTrue(rel.startswith(BOOKS_ROOT + "/"), f"{name} -> {rel}")
                    self.assertTrue(rel in files or rel in dirs, f"{name} -> {rel}")
            book_targets = getattr(module, "book_targets", None)
            if book_targets:
                for _, dst in book_targets(""):
                    rel = tree_relpath(dst)
                    with self.subTest(script=path.parent.name, target=rel):
                        self.assertIn(rel, files)


if __name__ == "__main__":
    unittest.main()
