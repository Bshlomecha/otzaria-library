# -*- coding: utf-8 -*-
"""
Insert all שפת אמת commentary links into Otzaria seforim.db.

Canonical direction for COMMENTARY (like Rashi):
  source = base masechet, target = שפת אמת על ...

JSON format is the opposite (commentary -> base), so we flip.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SEF_DB = Path(r"C:\ProgramData\otzaria\books\seforim.db")
LINKS_DIR = REPO_ROOT / "DictaToOtzaria" / "ערוך" / "links"
BACKUP_DIR = REPO_ROOT / "_db_backups"

# The generator's storage rules (flip / stored type / flags / heading lines) live in one
# place, the otzaria-db-linker skill's engine, which ports them from SeforimLibrary
# Generator.kt and is tested against it. Reuse it rather than keep a third copy.
_ICL_PATH = REPO_ROOT / ".claude" / "skills" / "otzaria-db-linker" / "scripts" / "insert_commentary_link.py"
_icl_spec = importlib.util.spec_from_file_location("insert_commentary_link", _ICL_PATH)
icl = importlib.util.module_from_spec(_icl_spec)
_icl_spec.loader.exec_module(icl)

PAIRS = [
    ("שפת אמת על ברכות", "ברכות"),
    ("שפת אמת על שבת", "שבת"),
    ("שפת אמת על עירובין", "עירובין"),
    ("שפת אמת על פסחים", "פסחים"),
    ("שפת אמת על זבחים", "זבחים"),
    ("שפת אמת על מנחות", "מנחות"),
    ("שפת אמת על ערכין", "ערכין"),
    ("שפת אמת על תמורה", "תמורה"),
    ("שפת אמת על כריתות", "כריתות"),
    ("שפת אמת על מעילה", "מעילה"),
    # בכורות: book exists, no links file yet
]

def canonical_connection_type(value: object) -> str | None:
    """The ConnectionType name SeforimLibrary parses `value` as; None if unknown."""
    if not isinstance(value, str):
        return None
    try:
        return icl.canonical_type(value)
    except ValueError:
        return None


# This script writes every link flipped (sourceBookId = the book named by path_2,
# targetBookId = the citing book). The library generator (SeforimLibrary
# otzariasqlite/Generator.kt) stores a citing-named entry that way only for
#   * SOURCE -> flipped, stored COMMENTARY (`flip = declaredType == SOURCE`), and
#   * ORIENTED_DEPENDANT_TYPES, when the citing title declares the base
#     (`reversedDependant`) -> flipped, stored as the declared type.
# Every other type (lateral references, EXPLICATION, OTHER, LINKER) is stored
# unflipped or not at all, so writing it here would store it backwards. Those are
# refused loudly by `preflight_connection_types` instead of being skipped; an oriented
# entry the generator would NOT flip (see icl.plan_storage) is refused in insert_pair.
# Stored ids are NOT hard-coded: they are read by name from the DB's connection_type
# table (ids follow enum order in a fresh build, but FOOTNOTES only exists in DBs
# built from SeforimLibrary e36a042 on — an older DB has no row for it).
STORED_TYPE_FOR = {
    "SOURCE": "COMMENTARY",
    "COMMENTARY": "COMMENTARY",
    "SUPER_COMMENTARY": "SUPER_COMMENTARY",
    "TARGUM": "TARGUM",
    "MIDRASH": "MIDRASH",
    "PARSHANUT": "PARSHANUT",
    "DIBUR_HAMATCHIL": "DIBUR_HAMATCHIL",
    "EIN_MISHPAT": "EIN_MISHPAT",
    "ELUCIDATION": "ELUCIDATION",
    "FOOTNOTES": "FOOTNOTES",
}


def stored_type_for(declared: object) -> str | None:
    """Stored ConnectionType name for a declared value, or None if unsupported here."""
    canonical = canonical_connection_type(declared)
    return STORED_TYPE_FOR.get(canonical) if canonical else None


def load_connection_type_ids(cur: sqlite3.Cursor) -> dict[str, int]:
    """name -> id from the target DB's own connection_type table."""
    return {str(name): int(cid) for cid, name in cur.execute("SELECT id, name FROM connection_type")}


def preflight_connection_types(
    entries_by_file: dict[str, list[dict]], type_ids: dict[str, int]
) -> list[str]:
    """Every problem that would make the run drop entries; empty = safe to write."""
    unsupported: Counter = Counter()
    needed: set[str] = set()
    for name, entries in entries_by_file.items():
        for item in entries:
            declared = item.get("Conection Type")
            stored = stored_type_for(declared)
            if stored is None:
                unsupported[(name, repr(declared))] += 1
            else:
                needed.add(stored)
    problems = [
        f"{n} entries in {name} have unsupported Conection Type {declared} "
        f"(supported: source + {', '.join(sorted(k.lower() for k in STORED_TYPE_FOR if k != 'SOURCE'))})"
        for (name, declared), n in sorted(unsupported.items())
    ]
    problems += [
        f"connection_type {name!r} is missing from this seforim.db "
        f"(built before SeforimLibrary added it) -- cannot store those links"
        for name in sorted(needed - set(type_ids))
    ]
    return problems


def find_links_file(citing: str) -> Path | None:
    candidates = [
        LINKS_DIR / f"{citing}_links.json",
        LINKS_DIR / f"{citing}.links.json",
        LINKS_DIR / f".{citing}links.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def target_title_from_path(path_2: str) -> str:
    """Return the actual target title named by a link entry."""
    name = path_2.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".txt") else name


def resolve_book(cur: sqlite3.Cursor, title: str) -> tuple[int, int] | None:
    """Resolve a JSON filename title, including the repo's Rashi spellings."""
    variants = [title]
    if title.startswith("רשי "):
        variants.append('רש"י ' + title[4:])
    if title.startswith("רשבם "):
        variants.append('רשב"ם ' + title[5:])
    for variant in variants:
        row = cur.execute(
            "SELECT id, orderIndex FROM book WHERE title=?", (variant,)
        ).fetchone()
        if row:
            return int(row[0]), int(row[1])
    return None


def is_base_book(cur: sqlite3.Cursor, book_id: int) -> bool:
    row = cur.execute("SELECT isBaseBook FROM book WHERE id=?", (book_id,)).fetchone()
    return bool(row and row[0])


def insert_pair(
    cur: sqlite3.Cursor, citing: str, target: str, next_id: int, type_ids: dict[str, int]
) -> tuple[int, int, int]:
    """Returns (next_id, inserted, skipped)."""
    icl._heading_cache.clear()  # keyed by book id; never reuse across DBs
    links_path = find_links_file(citing)
    if not links_path:
        print(f"  SKIP {citing}: no links file")
        return next_id, 0, 0

    data = json.loads(links_path.read_text(encoding="utf-8"))
    sfat = cur.execute(
        "SELECT id, title, totalLines, orderIndex, isBaseBook FROM book WHERE title=?",
        (citing,),
    ).fetchone()
    base = cur.execute(
        "SELECT id, title, totalLines, orderIndex FROM book WHERE title=?",
        (target,),
    ).fetchone()
    if not sfat or not base:
        print(f"  ERROR missing books citing={sfat} base={base}")
        return next_id, 0, 0

    sfat_id, _, sfat_lines, sfat_order, sfat_is_base = sfat
    base_id, _, base_lines, _ = base
    print(
        f"  {target} id={base_id} lines={base_lines} | "
        f"{citing} id={sfat_id} lines={sfat_lines} order={sfat_order} | "
        f"json={len(data)} ({links_path.name})"
    )

    sfat_map = {
        li: lid
        for li, lid in cur.execute(
            "SELECT lineIndex, id FROM line WHERE bookId=?", (sfat_id,)
        )
    }
    base_map = {
        li: lid
        for li, lid in cur.execute(
            "SELECT lineIndex, id FROM line WHERE bookId=?", (base_id,)
        )
    }
    # A file may mix Gemara commentary with super-commentary on Rashi/Tosafot.
    # path_2, rather than the pair's default base title, is the source of truth.
    target_maps: dict[str, tuple[int, dict[int, int]]] = {
        target: (base_id, base_map),
    }
    existing = {
        tuple(row)
        for row in cur.execute(
            "SELECT sourceLineId, targetLineId, connectionTypeId FROM link WHERE targetBookId=?",
            (sfat_id,),
        )
    }

    rows = []
    skipped = []
    seen = set()
    touched_book_ids = {base_id}
    for i, item in enumerate(data, start=1):
        # Generator.kt: (line_index - 1).coerceAtLeast(0)
        c_idx = max(int(item["line_index_1"]) - 1, 0)
        s_idx = max(int(item["line_index_2"]) - 1, 0)
        connection_type = item.get("Conection Type")
        stored = stored_type_for(connection_type)
        if stored is None or stored not in type_ids:
            # preflight_connection_types refuses these before anything is written;
            # reaching here means it was bypassed, so never drop the entry silently.
            raise ValueError(f"{links_path.name}[{i}]: unsupported Conection Type {connection_type!r}")
        connection_type_id = type_ids[stored]

        real_target = target_title_from_path(str(item["path_2"]))
        if real_target not in target_maps:
            resolved = resolve_book(cur, real_target)
            if not resolved:
                skipped.append((i, c_idx, s_idx, f"target book not found: {real_target}"))
                continue
            target_id, _ = resolved
            target_maps[real_target] = (
                target_id,
                {
                    li: lid
                    for li, lid in cur.execute(
                        "SELECT lineIndex, id FROM line WHERE bookId=?", (target_id,)
                    )
                },
            )
        source_book_id, source_map = target_maps[real_target]
        flip, generator_stored = icl.plan_storage(
            canonical_connection_type(connection_type), citing, bool(sfat_is_base),
            real_target, is_base_book(cur, source_book_id),
        )
        if not flip or generator_stored != stored:
            # This script only writes path_2 book -> citing book. The generator would
            # store this entry differently (as written, or as OTHER because the title
            # does not name the base), so writing it here would disagree with the build.
            raise ValueError(
                f"{links_path.name}[{i}]: the library generator stores {connection_type!r} -> "
                f"{real_target!r} as {generator_stored} {'flipped' if flip else 'as written'}; "
                f"this script can only write flipped dependent links. Use the otzaria-db-linker skill."
            )
        if c_idx not in sfat_map or s_idx not in source_map:
            skipped.append((i, c_idx, s_idx, "missing line"))
            continue
        source_line_id = source_map[s_idx]
        target_line_id = sfat_map[c_idx]
        if (source_line_id in icl.heading_line_ids(cur, source_book_id)
                or target_line_id in icl.heading_line_ids(cur, sfat_id)):
            skipped.append((i, c_idx, s_idx, "heading line (the generator skips these)"))
            continue
        key = (source_line_id, target_line_id, connection_type_id)
        if key in seen or key in existing:
            skipped.append((i, c_idx, s_idx, "duplicate"))
            continue
        seen.add(key)
        touched_book_ids.add(source_book_id)
        rows.append(
            (
                next_id,
                source_book_id,
                sfat_id,
                source_line_id,
                target_line_id,
                c_idx,
                int(sfat_order),
                connection_type_id,
            )
        )
        next_id += 1

    print(f"  to insert={len(rows)} skipped={len(skipped)}")
    if skipped[:3]:
        print(f"  skip sample={skipped[:3]}")

    if rows:
        cur.executemany(
            """
            INSERT INTO link (
                id, sourceBookId, targetBookId, sourceLineId, targetLineId,
                targetLineIndex, targetBookOrderIndex, connectionTypeId
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            rows,
        )

    # baseProvenance (isDeclaredBase before July 2026) keeps its DEFAULT 0, as the
    # generator leaves it. Flags: recomputed with the generator's own rules.
    icl.recompute_book_flags(cur, touched_book_ids | {sfat_id})

    dependent_ids = sorted({type_ids[t] for t in STORED_TYPE_FOR.values() if t in type_ids})
    verify = cur.execute(
        "SELECT COUNT(*) FROM link WHERE targetBookId=? AND connectionTypeId IN ("
        + ",".join("?" for _ in dependent_ids) + ")",
        (sfat_id, *dependent_ids),
    ).fetchone()[0]
    print(f"  VERIFY all dependent-text links to {citing}: {verify}")
    return next_id, len(rows), len(skipped)


def main() -> int:
    if not SEF_DB.exists():
        print("ERROR: seforim.db not found", SEF_DB)
        return 1

    try:
        probe = sqlite3.connect(str(SEF_DB), timeout=1)
        probe.execute("BEGIN IMMEDIATE")
        probe.rollback()
        type_ids = load_connection_type_ids(probe.cursor())
        probe.close()
    except sqlite3.OperationalError as e:
        print("ERROR: cannot write to seforim.db — close Otzaria completely and retry.")
        print(" detail:", e)
        return 2

    entries_by_file = {}
    for citing, _target in PAIRS:
        links_path = find_links_file(citing)
        if links_path:
            entries_by_file[links_path.name] = json.loads(links_path.read_text(encoding="utf-8"))
    problems = preflight_connection_types(entries_by_file, type_ids)
    if problems:
        print(f"ERROR: refusing to write — {len(problems)} problem(s) would drop links:")
        for problem in problems:
            print("  " + problem)
        return 3

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"seforim.db.bak_{stamp}"
    print(f"backing up to {backup} ...")
    shutil.copy2(SEF_DB, backup)
    print(f"backup size {backup.stat().st_size}")

    conn = sqlite3.connect(str(SEF_DB), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()

    next_id = (cur.execute("SELECT MAX(id) FROM link").fetchone()[0] or 0) + 1
    print(f"starting link id={next_id}")

    total_ins = total_skip = 0
    for citing, target in PAIRS:
        print(f"\n=== {citing} ===")
        next_id, ins, skip = insert_pair(cur, citing, target, next_id, type_ids)
        total_ins += ins
        total_skip += skip

    conn.commit()
    conn.close()
    print(f"\nDONE inserted={total_ins} skipped={total_skip}")
    print(f"backup kept at: {backup}")
    print("Restart Otzaria to see the commentators.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
