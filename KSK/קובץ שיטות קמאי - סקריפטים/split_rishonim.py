#!/usr/bin/env python3
"""Split single-rishon books out of the Kovetz Shitot Kamai tractates.

Each KSK tractate is laid out as:

    line 1   <h1>title</h1>
    line 2   author line
    line 3   copyright notice (small gray print)
    <h2>amud</h2>                 (daf X. / daf X:)
    <h3>rishon label</h3>         (the source of the passage that follows)
    passage paragraphs ...

A book in split_rishonim_config.json names one source tractate and the h3
labels that belong to it. Every passage under a matching label is copied, in
source order, under the <h2> of its amud; everything else is dropped. This is
the same rule as the old split scripts (split_2.py/split_3.py) that produced
these books from the pre-2026 edition, with two fixes: text before the first
<h3> (the author and copyright lines) is never copied, and labels are compared after
normalization, so spelling variants of a label are still found.

Label modes:
    primary   copy the passage text only
    sublabel  copy the label itself as a plain line, then the passage
              (used for a second work of the same author inside the book)

Output book:
    line 1   <h1>title</h1>      (title = file name)
    line 2   author
    line 3   copyright notice    (copyright_line.COPYRIGHT_LINE, as in the tractates)
    then <h2> + passages, per amud that has at least one matching passage.

Usage (from anywhere; all paths in the config are repo-relative):
    split_rishonim.py                 write the books
    split_rishonim.py --check         only compare with the files on disk
    split_rishonim.py --report        print match statistics, label variants
                                      and excluded near-miss labels
    split_rishonim.py --linemap FILE  also write a JSON line map (see README)
    --mask                            replace Hebrew letters by '*' in output
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from copyright_line import COPYRIGHT_LINE  # noqa: E402

REPO = HERE.parents[1]
CONFIG = HERE / "split_rishonim_config.json"

H2 = re.compile(r"<h2>(.*)</h2>")
H3 = re.compile(r"<h3>(.*)</h3>")

# niqqud and cantillation, but not maqaf (U+05BE), which separates words
MARKS = re.compile("[֑-ֽֿ-ׇ]")
QUOTES = re.compile("[\"'׳״‘’“”`]")
DASHES = re.compile("[־‐-―\\-]")
MATRES = re.compile("[וי]")  # vav, yod
HEBREW = re.compile("[֐-׿]+")


def normalize_label(s: str) -> str:
    s = MARKS.sub("", s)
    s = QUOTES.sub("", s)
    s = DASHES.sub(" ", s)
    return " ".join(s.split())


def loose_label(s: str) -> str:
    """normalize_label without vav/yod: equal keys = spelling variants."""
    return MATRES.sub("", normalize_label(s)).replace(" ", "")


def load_config() -> list[dict]:
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)["books"]


def split_book(book: dict) -> tuple[list[str], list[list], dict]:
    src = REPO / book["source"]
    lines = src.read_text(encoding="utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    exact = {normalize_label(x["label"]): x["mode"] for x in book["labels"]}
    loose = {loose_label(x["label"]): x["mode"] for x in book["labels"]}

    out = [f"<h1>{book['title']}</h1>", book["author"], COPYRIGHT_LINE]
    lmap: list[list] = []
    stats = {
        "matched": collections.Counter(),   # label -> passages copied
        "variants": collections.Counter(),  # label matched only loosely
        "near_miss": collections.Counter(), # similar label, not copied
        "passages": 0,
    }
    h2_line = h2_no = None
    h2_written = True
    inside = False
    for no, line in enumerate(lines[1:], start=2):
        m2 = H2.fullmatch(line)
        if m2:
            h2_line, h2_no, h2_written = line, no, False
            continue  # a passage may continue across amudim, as before
        m3 = H3.fullmatch(line)
        if m3:
            label = m3.group(1).strip()
            mode = exact.get(normalize_label(label))
            if mode is None:
                mode = loose.get(loose_label(label))
                if mode is not None:
                    stats["variants"][label] += 1
            inside = mode is not None
            if inside:
                stats["matched"][label] += 1
                stats["passages"] += 1
                if mode == "sublabel":
                    _emit_h2(out, lmap, src, h2_line, h2_no, h2_written)
                    h2_written = True
                    out.append(label)
                    lmap.append([len(out), src.name, no, "heading"])
            else:
                key = loose_label(label)
                if any(len(k) >= 4 and len(key) >= 4 and (k in key or key in k)
                       for k in loose):
                    stats["near_miss"][label] += 1
            continue
        if inside:
            if not h2_written:
                _emit_h2(out, lmap, src, h2_line, h2_no, h2_written)
                h2_written = True
            out.append(line)
            lmap.append([len(out), src.name, no, "content"])
    return out, lmap, stats


def _emit_h2(out, lmap, src, h2_line, h2_no, written):
    if written or h2_line is None:
        return
    out.append(h2_line)
    lmap.append([len(out), src.name, h2_no, "heading"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--linemap", type=Path)
    ap.add_argument("--mask", action="store_true")
    args = ap.parse_args()

    def show(s: str) -> str:
        return HEBREW.sub("*", s) if args.mask else s

    linemap = {}
    differ = 0
    for book in load_config():
        out, lmap, stats = split_book(book)
        text = "\n".join(out) + "\n"
        dest = REPO / book["output"]
        if args.check:
            same = dest.is_file() and dest.read_text(encoding="utf-8") == text
            differ += not same
            print(f"{'ok  ' if same else 'DIFF'} {show(book['output'])}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        linemap[book["title"]] = {
            "output": book["output"],
            "source": book["source"],
            "lines": lmap,
        }
        if args.report:
            print(f"== {show(book['title'])}: {stats['passages']} passages, "
                  f"{len(out)} lines")
            for lab, n in stats["matched"].most_common():
                print(f"   matched   {n:5d}  {show(lab)}")
            for lab, n in stats["variants"].most_common():
                print(f"   variant   {n:5d}  {show(lab)}")
            for lab, n in stats["near_miss"].most_common():
                print(f"   excluded  {n:5d}  {show(lab)}")
    if args.linemap:
        with open(args.linemap, "w", encoding="utf-8") as f:
            json.dump(linemap, f, ensure_ascii=False)
            f.write("\n")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
