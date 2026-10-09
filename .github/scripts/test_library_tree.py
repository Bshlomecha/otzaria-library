# -*- coding: utf-8 -*-
import os
import subprocess
import tempfile
import unittest

from library_tree import library_tree


class LibraryTreeTest(unittest.TestCase):
    def test_lists_packaged_regular_files_relative_to_the_merged_root(self):
        with tempfile.TemporaryDirectory() as repo:
            def write(rel):
                path = os.path.join(repo, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("x")

            write("MoreBooks/ספרים/אוצריא/קבלה/מחברי זמננו/א.txt")
            write("KSK/ספרים/אוצריא/קבלה/ב.pdf")
            write("extraBooks/ספרים/אוצריא/קבלה/לא נארז.txt")
            os.symlink("א.txt", os.path.join(repo, "MoreBooks/ספרים/אוצריא/קבלה/קישור.txt"))
            env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
            for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
                subprocess.run(["git", "-C", repo, *cmd], check=True, env=env)

            self.assertEqual(
                ["קבלה/ב.pdf", "קבלה/מחברי זמננו/א.txt"],
                sorted(library_tree("HEAD", repo)),
            )


if __name__ == "__main__":
    unittest.main()
