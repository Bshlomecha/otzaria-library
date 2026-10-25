#!/usr/bin/env python3
"""Rewrite rows of .github/data/locked_metadata.tsv to the live values (the unlock tool).

check_locked_metadata.py fails when a locked value differs from its row.  When the
change is intended, the row changes in the same commit; this script writes it:

    # these keys, to their current values in the working tree
    update_locked_metadata.py --key author:TITLE --key line2:PATH/TO/BOOK.txt

    # every key of a locked kind that this branch changed: the working tree (untracked
    # files included) against the merge base of REF and HEAD
    update_locked_metadata.py --all-changed-vs origin/main [--add-new] [--drop-missing]

The comparison starts at the merge base, not at REF itself: a branch behind REF would
otherwise count everything REF changed since the fork as its own change, and lock REF's
old values (the gate would then ask to revert REF's fix after the merge).

--add-new also locks keys that are not locked yet (with --key: the listed keys; with
--all-changed-vs: every changed or new value of the five kinds, except an empty value,
which locks nothing, and line2 of a file outside the packaged book roots).  --drop-missing deletes
the row of a key that no longer exists (a renamed or removed book, a deleted CSV row);
without it such a row is left for a human.  Existing rows keep their place; new rows are
inserted in sorted position, so parallel updates rarely touch the same lines.

The library functions (changed_values, apply_updates) take readers -- callables from a
repository path to its text, or None -- so the same logic runs on a working tree or on
git objects (the catalog editor's PR tooling runs it on a branch before pushing).

Exit codes: 0 done (also when nothing changed), 2 bad input.
"""

from __future__ import annotations

import argparse
import bisect
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

import check_locked_metadata as lock
from check_locked_metadata import is_packaged_book

Reader = Callable[[str], "str | None"]
GREY = frozenset(chr(c) for c in range(0x2061, 0x2065))  # never locked as a new value


def file_reader(repo: Path) -> Reader:
    def read(path: str) -> str | None:
        target = repo / path
        return target.read_text(encoding="utf-8") if target.is_file() else None
    return read


def git_reader(repo: Path, ref: str) -> Reader:
    def read(path: str) -> str | None:
        result = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True)
        return result.stdout.decode("utf-8") if result.returncode == 0 else None
    return read


def table_values(read: Reader, kind: str) -> dict[str, str | None] | None:
    """key -> value for one of the four table kinds; None when the file is missing.

    author: a title whose entries disagree (or have no author) maps to None: it cannot be locked."""
    if kind == "author":
        text = read(lock.METADATA_JSON)
        if text is None:
            return None
        out: dict[str, str | None] = {}
        for title, authors in lock.parse_metadata_authors(text).items():
            out[title] = authors[0] if len(set(authors)) == 1 and isinstance(authors[0], str) else None
        return out
    if kind == "sefaria_author":
        text = read(lock.SEFARIA_AUTHOR_CSV)
        return None if text is None else dict(lock.parse_sefaria_authors(text))
    text = read(lock.SEFARIA_METADATA_CSV)
    return None if text is None else dict(lock.parse_sefaria_descriptions(text)[kind])


def live_value(read: Reader, kind: str, key: str, cache: dict) -> tuple[bool, str | None]:
    """(exists, value) of one key."""
    if kind == "line2":
        text = read(key)
        return (text is not None, None if text is None else lock.second_line_of(text))
    if kind not in cache:
        cache[kind] = table_values(read, kind) or {}
    table = cache[kind]
    return (key in table, table.get(key))


def changed_values(old: Reader, new: Reader, changed_paths: Iterable[str]) -> dict[tuple[str, str], str | None]:
    """(kind, key) -> new value (None = the key is gone) for every key whose value differs.

    changed_paths: the repository paths that differ between the two trees (git diff
    --name-only); a table kind is compared only when its file is among them."""
    paths = set(changed_paths)
    out: dict[tuple[str, str], str | None] = {}
    files = {
        "author": lock.METADATA_JSON,
        "sefaria_author": lock.SEFARIA_AUTHOR_CSV,
        "sefaria_short": lock.SEFARIA_METADATA_CSV,
        "sefaria_long": lock.SEFARIA_METADATA_CSV,
    }
    for kind, path in files.items():
        if path not in paths:
            continue
        before, after = table_values(old, kind) or {}, table_values(new, kind) or {}
        for key in before.keys() | after.keys():
            if key in after and after[key] is None:
                continue  # author: entries with this title disagree; left for the gate to report
            if key not in after:
                out[kind, key] = None
            elif key not in before or before[key] != after[key]:
                out[kind, key] = after[key]
    for path in paths:
        if not path.endswith(".txt"):
            continue
        before_text, after_text = old(path), new(path)
        before = None if before_text is None else lock.second_line_of(before_text)
        after = None if after_text is None else lock.second_line_of(after_text)
        if after_text is None:
            out["line2", path] = None
        elif after is None:
            continue  # no second line: nothing to lock, left for the gate to report
        elif before_text is None or before != after:
            out["line2", path] = after
    return out


def _row(kind: str, key: str, value: str, note: str) -> str:
    return "\t".join([kind, lock.escape(key), lock.escape(value), note])


def _order(kind: str, key: str) -> tuple[int, bytes]:
    return (lock.KINDS.index(kind), key.encode("utf-8"))


def apply_updates(
    lock_text: str,
    updates: dict[tuple[str, str], str | None],
    *,
    add_new: bool,
    drop_missing: bool,
    note: str,
) -> tuple[str, dict[str, int]]:
    """The lock file with `updates` applied, and counts: updated, added, dropped, kept_missing, skipped."""
    lines = lock_text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0].rstrip("\r").split("\t") != lock.HEADER:
        raise ValueError(f"{lock.LOCK_PATH}: the header must be {'<TAB>'.join(lock.HEADER)}")
    stats = {"updated": 0, "added": 0, "dropped": 0, "kept_missing": 0, "skipped": 0}
    seen: set[tuple[str, str]] = set()
    out = [lines[0]]
    for n, line in enumerate(lines[1:], start=2):
        if not line.strip() or line.startswith("#"):
            out.append(line)
            continue
        cols = line.split("\t")
        if len(cols) != 4:
            raise ValueError(f"{lock.LOCK_PATH}:{n}: expected 4 columns, found {len(cols)}")
        where = f"{lock.LOCK_PATH}:{n}"
        kind, key, value = cols[0], lock.unescape(cols[1], where), lock.unescape(cols[2], where)
        seen.add((kind, key))
        if (kind, key) not in updates:
            out.append(line)
            continue
        new = updates[kind, key]
        if new is None:
            if drop_missing:
                stats["dropped"] += 1
            else:
                stats["kept_missing"] += 1
                out.append(line)
            continue
        if new != value:
            stats["updated"] += 1
            out.append(_row(kind, key, new, note or cols[3]))
        else:
            out.append(line)
    if add_new:
        # Each new row goes before the first data row that sorts after it (the file is
        # kept sorted by kind, then key bytes), else at the end.
        orders, positions = [], []
        for i in range(1, len(out)):
            cols = out[i].split("\t")
            if out[i].startswith("#") or len(cols) != 4 or cols[0] not in lock.KINDS:
                continue
            orders.append(_order(cols[0], lock.unescape(cols[1], f"{lock.LOCK_PATH}:{i + 1}")))
            positions.append(i)
        inserts: list[tuple[int, str]] = []
        for (kind, key), value in sorted(updates.items(), key=lambda item: _order(*item[0])):
            if (kind, key) in seen or value is None:
                continue
            if (kind not in lock.KINDS or not value or any(c in GREY for c in value)
                    or (kind == "line2" and not is_packaged_book(key))):
                stats["skipped"] += 1
                continue
            at = bisect.bisect_right(orders, _order(kind, key))
            inserts.append((positions[at] if at < len(positions) else len(out), _row(kind, key, value, note)))
            stats["added"] += 1
        for at, row in reversed(inserts):  # stable: equal positions keep sorted order
            out.insert(at, row)
    return "\n".join(out) + "\n", stats


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout.decode("utf-8")


def merge_base(repo: Path, ref: str) -> str:
    return _git(repo, "merge-base", ref, "HEAD").strip()


def git_changed_paths(repo: Path, base: str) -> list[str]:
    """The paths that differ between base and the working tree, untracked files included."""
    changed = _git(repo, "diff", "--no-renames", "--name-only", "-z", base, "--")
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted({p for p in (changed + untracked).split("\0") if p})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--lock", type=Path, help=f"default: <repo>/{lock.LOCK_PATH}")
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--key", action="append", metavar="KIND:KEY", help="a key to set to its live value (repeatable)")
    what.add_argument("--all-changed-vs", metavar="REF", help="every locked kind whose value differs from REF")
    parser.add_argument("--add-new", action="store_true", help="also lock keys that are not locked yet")
    parser.add_argument("--drop-missing", action="store_true", help="delete rows whose key no longer exists")
    parser.add_argument("--note", default="", help="note column for updated and new rows (default: keep / empty)")
    args = parser.parse_args(argv)
    lock_path = args.lock if args.lock is not None else args.repo / lock.LOCK_PATH
    read = file_reader(args.repo)
    try:
        text = lock_path.read_text(encoding="utf-8")
        if args.key:
            updates: dict[tuple[str, str], str | None] = {}
            cache: dict = {}
            for item in args.key:
                kind, sep, key = item.partition(":")
                if not sep or kind not in lock.KINDS or not key:
                    raise ValueError(f"--key {item!r}: expected KIND:KEY with KIND one of {', '.join(lock.KINDS)}")
                exists, value = live_value(read, kind, key, cache)
                if exists and value is None:
                    raise ValueError(f"--key {item!r}: the live value cannot be locked (no second line, or entries disagree)")
                updates[kind, key] = value if exists else None
        else:
            base = merge_base(args.repo, args.all_changed_vs)
            paths = git_changed_paths(args.repo, base)
            updates = changed_values(git_reader(args.repo, base), read, paths)
        new_text, stats = apply_updates(
            text, updates, add_new=args.add_new, drop_missing=args.drop_missing, note=args.note
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if new_text != text:
        lock_path.write_text(new_text, encoding="utf-8", newline="")
    print(", ".join(f"{name} {count}" for name, count in stats.items()) + f" ({lock_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
