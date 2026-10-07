"""Write a converted Ben-Yehuda book with its footnotes in a companion notes book.

Ben-Yehuda keeps footnotes as a list at the end of the text. They become:
  * <book>.txt              - the reference stays in the text as a bare <sup>N</sup>
  * הערות על <book>.txt     - <h1> on line 1, then note N on line N+1 as "<sup>N</sup> text"
                              (the layout of the packaged Ben-Yehuda notes books)
  * links/<book>_links.json - "footnotes" links from the reference line to note N
This is the separate-file footnote mechanism of .claude/skills/otzaria-book-format.

Run on its own, it upgrades a book that ben_y.py converted in the old block format
(raw HTML block lines, footnote list as the last line):
    python -X utf8 split_footnotes.py "<old book>.txt" --out-dir <dir> --links-dir <links>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from otzaria_markup import convert_block_lines

NOTES_PREFIX = "הערות על "


def notes_book(stem: str, notes: list[str]) -> list[str]:
    return [f"<h1>{NOTES_PREFIX}{stem}</h1>"] + [f"<sup>{n}</sup> {body}" for n, body in enumerate(notes, start=1)]


def footnote_links(refs: list[tuple[int, int]], notes_name: str) -> list[dict]:
    return [
        {
            "line_index_1": line,
            "line_index_2": note + 1,  # line 1 of the notes book is its <h1>
            "heRef_2": "הערות",
            "path_2": notes_name,
            "Conection Type": "footnotes",
        }
        for line, note in refs
    ]


def write_book(book_path: Path, lines: list[str], notes: list[str],
               refs: list[tuple[int, int]], links_dir: Path) -> None:
    book_path.parent.mkdir(parents=True, exist_ok=True)
    book_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    if not notes:
        return
    missing = sorted(set(range(1, len(notes) + 1)) - {n for _, n in refs})
    if missing:
        print(f"{book_path.stem}: notes without a reference in the text: {missing}")
    notes_name = f"{NOTES_PREFIX}{book_path.stem}.txt"
    (book_path.parent / notes_name).write_text("\n".join(notes_book(book_path.stem, notes)), encoding="utf-8", newline="\n")
    links_dir.mkdir(parents=True, exist_ok=True)
    links_path = links_dir / f"{book_path.stem}_links.json"
    links_path.write_text(json.dumps(footnote_links(refs, notes_name), ensure_ascii=False, indent=2),
                          encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert an old-format Ben-Yehuda book and split its footnotes")
    ap.add_argument("book", type=Path, help="book converted by the old ben_y.py (block lines)")
    ap.add_argument("--out-dir", type=Path, help="output folder (default: next to the input)")
    ap.add_argument("--links-dir", type=Path, required=True, help="the source's links/ folder")
    args = ap.parse_args()
    old = args.book.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    lines, notes, refs = convert_block_lines(old)
    out = (args.out_dir or args.book.parent) / args.book.name
    write_book(out, lines, notes, refs, args.links_dir)
    print(f"{out}: {len(lines)} lines, {len(notes)} notes, {len(refs)} links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
