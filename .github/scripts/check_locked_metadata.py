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

--skip KIND leaves one kind unchecked.

--git-rev REV reads the book files of the line2 rows from that commit instead of the working
tree, for the CI checkout, which has no book files (blob:none, sparse).  Reading all 1,500+
locked books would fetch about 2 GB, so with --since BASE (repeatable; the first one that is an
ancestor of REV is used) the second line is compared only for the books that changed in
BASE..REV; every locked path must still exist in REV.  A locked path that git sees as an exact
rename (same content, R100) to another packaged book path in BASE..REV is not a failure:
follow_lock_renames.py moves the row on the next push to main.  Without a usable BASE only the paths are checked.

Exit codes: 0 every locked value matches, 1 mismatch or missing key, 2 bad input.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from validate_fordb_book_names import DB_BOOK_PREFIXES

LOCK_PATH = ".github/data/locked_metadata.tsv"
HEADER = ["kind", "key", "value", "note"]
METADATA_JSON = "metadata.json"
SEFARIA_AUTHOR_CSV = "ForDB/sefaria_author_changes.csv"
SEFARIA_METADATA_CSV = "ForDB/sefaria_metadata_changes.csv"
# sefaria_metadata_changes.csv: categoryPath,title,author,heShortDesc,heDesc,heDescNew
SEFARIA_KEY_COLUMN = "title"
SEFARIA_COLUMNS = {"sefaria_short": "heShortDesc", "sefaria_long": "heDescNew"}
KINDS = ("author", "line2", "sefaria_author", "sefaria_short", "sefaria_long")
TXT_PATHSPEC = ":(glob)**/*.txt"


def is_packaged_book(path: str) -> bool:
    """A book file that reaches the DB (not extraBooks, not Dicta לא ערוך): the only line2 keys."""
    return path.endswith(".txt") and path.startswith(DB_BOOK_PREFIXES)
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
    return parse_locks(path.read_text(encoding="utf-8"), path)


def parse_locks(text: str, path) -> list[Lock]:
    lines = text.split("\n")
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


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True)
    if result.returncode != 0:
        raise ValueError(f"git {' '.join(args)}: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


def pick_base(repo: Path, candidates, rev: str) -> str | None:
    """The first candidate that is a commit and an ancestor of rev."""
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if not candidate or set(candidate) == {"0"}:
            continue
        try:
            sha = _git(repo, "rev-parse", "--verify", "--quiet", candidate + "^{commit}").decode().strip()
            _git(repo, "merge-base", "--is-ancestor", sha, rev)
        except ValueError:
            continue
        return sha
    return None


def exact_moves(repo: Path, base: str, rev: str) -> dict[str, str]:
    """old path -> new path of the .txt files that git sees as renamed with identical content."""
    out = _git(repo, "diff", "-M100%", "--diff-filter=R", "--name-status", "-z", base, rev, "--", TXT_PATHSPEC)
    chunks = out.decode("utf-8").split("\0")
    moves, i = {}, 0
    while i + 2 < len(chunks):
        if chunks[i] == "R100":
            moves[chunks[i + 1]] = chunks[i + 2]
        i += 3
    return moves


def prefetch(repo: Path, oids) -> None:
    """In a partial clone (the CI checkout), fetch the missing blobs in one request.

    Without this, cat-file fetches each missing blob lazily, one request per book: about
    eight minutes for the 1,500 books that one author-name commit touches."""
    if _git(repo, "config", "--bool", "--default", "false", "remote.origin.promisor").strip() != b"true":
        return
    check = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-check"],
        input="".join(f"{oid}\n" for oid in oids).encode(), capture_output=True,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    missing = [line.split()[0] for line in check.stdout.splitlines() if line.endswith(b" missing")]
    if missing:
        # Best effort: whatever this does not bring is still fetched lazily by cat-file below.
        subprocess.run(
            ["git", "-C", str(repo), "-c", "fetch.negotiationAlgorithm=noop", "fetch", "--no-tags",
             "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none", "--stdin", "origin"],
            input=b"".join(oid + b"\n" for oid in missing), capture_output=True,
        )


def read_second_lines(repo: Path, rev: str, paths) -> dict[str, str | None]:
    """path -> second line of the file at rev, streamed through one git cat-file --batch."""
    paths = sorted(paths)
    if not paths:
        return {}
    listing = _git(repo, "ls-tree", "-z", "--full-tree", rev, "--", *paths).decode("utf-8")
    oids = {}
    for entry in filter(None, listing.split("\0")):
        meta, _, path = entry.partition("\t")
        oids[path] = meta.split()[2]
    missing = [p for p in paths if p not in oids]
    if missing:
        raise ValueError(f"git ls-tree {rev}: no blob for {missing[0]}")
    prefetch(repo, sorted(set(oids.values())))
    proc = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    proc.stdin.write("".join(f"{oids[p]}\n" for p in paths).encode())
    proc.stdin.close()
    lines = {}
    for path in paths:
        header = proc.stdout.readline().split()
        if len(header) != 3:
            proc.kill()
            raise ValueError(f"git cat-file: no blob {rev}:{path}")
        data = proc.stdout.read(int(header[2]) + 1)[:-1]
        end = data.find(b"\n", data.find(b"\n") + 1)
        lines[path] = second_line_of(data[: end + 1 if end >= 0 else len(data)].decode("utf-8"))
    proc.wait()
    return lines


@dataclass
class GitBooks:
    """The line2 inputs read from a commit: which paths exist, and which changed since a base."""

    paths: set[str]
    base: str | None
    changed: set[str]
    moves: dict[str, str]
    second_lines: dict[str, str | None]


def git_books(repo: Path, rev: str, bases, keys: dict[str, str]) -> GitBooks:
    """keys: the locked line2 rows, path -> value."""
    tree = _git(repo, "ls-tree", "-r", "-z", "--name-only", "--full-tree", rev).decode("utf-8")
    paths = set(filter(None, tree.split("\0")))
    base = pick_base(repo, bases, rev)
    changed, moves = set(), {}
    if base is not None:
        diff = _git(repo, "diff", "--no-renames", "--name-only", "-z", base, rev).decode("utf-8")
        changed = set(filter(None, diff.split("\0")))
        if any(key not in paths for key in keys):
            moves = exact_moves(repo, base, rev)
        if LOCK_PATH in changed:
            # A row added or edited in this range is compared even when its book did not change.
            try:
                before = _git(repo, "cat-file", "-p", f"{base}:{LOCK_PATH}").decode("utf-8")
            except ValueError:
                before = None  # the lock file is new in this range: every row is new
            old_rows = set() if before is None else {
                (lock.key, lock.value) for lock in parse_locks(before, f"{base}:{LOCK_PATH}") if lock.kind == "line2"
            }
            changed |= {key for key, value in keys.items() if (key, value) not in old_rows}
    lines = read_second_lines(repo, rev, {key for key in keys if key in paths and key in changed})
    return GitBooks(paths, base, changed, moves, lines)


def check(
    locks: list[Lock],
    repo: Path,
    skip: frozenset[str] = frozenset(),
    git_rev: str | None = None,
    bases=(),
    notes: list[str] | None = None,
) -> tuple[list[str], int]:
    """Problems (one line each) and the number of rows checked.  `notes` collects lines that are not failures."""
    notes = [] if notes is None else notes
    kinds = {lock.kind for lock in locks} - skip
    authors = metadata_authors(repo / METADATA_JSON) if "author" in kinds else {}
    sefaria = sefaria_authors(repo / SEFARIA_AUTHOR_CSV) if "sefaria_author" in kinds else {}
    descriptions = (
        sefaria_descriptions(repo / SEFARIA_METADATA_CSV) if kinds & set(SEFARIA_COLUMNS) else {}
    )
    books = None
    if git_rev is not None and "line2" in kinds:
        books = git_books(repo, git_rev, bases, {lock.key: lock.value for lock in locks if lock.kind == "line2"})
        if books.base is None:
            notes.append(f"line2: no base commit is an ancestor of {git_rev}; only the paths were checked")
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
        elif lock.kind == "line2" and books is not None:
            if lock.key not in books.paths:
                moved = books.moves.get(lock.key)
                if moved in books.paths and is_packaged_book(moved):
                    notes.append(f"MOVED: {lock.where}: {lock.key!r} -> {moved!r} unchanged; "
                                 "follow_lock_renames.py moves the row on main")
                else:
                    problems.append(f"MISSING: {lock.where}: the book file {lock.key!r} does not exist in {git_rev}")
                continue
            if lock.key not in books.second_lines:
                continue  # unchanged since the base: its second line is what was checked then
            live = [books.second_lines[lock.key]]
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
    if books is not None and books.base is not None:
        notes.append(f"line2: {len(books.second_lines)} changed books compared since {books.base[:12]}")
    return problems, checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--lock", type=Path, help=f"default: <repo>/{LOCK_PATH}")
    parser.add_argument("--skip", action="append", default=[], choices=KINDS, help="leave this kind unchecked")
    parser.add_argument("--git-rev", metavar="REV", help="read the line2 books from this commit")
    parser.add_argument("--since", action="append", default=[], metavar="BASE",
                        help="with --git-rev: compare line2 only for books changed since BASE (repeatable)")
    args = parser.parse_args(argv)
    lock_path = args.lock if args.lock is not None else args.repo / LOCK_PATH
    skip = frozenset(args.skip)
    try:
        locks = load_locks(lock_path)
        notes: list[str] = []
        problems, checked = check(locks, args.repo, skip, args.git_rev, args.since, notes)
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for line in notes:
        print(line)
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
        print("(python3 .github/scripts/update_locked_metadata.py --key KIND:KEY, or --all-changed-vs REF;")
        print("a book moved with an edit: --key line2:OLD --key line2:NEW --drop-missing --add-new).")
        return 1
    print(f"lock matches: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
