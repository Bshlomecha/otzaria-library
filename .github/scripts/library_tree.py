#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
כותב את רשימת קבצי הספרייה הנארזים בקומיט נתון, יחסית לשורש "אוצריא" שבארכיון,
מופרדים ב-NUL. validateForDbInputs משווה שתי רשימות (קומיט השחרור מול המועמד)
כדי לתפוס שורת ForDB שמתארת קטגוריה שהתיקייה שלה כבר לא קיימת.

שימוש: library_tree.py <commit> <output>
"""
import subprocess
import sys

from validate_fordb_book_names import DB_BOOK_PREFIXES

SYMLINK_MODE = "120000"


def library_tree(commit, root=None):
    root = root or subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    out = subprocess.run(
        ["git", "-C", root, "ls-tree", "-r", "-z", commit, "--", *(p.rstrip("/") for p in DB_BOOK_PREFIXES)],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    files = set()
    for record in filter(None, out.split("\0")):
        meta, path = record.split("\t", 1)
        mode, kind, _ = meta.split(" ")
        # הארכיון מעתיק קבצים רגילים בלבד (copy_regular_tree).
        if kind != "blob" or mode == SYMLINK_MODE:
            continue
        prefix = next(p for p in DB_BOOK_PREFIXES if path.startswith(p))
        files.add(path[len(prefix):])
    if not files:
        raise SystemExit(f"no packaged library files at {commit}")
    return sorted(files, key=lambda p: p.encode("utf-8"))


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    commit, output = sys.argv[1:]
    files = library_tree(commit)
    with open(output, "wb") as fh:
        fh.write(b"".join(p.encode("utf-8") + b"\0" for p in files))
    print(f"{commit}: {len(files)} packaged library files -> {output}")


if __name__ == "__main__":
    main()
