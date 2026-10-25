#!/usr/bin/env python3
"""Fail when a locked metadata value changes without its lock row changing too.

Some metadata values were fixed by hand after a review (author names, the author
line of a book file, the Sefaria overrides of descriptions and author names).  A
later bulk operation can put the old value back without anyone noticing: a manual
heAuthors -> metadata.json sync (which strips honorifics), a manual run of the
Sefaria export, a re-conversion of a source, or a Sefaria title/key change that
leaves a CSV row orphaned.  The lock file lists those values; this check compares
each one with the live value in the tree.

Lock file: .github/data/locked_metadata.tsv, UTF-8, tab separated, first line is
the header `kind<TAB>key<TAB>value<TAB>note`, lines starting with '#' are comments.
Inside key/value: \\t = tab, \\n = newline, \\r = carriage return, \\\\ = backslash.

    kind            key                                       value
    author          "title" in metadata.json                  its "author" (every entry with that title)
    line2           repository path of a packaged book .txt   the second line of the file
    sefaria_author  "שם בספריא" in ForDB/sefaria_author_changes.csv   "שם קנוני"
    sefaria_short   "title" in ForDB/sefaria_metadata_changes.csv     heShortDesc
    sefaria_long    "title" in ForDB/sefaria_metadata_changes.csv     heDescNew

Both directions fail: a live value that differs from its row, and a key that is gone
(a book renamed or removed, a CSV row deleted).  To change a locked value on purpose,
edit (or delete) its row in the lock file in the same commit.

--skip KIND leaves one kind unchecked, for jobs whose checkout lacks the inputs of that
kind (line2 needs the book files themselves).

Exit codes: 0 every locked value matches, 1 mismatch or missing key, 2 bad input.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path

LOCK_PATH = ".github/data/locked_metadata.tsv"
HEADER = ["kind", "key", "value", "note"]
METADATA_JSON = "metadata.json"
SEFARIA_AUTHOR_CSV = "ForDB/sefaria_author_changes.csv"
SEFARIA_METADATA_CSV = "ForDB/sefaria_metadata_changes.csv"
# sefaria_metadata_changes.csv: categoryPath,title,author,heShortDesc,heDesc,heDescNew
SEFARIA_KEY_COLUMN = "title"
SEFARIA_COLUMNS = {"sefaria_short": "heShortDesc", "sefaria_long": "heDescNew"}
KINDS = ("author", "line2", "sefaria_author", "sefaria_short", "sefaria_long")
SHOWN = 120  # characters of a value shown in a report line

_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}


@dataclass(frozen=True)
class Lock:
    kind: str
    key: str
    value: str
    note: str
    where: str  # "<file>:<line>"


def unescape(text: str, where: str) -> str:
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            nxt = text[i + 1:i + 2]
            if nxt not in _ESCAPES:
                raise ValueError(f"{where}: unknown escape '\\{nxt}'")
            out.append(_ESCAPES[nxt])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def load_locks(path: Path) -> list[Lock]:
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0].rstrip("\r").split("\t") != HEADER:
        raise ValueError(f"{path}: the header must be {'<TAB>'.join(HEADER)}")
    locks, seen = [], {}
    for n, line in enumerate(lines[1:], start=2):
        line = line.rstrip("\r")
        if not line.strip() or line.startswith("#"):
            continue
        where = f"{path}:{n}"
        cols = line.split("\t")
        if len(cols) != 4:
            raise ValueError(f"{where}: expected 4 columns, found {len(cols)}")
        kind, key, value, note = cols[0], unescape(cols[1], where), unescape(cols[2], where), cols[3]
        if kind not in KINDS:
            raise ValueError(f"{where}: unknown kind {kind!r} (expected one of {', '.join(KINDS)})")
        if not key:
            raise ValueError(f"{where}: empty key")
        if (kind, key) in seen:
            raise ValueError(f"{where}: duplicate of {seen[kind, key]}")
        seen[kind, key] = where
        locks.append(Lock(kind, key, value, note, where))
    return locks


def parse_metadata_authors(text: str, name: str = METADATA_JSON) -> dict[str, list[str | None]]:
    """title -> the "author" of every metadata.json entry with that title, in file order."""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{name}: expected a JSON list")
    authors: dict[str, list[str | None]] = {}
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("title"), str):
            authors.setdefault(entry["title"], []).append(entry.get("author"))
    return authors


def parse_sefaria_authors(text: str) -> dict[str, str]:
    rows = list(csv.reader(io.StringIO(text, newline="")))
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}


def parse_sefaria_descriptions(text: str, name: str = SEFARIA_METADATA_CSV) -> dict[str, dict[str, str]]:
    """kind -> {title: value} for sefaria_short / sefaria_long."""
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise ValueError(f"{name}: empty")
    header = rows[0]
    try:
        key = header.index(SEFARIA_KEY_COLUMN)
        columns = {kind: header.index(column) for kind, column in SEFARIA_COLUMNS.items()}
    except ValueError as error:
        raise ValueError(f"{name}: unexpected header {header}") from error
    out: dict[str, dict[str, str]] = {kind: {} for kind in SEFARIA_COLUMNS}
    for row in rows[1:]:
        if len(row) != len(header):
            continue
        for kind, column in columns.items():
            out[kind][row[key]] = row[column]
    return out


def second_line_of(text: str) -> str | None:
    """The second line of a book text, without its line ending; None when there is no second line."""
    first = text.find("\n")
    if first < 0 or first == len(text) - 1:
        return None
    end = text.find("\n", first + 1)
    line = text[first + 1:] if end < 0 else text[first + 1:end]
    return line.rstrip("\r")


def metadata_authors(path: Path) -> dict[str, list[str | None]]:
    return parse_metadata_authors(path.read_text(encoding="utf-8"), str(path))


def sefaria_authors(path: Path) -> dict[str, str]:
    return parse_sefaria_authors(path.read_text(encoding="utf-8"))


def sefaria_descriptions(path: Path) -> dict[str, dict[str, str]]:
    return parse_sefaria_descriptions(path.read_text(encoding="utf-8"), str(path))


def second_line(path: Path) -> str | None:
    """second_line_of() without reading the whole book."""
    with path.open(encoding="utf-8", newline="\n") as f:
        f.readline()
        line = f.readline()
    if not line:
        return None
    return line.rstrip("\n").rstrip("\r")


def shown(value: str | None) -> str:
    if value is None:
        return "nothing"
    text = escape(value)
    return repr(text if len(text) <= SHOWN else text[:SHOWN] + "...")


def check(locks: list[Lock], repo: Path, skip: frozenset[str] = frozenset()) -> tuple[list[str], int]:
    """Problems (one line each) and the number of rows checked."""
    kinds = {lock.kind for lock in locks} - skip
    authors = metadata_authors(repo / METADATA_JSON) if "author" in kinds else {}
    sefaria = sefaria_authors(repo / SEFARIA_AUTHOR_CSV) if "sefaria_author" in kinds else {}
    descriptions = (
        sefaria_descriptions(repo / SEFARIA_METADATA_CSV) if kinds & set(SEFARIA_COLUMNS) else {}
    )
    problems, checked = [], 0
    for lock in locks:
        if lock.kind in skip:
            continue
        checked += 1
        live: list[str | None]
        if lock.kind == "author":
            if lock.key not in authors:
                problems.append(f"MISSING: {lock.where}: no entry titled {lock.key!r} in {METADATA_JSON}")
                continue
            live = authors[lock.key]
        elif lock.kind == "line2":
            path = repo / lock.key
            if not path.is_file():
                problems.append(f"MISSING: {lock.where}: the book file {lock.key!r} does not exist")
                continue
            live = [second_line(path)]
        elif lock.kind == "sefaria_author":
            if lock.key not in sefaria:
                problems.append(f"MISSING: {lock.where}: no row {lock.key!r} in {SEFARIA_AUTHOR_CSV}")
                continue
            live = [sefaria[lock.key]]
        else:
            table = descriptions[lock.kind]
            if lock.key not in table:
                problems.append(f"MISSING: {lock.where}: no row titled {lock.key!r} in {SEFARIA_METADATA_CSV}")
                continue
            live = [table[lock.key]]
        for value in live:
            if value != lock.value:
                problems.append(
                    f"CHANGED: {lock.where}: {lock.kind} {lock.key!r} is locked to {shown(lock.value)}, "
                    f"now {shown(value)}"
                )
                break
    return problems, checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--lock", type=Path, help=f"default: <repo>/{LOCK_PATH}")
    parser.add_argument("--skip", action="append", default=[], choices=KINDS, help="leave this kind unchecked")
    args = parser.parse_args(argv)
    lock_path = args.lock if args.lock is not None else args.repo / LOCK_PATH
    skip = frozenset(args.skip)
    try:
        locks = load_locks(lock_path)
        problems, checked = check(locks, args.repo, skip)
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for line in problems:
        print(line)
    skipped = len(locks) - checked
    summary = f"{checked} locked values checked" + (f", {skipped} skipped ({', '.join(sorted(skip))})" if skipped else "")
    if problems:
        print("")
        print(f"{len(problems)} of {summary}.")
        print("These values were fixed on purpose and are locked in " + LOCK_PATH + ".")
        print("If the change comes from a PR of the catalog editor (Bshlomecha), that PR should already carry")
        print("the lock update (a commit that rewrites these rows); ask for it rather than editing by hand.")
        print("Otherwise restore the value, or change the row deliberately in the same commit")
        print("(python3 .github/scripts/update_locked_metadata.py --key KIND:KEY, or --all-changed-vs REF).")
        return 1
    print(f"lock matches: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
