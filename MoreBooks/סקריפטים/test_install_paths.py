"""כל install.py תחת MoreBooks/סקריפטים נטען לבד ומוצא את שורש הריפו.

הסקריפטים קובעים את הנתיבים לפי מיקום הקובץ, ולכן העברת תיקייה שוברת אותם בשקט;
הבדיקה טוענת כל אחד (בלי להריץ את main) ובודקת שהנתיבים מצביעים לתוך הריפו.
"""
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]


class InstallPathsTest(unittest.TestCase):
    def test_every_install_script_resolves_the_repo(self):
        scripts = sorted(HERE.glob("*/install.py"))
        self.assertTrue(scripts)
        for i, path in enumerate(scripts):
            with self.subTest(script=path.parent.name):
                spec = importlib.util.spec_from_file_location(f"morebooks_install_{i}", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertEqual(Path(module.REPO).resolve(), REPO_ROOT)
                self.assertTrue((Path(module.REPO) / ".github" / "scripts" / "book_info_writer.py").is_file())
                links_dir = getattr(module, "LINKS_DIR", None)
                if links_dir:
                    self.assertEqual(Path(links_dir).resolve(), REPO_ROOT / "MoreBooks" / "links")
                book_dir = getattr(module, "BOOK_DIR", None)
                if book_dir:
                    self.assertTrue(Path(book_dir).resolve().is_relative_to(REPO_ROOT / "MoreBooks" / "ספרים"))


if __name__ == "__main__":
    unittest.main()
