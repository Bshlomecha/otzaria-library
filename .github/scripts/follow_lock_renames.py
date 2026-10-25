#!/usr/bin/env python3
"""Move the rows of .github/data/locked_metadata.tsv along with a book rename.

validate_fordb_book_names.py --fix follows a renamed book file through the files that
identify a book by title (metadata.json, sefaria_metadata_changes.csv, ...) and writes
fordb_renamed.json.  The lock keys the author / sefaria_short / sefaria_long rows by that
same title, so without this step the auto-fix push would leave them pointing at the old title
and check_locked_metadata.py would fail on the very next run with MISSING.

For every rename old -> new in fordb_renamed.json this script rewrites the key of those rows
in place (the value stays: the rename must not change it, and the check compares it on the
next run).  When a row for the new title already exists, the old row is dropped.  line2 rows
are keyed by repository path, which the report does not carry, and CI skips them; they are
left for update_locked_metadata.py --drop-missing --add-new.

When the lock changed, its path is appended to fordb_touched.txt (NUL separated, as the
validator writes it) so the auto-fix commit stages it.

Exit codes: 0 done (also when nothing changed), 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import check_locked_metadata as lock

TITLE_KINDS = ("author", "sefaria_short", "sefaria_long")
RENAMED_REPORT = "fordb_renamed.json"
TOUCHED_LIST = "fordb_touched.txt"


def follow_renames(text: str, renames: dict[str, str]) -> tuple[str, int]:
    """The lock text with title keys renamed, and how many rows were rewritten or dropped."""
    lines = text.split("\n")
    existing = set()
    for line in lines[1:]:
        cols = line.rstrip("\r").split("\t")
        if len(cols) == 4 and cols[0] in TITLE_KINDS:
            existing.add((cols[0], lock.unescape(cols[1], "lock")))
    out, changed = [lines[0]], 0
    for number, line in enumerate(lines[1:], start=2):
        cols = line.rstrip("\r").split("\t")
        if line.startswith("#") or len(cols) != 4 or cols[0] not in TITLE_KINDS:
            out.append(line)
            continue
        key = lock.unescape(cols[1], f"lock:{number}")
        if key not in renames:
            out.append(line)
            continue
        changed += 1
        if (cols[0], renames[key]) in existing:
            continue
        cols[1] = lock.escape(renames[key])
        out.append("\t".join(cols))
    return "\n".join(out), changed


def read_renames(path: Path) -> dict[str, str]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, list):
        raise ValueError(f"{path}: expected a JSON list")
    return {item["old"]: item["new"] for item in report if item.get("old") and item.get("new")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    report = args.repo / RENAMED_REPORT
    lock_path = args.repo / lock.LOCK_PATH
    try:
        if not report.is_file():
            print("no fordb_renamed.json: nothing to follow")
            return 0
        renames = read_renames(report)
        before = lock_path.read_text(encoding="utf-8")
        after, changed = follow_renames(before, renames)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if changed:
        lock_path.write_text(after, encoding="utf-8", newline="")
        with (args.repo / TOUCHED_LIST).open("ab") as touched:
            touched.write(lock.LOCK_PATH.encode("utf-8") + b"\0")
    print(f"{changed} lock rows followed {len(renames)} renames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
