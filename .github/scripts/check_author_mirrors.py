#!/usr/bin/env python3
"""אזהרה (לא כשל) כששם המחבר של ספר של המאגר ב־heAuthors או ב־authorName שונה מ־metadata.json.

שם המחבר של ספר של המאגר נקבע ב־`author` (או `authors[]`) של metadata.json שבשורש — זה מה שנכנס
לטבלת `author` במסד. `heAuthors` ב־ForDB/all_metadata.json ו־`authorName` ב־ForDB/book_info.csv
הם העתקים בלבד (ForDB/README.md), וכשהם מפגרים אחריו הם מציגים באתר שם ישן, ומי שיסנכרן מהם
אל metadata.json יחזיר צורות שתוקנו.

הבדיקה רק מדווחת (`::warning`) ויוצאת תמיד 0: יש הפרשים שאדם צריך להכריע בהם, ושינוי
`authorName` מחייב אירוע ביומן הזהות של האתר, ולכן אין כאן תיקון אוטומטי.

נבדקים רק ספרי המאגר: רשומה שאינה של ספריא, שיש לה מחבר ב־metadata.json. ב־book_info.csv
נבדק ספר עם שורה אחת ומחבר אחד; שורה עם authorName ריק אינה נבדקת. ההשוואה אחרי
normalizeAuthorName (ניקוד, תווי כיוון ורווחים), כמו במחולל.
"""
import csv
import io
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAX_ANNOTATIONS = 30

_NIKUD = re.compile("[֑-ֽֿ-ׇ]")
_BIDI = re.compile("[‎‏‪-‮⁦-⁩﻿]")
_SPACE = re.compile("[\\s  -​  　]+")


def normalize_author_name(raw):
    """כמו normalizeAuthorName ב־SeforimLibrary: גרשיים וגרש נשמרים."""
    return _SPACE.sub(" ", _BIDI.sub("", _NIKUD.sub("", raw or ""))).strip()


def metadata_authors(record):
    authors = record.get("authors")
    if isinstance(authors, list) and any(isinstance(a, str) and a.strip() for a in authors):
        names = [a.strip() for a in authors if isinstance(a, str) and a.strip()]
    else:
        author = record.get("author")
        names = [author.strip()] if isinstance(author, str) and author.strip() else []
    return list(dict.fromkeys(names))


def _read_json(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return json.load(f)


def find_mismatches(root):
    """[(קובץ, ספר, ערך בשדה, ערך ב־metadata.json)] לספרי המאגר."""
    meta = {}
    for record in _read_json(root, "metadata.json"):
        title = (record.get("title") or "").strip()
        if title and title not in meta:
            meta[title] = metadata_authors(record)

    fordb = _read_json(root, "ForDB/all_metadata.json")
    sefaria = {(r.get("title") or "").strip() for r in fordb if r.get("Sourcefolder") == "sefaria"}
    local = {(r.get("title") or "").strip() for r in fordb if r.get("Sourcefolder") != "sefaria"}
    canonical = os.path.join(root, "all_metadata_with_file_paths.json")
    if os.path.exists(canonical):
        for r in _read_json(root, "all_metadata_with_file_paths.json"):
            (sefaria if r.get("Sourcefolder") == "sefaria" else local).add((r.get("title") or "").strip())
    local -= sefaria

    def same(left, right):
        return [normalize_author_name(x) for x in left] == [normalize_author_name(x) for x in right]

    out = []
    for record in fordb:
        title = (record.get("title") or "").strip()
        expected = meta.get(title)
        if title not in local or not expected:
            continue
        he = [h.strip() for h in (record.get("heAuthors") or []) if isinstance(h, str) and h.strip()]
        if not same(he, expected):
            out.append(("ForDB/all_metadata.json", title, " / ".join(he), " / ".join(expected)))

    with open(os.path.join(root, "ForDB/book_info.csv"), encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))[1:]
    per_book = {}
    for row in rows:
        if row:
            per_book.setdefault(row[0], []).append(row[1])
    for book, names in per_book.items():
        expected = meta.get(book.strip())
        if book.strip() not in local or len(names) != 1 or not names[0] or not expected or len(expected) != 1:
            continue
        if not same(names, expected):
            out.append(("ForDB/book_info.csv", book, names[0], expected[0]))
    return out


def main(root=REPO_ROOT, stream=sys.stdout):
    try:
        mismatches = find_mismatches(root)
    except Exception as error:  # בדיקה מייעצת: אסור לה להפיל את ה-CI
        print(f"::warning title=Author mirrors::check skipped: {error}", file=stream)
        return 0
    for path, book, field, expected in mismatches[:MAX_ANNOTATIONS]:
        print(f"::warning file={path},title=Author mirror differs from metadata.json::"
              f"{book}: '{field}' != '{expected}'", file=stream)
    by_file = {}
    for path, *_ in mismatches:
        by_file[path] = by_file.get(path, 0) + 1
    summary = ", ".join(f"{path}: {count}" for path, count in sorted(by_file.items())) or "none"
    print(f"Author mirror differences (metadata.json is the source): {summary}", file=stream)
    if len(mismatches) > MAX_ANNOTATIONS:
        print(f"::warning title=Author mirrors::{len(mismatches)} differences; "
              f"the first {MAX_ANNOTATIONS} are annotated", file=stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
