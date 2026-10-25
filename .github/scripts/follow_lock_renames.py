#!/usr/bin/env python3
"""Move the rows of .github/data/locked_metadata.tsv along with a book rename or move.

Two kinds of keys move, each with the change that moved it:

* author / sefaria_short / sefaria_long rows are keyed by a title in metadata.json or in
  ForDB/sefaria_metadata_changes.csv.  validate_fordb_book_names.py --fix rewrites those
  titles after a book file is renamed and lists every rewritten value in fordb_renamed.json
  (`changes`: file, kind "renamed", from, to).  A row follows exactly the value written in
  its own file: metadata.json holds the raw file name, the CSV the DB spelling (״ for '' or ").
  A rename the validator kept back (kept_conflict, blocked) wrote nothing, so its rows stay.
* line2 rows are keyed by the repository path of the book.  With --base, a locked path that
  is gone from HEAD follows git's exact renames (R100: same content, so the same second line)
  in BASE..HEAD, to another packaged book path.  A file moved with an edit, or out of the
  packaged roots (extraBooks, Dicta לא ערוך), is left for a human: the check reports it.

When a row for the new key already exists, the old row is dropped if it holds the same value;
otherwise both stay and check_locked_metadata.py reports the conflict.

When the lock changed, its path is appended to fordb_touched.txt (NUL separated, as the
validator writes it) so the auto-fix commit stages it, and fordb_commit_message.txt is
written when the validator did not write one.

Exit codes: 0 done (also when nothing changed), 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import check_locked_metadata as lock

RENAMED_REPORT = "fordb_renamed.json"
TOUCHED_LIST = "fordb_touched.txt"
COMMIT_MESSAGE = "fordb_commit_message.txt"
# The file whose title column keys each kind, as named in the report.
KIND_FILES = {
    "author": lock.METADATA_JSON,
    "sefaria_short": lock.SEFARIA_METADATA_CSV,
    "sefaria_long": lock.SEFARIA_METADATA_CSV,
}


def follow_renames(text: str, renames: dict[str, dict[str, str]]) -> tuple[str, int, list[str]]:
    """The lock text with keys moved, how many rows were moved or dropped, and warnings.

    renames: kind -> {old key: new key}.  A key is compared with the keys that remain after
    every move (a chain a -> b, b -> c moves both rows); two rows that would end under one key
    with different values both stay where they are, for a human."""
    lines = text.split("\n")
    rows = []  # (index in lines, kind, key, value, new key or None)
    for number, line in enumerate(lines[1:], start=1):
        cols = line.rstrip("\r").split("\t")
        if line.startswith("#") or len(cols) != 4 or cols[0] not in renames:
            continue
        where = f"lock:{number + 1}"
        key = lock.unescape(cols[1], where)
        new_key = renames[cols[0]].get(key)
        rows.append((number, cols[0], key, lock.unescape(cols[2], where), new_key if new_key != key else None))
    # Rows that end under the same key: (kind, final key) -> values.
    final: dict[tuple[str, str], set[str]] = {}
    for _n, kind, key, value, new_key in rows:
        final.setdefault((kind, new_key or key), set()).add(value)
    staying = {(kind, key) for _n, kind, key, _v, new_key in rows if new_key is None}
    warnings, moved, drop, inserted, changed = [], [], set(), set(), 0
    for number, kind, key, value, new_key in rows:
        if new_key is None:
            continue
        if len(final[kind, new_key]) > 1:
            warnings.append(f"{kind} {key!r} -> {new_key!r}: another value is locked there; both kept")
            continue
        changed += 1
        drop.add(number)
        if (kind, new_key) in staying or (kind, new_key) in inserted:
            continue  # the same lock under the new key already: the old row goes
        inserted.add((kind, new_key))
        line = lines[number]
        cols = line.rstrip("\r").split("\t")
        cols[1] = lock.escape(new_key)
        moved.append((kind, new_key, "\t".join(cols) + ("\r" if line.endswith("\r") else "")))
    out = [line for n, line in enumerate(lines) if n not in drop]
    for kind, key, row in moved:  # into sorted position, as update_locked_metadata.py inserts
        order = _order(kind, key)
        end = len(out) - 1 if out[-1] == "" else len(out)  # before the final newline
        at = next((i for i in range(1, end) if _sorts_after(out[i], order)), end)
        out.insert(at, row)
    return "\n".join(out), changed, warnings


def _order(kind: str, key: str) -> tuple[int, bytes]:
    return (lock.KINDS.index(kind), key.encode("utf-8"))


def _sorts_after(line: str, order: tuple[int, bytes]) -> bool:
    cols = line.rstrip("\r").split("\t")
    if line.startswith("#") or len(cols) != 4 or cols[0] not in lock.KINDS:
        return False
    return _order(cols[0], lock.unescape(cols[1], "lock")) > order


def read_title_renames(path: Path) -> dict[str, dict[str, str]]:
    """kind -> {old title: new title}, from the values the validator wrote."""
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, list):
        raise ValueError(f"{path}: expected a JSON list")
    by_file: dict[str, dict[str, str]] = {}
    for item in report:
        for change in item.get("changes", []):
            if change.get("kind") != "renamed" or "from" not in change:
                continue
            if not isinstance(change["from"], str) or not isinstance(change["to"], str):
                raise ValueError(f"{path}: bad change {change!r}")
            by_file.setdefault(change["file"], {})[change["from"]] = change["to"]
    return {kind: by_file.get(file, {}) for kind, file in KIND_FILES.items()}


def read_path_moves(repo: Path, bases, text: str) -> dict[str, str]:
    """old path -> new path for the locked line2 paths that are gone from HEAD."""
    keys = [l.key for l in lock.parse_locks(text, lock.LOCK_PATH) if l.kind == "line2"]
    base = lock.pick_base(repo, bases, "HEAD")
    if base is None or not keys:
        return {}
    tree = lock._git(repo, "ls-tree", "-r", "-z", "--name-only", "--full-tree", "HEAD").decode("utf-8")
    paths = set(filter(None, tree.split("\0")))
    gone = [key for key in keys if key not in paths]
    if not gone:
        return {}
    moves = lock.exact_moves(repo, base, "HEAD")
    return {key: moves[key] for key in gone if moves.get(key) in paths and lock.is_packaged_book(moves[key])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", action="append", default=[], metavar="REV",
                        help="follow line2 paths renamed since the first of these that is an ancestor of HEAD")
    args = parser.parse_args(argv)
    report = args.repo / RENAMED_REPORT
    lock_path = args.repo / lock.LOCK_PATH
    if not report.is_file() and not args.base:
        print("no fordb_renamed.json and no --base: nothing to follow")
        return 0
    try:
        before = lock_path.read_text(encoding="utf-8")
        renames = read_title_renames(report) if report.is_file() else {kind: {} for kind in KIND_FILES}
        renames["line2"] = read_path_moves(args.repo, args.base, before) if args.base else {}
        after, changed, warnings = follow_renames(before, renames)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"::warning title=Locked metadata::{warning}")
    if changed:
        lock_path.write_text(after, encoding="utf-8", newline="")
        with (args.repo / TOUCHED_LIST).open("ab") as touched:
            touched.write(lock.LOCK_PATH.encode("utf-8") + b"\0")
        message = args.repo / COMMIT_MESSAGE
        if not message.exists():
            message.write_text("ci(lock): follow moved book files in the metadata lock\n", encoding="utf-8")
    counts = ", ".join(f"{kind} {len(items)}" for kind, items in renames.items())
    print(f"{changed} lock rows followed ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
