#!/usr/bin/env python3
"""Fail when a packaged Otzaria book becomes covered ("shadowed") by a Sefaria book.

The DB build imports Sefaria first and Otzaria after it.  createAndProcessBook in
SeforimLibrary generator/otzariasqlite/.../Generator.kt skips an Otzaria file when

    repository.getBookByHeRef(normalizeBookTitle(stem))   # SELECT * FROM book WHERE heRef = ? LIMIT 1
    ... and that row's source name == "Sefaria"

("already exists from Sefaria (priority source)").  The book then silently changes
from Otzaria to Sefaria: new book id, new line ids, orphaned bookmarks.  This check
replicates that decision exactly and compares it with a committed baseline, so a
human decides (rename, blacklist, or accept) whenever a file NEWLY becomes covered.

What the generator decides, and what this script replicates:
  * the title is normalizeBookTitle(file stem) == db_title() of
    validate_fordb_book_names.py (CategoryLabels.normalize + the תנ"ך special case);
  * it is compared verbatim (SQLite BINARY) with book.heRef of Sefaria books.  A
    Sefaria book's heRef is the export's Hebrew title and nothing rewrites it later
    (book_renames.csv changes book.title only), so book_renames never applies;
  * files never reach that comparison when they sit directly under the library root,
    when their file name is in files-blacklist.txt, or when their manifest source
    (the top-level folder of the first files_manifest.json key with that archive
    path) is in source-blacklist.txt;
  * the same archive path in several BOOK_ROOTS is one file in otzaria_latest.zip.

Sefaria side: the heRefs of every Sefaria book in the latest SeforimLibrary release
DB, i.e. after the books/authors blacklists and every other import rule.  A newer
Sefaria export that has not been built yet is covered by --export-titles: titles in
its titles.json that were absent from the titles.json of the export the DB was built
from.  Such a title may still be blacklisted by the next build, so those files are
reported as "pending" rather than certain, but they fail the check all the same.

Baseline: .github/data/sefaria_shadowed_books.txt, one archive path (relative to the
"אוצריא" root of otzaria_latest.zip) per line.  Both directions fail: a covered file
missing from the baseline, and a baseline line that is no longer covered.

Exit codes: 0 baseline matches, 1 baseline mismatch, 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from validate_fordb_book_names import DB_BOOK_PREFIXES, db_title

BASELINE_PATH = ".github/data/sefaria_shadowed_books.txt"
BASELINE_HEADER = (
    "# Packaged Otzaria books that the DB build skips because a Sefaria book has the same heRef.\n"
    "# One path per line, relative to the אוצריא root of otzaria_latest.zip.\n"
    "# Checked by .github/scripts/check_sefaria_shadowed_books.py; see that file before editing.\n"
)
SYMLINK_MODE = "120000"
# Generator.loadSourceBlacklistFromResources: used when the file is missing or empty.
SOURCE_BLACKLIST_FALLBACK = frozenset({"wiki_jewish_books"})
# HearotCompanionMerge.isMergeableCompanionTitle
COMPANION_PREFIX = "הערות על "
SEFARIA_HEREFS_SQL = (
    "SELECT b.heRef FROM book b JOIN source s ON s.id = b.sourceId "
    "WHERE s.name = 'Sefaria' AND b.heRef IS NOT NULL"
)


@dataclass(frozen=True)
class LibraryFile:
    archive_path: str  # relative to the אוצריא root of otzaria_latest.zip
    repo_path: str  # the copy that lands in the archive (last root wins)
    source: str  # Generator.getSourceNameFor

    @property
    def title(self) -> str:
        return db_title(self.archive_path.rsplit("/", 1)[-1].rsplit(".", 1)[0])


@dataclass(frozen=True)
class Covered:
    file: LibraryFile
    pending: bool  # covered only by a Sefaria export that is not built yet


def read_resource_lines(path: Path) -> list[str]:
    """loadFileNameBlacklistFromResources / loadSourceBlacklistFromResources."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]


def load_source_blacklist(path: Path | None) -> frozenset[str]:
    if path is None or not path.is_file():
        return SOURCE_BLACKLIST_FALLBACK
    return frozenset(read_resource_lines(path)) or SOURCE_BLACKLIST_FALLBACK


def load_files_blacklist(path: Path | None) -> frozenset[str]:
    if path is None or not path.is_file():
        return frozenset()
    return frozenset(read_resource_lines(path))


def library_files(paths: list[str]) -> list[LibraryFile]:
    """Packaged .txt books as one archive entry each, from repository paths."""
    by_archive: dict[str, list[tuple[int, str]]] = {}
    for path in paths:
        index = next((i for i, p in enumerate(DB_BOOK_PREFIXES) if path.startswith(p)), None)
        if index is None or not path.endswith(".txt"):
            continue
        by_archive.setdefault(path[len(DB_BOOK_PREFIXES[index]):], []).append((index, path))
    result = []
    for archive_path, copies in by_archive.items():
        # copy_regular_tree(overwrite=True): the last root in BOOK_ROOTS order wins.
        repo_path = max(copies)[1]
        # files_manifest.json is written with sort_keys and read with putIfAbsent.
        source = min(path for _, path in copies).split("/", 1)[0]
        result.append(LibraryFile(archive_path, repo_path, source))
    return sorted(result, key=lambda f: f.archive_path.encode("utf-8"))


def git_library_paths(commit: str, root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "-z", commit, "--",
         *(p.rstrip("/") for p in DB_BOOK_PREFIXES)],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    paths = []
    for record in filter(None, out.split("\0")):
        meta, path = record.split("\t", 1)
        mode, kind, _ = meta.split(" ")
        if kind == "blob" and mode != SYMLINK_MODE:
            paths.append(path)
    return paths


def importable(file: LibraryFile, files_blacklist: frozenset[str], source_blacklist: frozenset[str]) -> bool:
    """True when the file reaches the Sefaria-priority check in createAndProcessBook."""
    if "/" not in file.archive_path:  # library root: parentCategoryId == null
        return False
    if file.archive_path.rsplit("/", 1)[-1] in files_blacklist:
        return False
    return file.source not in source_blacklist


def covered_files(
    files: list[LibraryFile],
    sefaria_herefs: set[str],
    pending_titles: set[str],
    files_blacklist: frozenset[str],
    source_blacklist: frozenset[str],
) -> list[Covered]:
    result = []
    for file in files:
        if not importable(file, files_blacklist, source_blacklist):
            continue
        if file.title in sefaria_herefs:
            result.append(Covered(file, pending=False))
        elif file.title in pending_titles:
            result.append(Covered(file, pending=True))
    return result


def pending_export_titles(latest: dict[str, str], built: dict[str, str]) -> set[str]:
    """Hebrew titles in the newest export that the built export did not have."""
    return {he for he in latest.values() if he} - {he for he in built.values() if he}


def read_titles_json(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{path}: expected a non-empty {{English: Hebrew}} object")
    return data


def read_list(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


def sefaria_herefs_from_db(db: Path) -> list[str]:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        rows = [row[0] for row in conn.execute(SEFARIA_HEREFS_SQL)]
    if not rows:
        raise ValueError(f"{db}: no Sefaria books")
    return sorted(set(rows), key=lambda t: t.encode("utf-8"))


def write_baseline(path: Path, covered: list[Covered]) -> None:
    body = "".join(c.file.archive_path + "\n" for c in covered)
    path.write_text(BASELINE_HEADER + body, encoding="utf-8")


def report(new: list[Covered], stale: list[str], companions: set[str]) -> list[str]:
    out = []
    for c in new:
        f = c.file
        why = (
            f"the newest Sefaria export adds a book titled {f.title!r}; unless the next build blacklists it, "
            "the next build will skip this file"
            if c.pending
            else f"the Sefaria book with heRef {f.title!r} makes the build skip this file"
        )
        out.append(f"NEWLY COVERED: {f.repo_path} (archive path {f.archive_path!r}): {why}.")
        if COMPANION_PREFIX + f.title in companions:
            out.append(
                f"  its companion {COMPANION_PREFIX + f.title!r} is then no longer merged into it and "
                "is imported as a standalone book (Generator.buildHearotMergePlans)."
            )
    for archive_path in stale:
        out.append(f"NO LONGER COVERED: baseline entry {archive_path!r} is not a covered Otzaria file any more.")
    if new:
        out += [
            "",
            "A covered book stops being an Otzaria book: its title now opens the Sefaria book, with another",
            "book id and other line ids, and every bookmark on the Otzaria book is orphaned.",
            "Decide, then make the check pass:",
            "  * keep the Otzaria book: rename the file so its title differs from the Sefaria heRef",
            "    (and follow the rename in ForDB/metadata/links), or",
            "  * keep the Otzaria book: add the Sefaria title to SeforimLibrary",
            "    generator/sefariasqlite/src/jvmMain/resources/books_blacklist.txt, or",
            "  * accept the Sefaria book: add the archive path to " + BASELINE_PATH + ".",
        ]
    if stale:
        out += [
            "",
            "Remove stale lines from " + BASELINE_PATH + " (the file becomes an Otzaria book again, with a new id).",
        ]
    if new or stale:
        out.append("Regenerate the whole baseline with --write-baseline once every entry is intended.")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract-herefs", help="write the Sefaria heRefs of a seforim.db, one per line")
    extract.add_argument("--db", required=True, type=Path)
    extract.add_argument("--output", required=True, type=Path)

    check = sub.add_parser("check", help="compare covered files with the baseline")
    check.add_argument("--sefaria-herefs", required=True, type=Path)
    check.add_argument("--export-titles", type=Path, help="titles.json of the newest SefariaExport release")
    check.add_argument("--built-export-titles", type=Path, help="titles.json of the export the DB was built from")
    check.add_argument("--files-blacklist", required=True, type=Path)
    check.add_argument("--source-blacklist", required=True, type=Path)
    check.add_argument("--baseline", type=Path, default=Path(BASELINE_PATH))
    check.add_argument("--commit", default="HEAD")
    check.add_argument("--repo", type=Path, default=Path("."))
    check.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "extract-herefs":
            herefs = sefaria_herefs_from_db(args.db)
            args.output.write_text("".join(t + "\n" for t in herefs), encoding="utf-8")
            print(f"wrote {len(herefs)} Sefaria heRefs to {args.output}")
            return 0

        if (args.export_titles is None) != (args.built_export_titles is None):
            raise ValueError("--export-titles and --built-export-titles go together")
        for path in (args.sefaria_herefs, args.files_blacklist, args.source_blacklist):
            if not path.is_file():
                raise ValueError(f"{path}: missing")
        herefs = set(read_list(args.sefaria_herefs))
        if not herefs:
            raise ValueError(f"{args.sefaria_herefs}: no Sefaria heRefs")
        pending = set()
        if args.export_titles is not None:
            pending = pending_export_titles(
                read_titles_json(args.export_titles), read_titles_json(args.built_export_titles)
            )
        files = library_files(git_library_paths(args.commit, args.repo))
        if not files:
            raise ValueError(f"no packaged library books at {args.commit}")
        covered = covered_files(
            files, herefs, pending,
            load_files_blacklist(args.files_blacklist), load_source_blacklist(args.source_blacklist),
        )
    except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(
        f"{len(files)} packaged books, {len(herefs)} Sefaria heRefs, "
        f"{len(pending)} Sefaria titles not built yet, {len(covered)} covered files"
    )
    if args.write_baseline:
        write_baseline(args.baseline, covered)
        print(f"wrote {len(covered)} entries to {args.baseline}")
        return 0

    baseline = read_list(args.baseline) if args.baseline.is_file() else None
    if baseline is None:
        print(f"error: {args.baseline} is missing", file=sys.stderr)
        return 2
    if len(set(baseline)) != len(baseline):
        print(f"error: {args.baseline} has duplicate lines", file=sys.stderr)
        return 2
    covered_paths = {c.file.archive_path for c in covered}
    new = [c for c in covered if c.file.archive_path not in set(baseline)]
    stale = [p for p in baseline if p not in covered_paths]
    companions = {f.title for f in files if f.title.startswith(COMPANION_PREFIX)}
    lines = report(new, stale, companions)
    for line in lines:
        print(line)
    if lines:
        return 1
    print(f"baseline matches: {len(covered)} covered files, all expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
