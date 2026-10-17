#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""וביום השבת (תורת אמת) -> אוצריא: הספר, «הערות על וביום השבת» וקובץ הקישורים.

הקלט הוא קובץ המקור המלא של תורת אמת (410_beyom_hashabat.txt, אותו תוכן כמו
book-sources, בקידוד UTF-8). השורה הראשונה בו היא שורת פרמטרים, ובה כללי התצוגה של
הספר עצמו (CosmeticsType). הכללים של הספר הזה:

    [[[ ... ]]] {{ ... }}   סימן הערה + הערה מתקפלת   -> <sup>X</sup> בספר, והערה ב"הערות על"
    [[ ... ]]               מודגש                      -> <b>
    {{{ ... }}}             כותרת גדולה                -> <big><b>
    BB ... EE               בלוק מוזח (blockquote)     -> כל שורה בו ב-<blockquote>
    XX ... GG               מסגרת                      -> הסימונים נמחקים
    JJ -> *      AMP -> (נמחק)      RRR -> (שורת רווח, נמחקת)

הסקריפט מוודא שהכללים בשורה הראשונה הם אלה שהוא מניח, ונעצר אם הם שונים.

הערות: כל הערה נכתבת בספר ההערות כשהיא פותחת בסימן שלה (<sup>X</sup> ...), כך
ש-HearotCompanionMerge ב-SeforimLibrary מזריק אותה במקום הסימן בספר. בלי הסימן המוביל
כל ההערות נדבקות בסוף השורה. הסקריפט מדמה את אלגוריתם המיזוג ונכשל אם הערה כלשהי לא
נקלטת במקומה, או אם אחד מתנאי המיזוג האחרים (SeforimLibrary, Generator.kt) נפגע.

תיקונים ידניים שהמקור עצמו דורש (טעויות של המקור) נמצאים ב-
ToratEmetToOtzaria/post_convert_fixes.tsv ומוחלים כאן דרך post_convert_fixes.py.

שימוש (מתיקיית הסקריפט, או משם אחר):
    python3 manipulate.py              # כותב את הספר, ההערות והקישורים למקומם במאגר
    python3 manipulate.py --check      # לא כותב; נכשל אם הקבצים שבמאגר שונים ממה שההמרה מייצרת
    python3 manipulate.py --out-dir D  # כותב לתיקייה D במקום למאגר
"""

from __future__ import annotations

import argparse
import base64
import collections
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_DIR = HERE.parent.parent          # ToratEmetToOtzaria
REPO_ROOT = SOURCE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
import post_convert_fixes  # noqa: E402

BOOK_TITLE = "וביום השבת"
NOTES_TITLE = f"הערות על {BOOK_TITLE}"
# שורה 2 בספר = שם המחבר כפי שב-metadata.json (בלי תואר-סיומת), ר' ADDING_BOOKS.md
AUTHOR_LINE = "הרב ישראל מאיר ווייל"

DEFAULT_INPUT = HERE / "410_beyom_hashabat.txt"
DEFAULT_PICS = HERE / "Pics"
BOOKS_DIR = SOURCE_DIR / "ספרים" / "אוצריא" / "הלכה" / "מחברי זמננו"
LINKS_DIR = SOURCE_DIR / "links"

# כללי המקור שהסקריפט מניח (שורה 1 של הקובץ); ר' המסמך שלמעלה.
EXPECTED_RULES = (
    "#rep=[[[=<small><sup>(^^]]]=)</sup></small>",
    "#rep2=[[=<b>^^]]=</b>",
    "{{{=<big", "}}}=_nbsp;</center></b></big>",
    "#rep6=RRR=_nbsp;",
    "#rep7=BB=<blockquote>^^EE=</blockquote>",
    "#rep9=XX=", "GG=</div>",
    "#rep12={{=<small>", "#rep13=}}=</small>",
    "#rep14=JJ=*", "#rep15=AMP=_nbsp;",
)

# שורות מקור שאינן טקסט: הוראות של התוכנה המקורית
DIRECTIVE_RE = re.compile(r"^\s*(\*\*INDEX_WRITE=|@PicWidth|@ExpandColapseScript)")
IMG_LINE_RE = re.compile(r'^<div align=center><img [^>]*src="\.\./Pics/([^"]+)"[^>]*></div>$')
HEADING_TAGS = {"$": "h1", "@": "h2", "~": "h3"}

MARK_OPEN_RE = re.compile(r"\[\[\[([^\]\[]+?)\]\]\]\s*\{\{|\[\[(\*)\]\]\s*\{\{")
BRACE_RE = re.compile(r"\{\{|\}\}")
BIG_LINE_RE = re.compile(r"^\{\{\{(.*?)\}\}\}\s*$")
BOLD_RE = re.compile(r"\[\[(?!\[)(.*?)\]\]")
PLACEHOLDER_RE = re.compile(r"￰(\d+)￱")
LATIN_TOKEN_RE = re.compile(r"(?<![A-Za-z])(?:RRR|AMP|JJ|BB|EE|XX|GG)(?![a-z])")


class ConversionError(Exception):
    pass


@dataclass(frozen=True)
class Note:
    marker: str
    body: str
    base_line: int    # 1-based, בספר
    note_line: int    # 1-based, בקובץ ההערות


# ---------------------------------------------------------------- ניקוי גולמי

def collapse_spaces(text: str) -> str:
    return re.sub(r"[ \t ]{2,}", " ", text).strip()


def strip_source_tokens(text: str) -> str:
    """JJ -> *, AMP/RRR נמחקים (כללי הספר)."""
    return text.replace("AMP", "").replace("RRR", "").replace("JJ", "*")


def inline_markup(text: str) -> str:
    """עיצוב בתוך שורה אחת: [[...]] מודגש, <BR> אחיד. סגירה יתומה ']]' נמחקת."""
    text = re.sub(r"<\s*BR\s*/?\s*>", "<br>", text, flags=re.I)
    text = BOLD_RE.sub(lambda m: f"<b>{m.group(1).strip()}</b>" if m.group(1).strip() else "", text)
    return text.replace("]]", "")


def clean_note_body(raw_body: str) -> str:
    paragraphs = []
    for para in raw_body.replace("{{", "").replace("}}", "").split("\n"):
        para = collapse_spaces(inline_markup(strip_source_tokens(para)))
        para = re.sub(r"</?\s*(?:i|h[1-6])\b[^>]*>", "", para, flags=re.I)
        if para:
            paragraphs.append(para)
    return "<br>".join(paragraphs)


# ----------------------------------------------------------------- הערות

def extract_notes(text: str) -> tuple[str, list[tuple[str, str]]]:
    """מחליף כל [[[X]]] {{...}} בסמן-מקום; מחזיר את הטקסט ואת (סימן, גוף) לפי הסדר.
    ההערה נסגרת בסוגר המתאים (כולל {{ }} מקוננים, שנמחקים)."""
    out, notes, pos = [], [], 0
    while True:
        m = MARK_OPEN_RE.search(text, pos)
        if not m:
            break
        depth, end = 1, None
        for b in BRACE_RE.finditer(text, m.end()):
            depth += 1 if b.group(0) == "{{" else -1
            if depth == 0:
                end = b
                break
        if end is None:
            raise ConversionError(f"הערה שלא נסגרת, תחילתה: {text[m.start():m.start() + 60]!r}")
        marker = (m.group(1) or m.group(2)).strip()
        out.append(text[pos:m.start()])
        out.append(f"￰{len(notes)}￱")
        notes.append((marker, text[m.end():end.start()]))
        pos = end.end()
    out.append(text[pos:])
    return "".join(out), notes


# ---------------------------------------------------------------- תמונות

def image_line(pics_dir: Path, name: str) -> str:
    path = pics_dir / name
    if not path.is_file():
        raise ConversionError(f"חסרה תמונה: {path}")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/jpeg;base64,{data}" style="max-width: 100%;"/>'


# ------------------------------------------------------------------- המרה

def convert(raw: str, pics_dir: Path):
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    header, _, body = raw.partition("\n")
    if not header.startswith("&"):
        raise ConversionError("שורה 1 אינה שורת פרמטרים של תורת אמת")
    for rule in EXPECTED_RULES:
        if rule not in header:
            raise ConversionError(f"כלל תצוגה צפוי חסר בשורה 1: {rule}")

    # חזית הספר: $ שם / כותרת-משנה / מחבר / "בן הגאון ... - שנה" -> h1 + שורת מחבר.
    lines = [l for l in body.split("\n")]
    first_h2 = next(i for i, l in enumerate(lines) if l.startswith("@ ") and "ExpandColapse" not in l)
    front = [l.strip() for l in lines[:first_h2] if l.strip() and not DIRECTIVE_RE.match(l)]
    if len(front) != 4 or front[0] != f"$ {BOOK_TITLE}" or not front[2].startswith(f"<big><big>{AUTHOR_LINE} שליט"):
        raise ConversionError(f"חזית הספר אינה כצפוי: {front!r}")
    lines = lines[first_h2:]

    text = "\n".join(l for l in lines if not DIRECTIVE_RE.match(l))
    text = BIG_TITLE(text)
    text, raw_notes = extract_notes(text)
    if "{{" in text or "}}" in text or "[[[" in text or "]]]" in text:
        raise ConversionError("נשארו סימוני הערה/כותרת גדולה שלא נקלטו")

    subtitle = re.sub(r"</?big>", "", front[1]).strip()
    out: list[str] = [f"<h1>{BOOK_TITLE} - {subtitle}</h1>", AUTHOR_LINE]
    in_quote = False
    pending_table: list[str] | None = None
    for line in text.split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue
        img = IMG_LINE_RE.match(line.strip())
        if img:
            out.append(image_line(pics_dir, img.group(1)))
            continue
        if line.strip() == "<hr>":
            continue
        # כותרות
        sigil = line.lstrip()[:1]
        if sigil in HEADING_TAGS:
            tag = HEADING_TAGS[sigil]
            content = collapse_spaces(inline_markup(strip_source_tokens(line.lstrip()[1:])))
            if content:
                out.append(f"<{tag}>{content}</{tag}>")
            continue
        if sigil in "#^!" and sigil:
            raise ConversionError(f"סימן רמה לא צפוי: {line[:40]!r}")
        # בלוק מוזח: BB ... EE
        ends = False
        if line.lstrip().startswith("BB"):
            line = line.lstrip()[2:]
            if in_quote:
                raise ConversionError("BB בתוך BB")
            in_quote = True
        if "EE" in line:
            if not in_quote:
                raise ConversionError("EE בלי BB")
            line, ends = line.replace("EE", ""), True
        line = line.replace("XX", "").replace("GG", "")
        content = collapse_spaces(inline_markup(strip_source_tokens(line)))
        if content:
            if in_quote:
                content = f"<blockquote>{content}</blockquote>"
            out.append(content)
        if ends:
            in_quote = False
    if in_quote:
        raise ConversionError("BB שלא נסגר")

    # טבלה שנפרסה על כמה שורות -> שורה אחת (מבנה מרובה-חלקים)
    joined: list[str] = []
    for l in out:
        if pending_table is not None:
            pending_table.append(l)
            if "</table>" in l:
                joined.append("".join(pending_table))
                pending_table = None
            continue
        if "<table" in l and "</table>" not in l:
            pending_table = [l]
            continue
        joined.append(l)
    if pending_table is not None:
        raise ConversionError("טבלה שלא נסגרת")
    out = joined

    # סמני-מקום -> <sup>X</sup>, ורישום ההערות לפי שורת הבסיס
    notes: list[Note] = []
    final: list[str] = []
    for line in out:
        def put(m):
            marker, body = raw_notes[int(m.group(1))]
            notes.append(Note(marker, clean_note_body(body), len(final) + 1, len(notes) + 1))
            return f"<sup>{html.escape(marker)}</sup>"
        line = collapse_spaces(PLACEHOLDER_RE.sub(put, line))
        final.append(line)
    if len(notes) != len(raw_notes):
        raise ConversionError("לא כל ההערות הוצבו בספר")
    return final, notes


def BIG_TITLE(text: str) -> str:
    """{{{כותרת}}} בשורה משלה -> <big><b>...</b></big> (כללי הספר: גדול + מודגש)."""
    out = []
    for line in text.split("\n"):
        m = BIG_LINE_RE.match(line.strip())
        out.append(f"<big><b>{strip_source_tokens(m.group(1)).strip()}</b></big>" if m else line)
    return "\n".join(out)


# --------------------------------------------------- אימות מול חוזה המיזוג

def simulate_merge(main_lines: list[str], note_bodies: list[str], links: list[dict]) -> None:
    """HearotCompanionMerge.kt (SeforimLibrary): כל הערה חייבת להיקלט במקום הסימן."""
    by_line = collections.defaultdict(list)
    for l in links:
        by_line[l["line_index_1"] - 1].append(l["line_index_2"] - 1)
    note_sup = re.compile(r"^﻿?<sup(?:\s[^>]*)?>([^<]+)</sup>\s*")
    for li, idxs in by_line.items():
        line, consumed = main_lines[li], []
        for ni in idxs:
            note = note_bodies[ni]
            if "<i>" in note or "<i " in note or "</i>" in note or not note.strip():
                raise ConversionError(f"הערה {ni + 1}: <i> או ריקה")
            m = note_sup.match(note)
            if not m:
                raise ConversionError(f"הערה {ni + 1} בלי סימן מוביל")
            esc = re.escape(m.group(1))
            hits = [r.span() for r in re.finditer(f"<sup>{esc}</sup>", line)]
            hits = [r for r in hits if all(not (a < r[1] and r[0] < b) for a, b in consumed)]
            if not hits:
                raise ConversionError(f"הערה {ni + 1}: הסימן {m.group(1)!r} לא נמצא בשורה {li + 1}")
            consumed.append(min(hits))


def validate(main_lines: list[str], note_bodies: list[str], links: list[dict]) -> None:
    errors = []
    if not re.fullmatch(r"<h1>.+</h1>", main_lines[0]):
        errors.append("שורה 1 אינה <h1>")
    for i, line in enumerate(main_lines, 1):
        if not line.strip():
            errors.append(f"שורה {i}: ריקה")
        if line != line.strip() or "  " in re.sub(r"data:[^\"]+", "", line):
            errors.append(f"שורה {i}: רווחים מיותרים")
        if re.search(r"\[\[|\]\]|\{\{|\}\}", line) or LATIN_TOKEN_RE.search(re.sub(r"<[^>]+>|data:[^\"]+", "", line)):
            errors.append(f"שורה {i}: נשאר סימון מקור")
        m = re.fullmatch(r"<h([1-6])>(.*)</h\1>", line)
        if m and not re.sub(r"<[^>]+>", "", m.group(2)).strip():
            errors.append(f"שורה {i}: כותרת ריקה")
        if "src=\"../" in line:
            errors.append(f"שורה {i}: תמונה בלי data URI")
    for i, note in enumerate(note_bodies, 1):
        if re.search(r"\[\[|\]\]|\{\{|\}\}", note) or LATIN_TOKEN_RE.search(note) or "  " in note or note != note.strip():
            errors.append(f"הערה {i}: סימון מקור או רווחים מיותרים")
    sup_per_line = collections.Counter()
    for i, line in enumerate(main_lines, 1):
        n = len(re.findall(r"<sup>[^<]*</sup>", line))
        if n:
            sup_per_line[i] = n
            if re.match(r"<h[1-6]>", line):
                errors.append(f"שורה {i}: סימן הערה בכותרת")
    link_per_line = collections.Counter(l["line_index_1"] for l in links)
    if sup_per_line != link_per_line:
        errors.append("מספר הסמנים בשורה שונה ממספר הקישורים אליה")
    if [l["line_index_2"] for l in links] != list(range(1, len(note_bodies) + 1)):
        errors.append("line_index_2 אינו רצף 1..N")
    if errors:
        raise ConversionError("\n".join(errors[:40]) + (f"\n... ועוד {len(errors) - 40}" if len(errors) > 40 else ""))
    simulate_merge(main_lines, note_bodies, links)


# ---------------------------------------------------------------- כתיבה

def build(input_path: Path, pics_dir: Path):
    final, notes = convert(input_path.read_text(encoding="utf-8"), pics_dir)
    main_text = post_convert_fixes.apply_book(str(SOURCE_DIR), BOOK_TITLE, "\n".join(final))
    note_lines = [f"<sup>{html.escape(n.marker)}</sup> {n.body}" for n in notes]
    notes_text = post_convert_fixes.apply_book(str(SOURCE_DIR), NOTES_TITLE, "\n".join(note_lines))
    main_lines, note_bodies = main_text.split("\n"), notes_text.split("\n")
    if len(main_lines) != len(final) or len(note_bodies) != len(notes):
        raise ConversionError("post_convert_fixes שינה את מספר השורות")
    links = [{"line_index_1": n.base_line, "heRef_2": "הערות", "path_2": f"{NOTES_TITLE}.txt",
              "line_index_2": n.note_line, "Conection Type": "footnotes"} for n in notes]
    validate(main_lines, note_bodies, links)
    return (main_text + "\n", notes_text + "\n",
            json.dumps(links, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--pics-dir", type=Path, default=DEFAULT_PICS)
    ap.add_argument("--out-dir", type=Path, help="כותב ל-D/{ספר,הערות,קישורים} במקום למאגר")
    ap.add_argument("--check", action="store_true", help="לא כותב; נכשל אם הקבצים שבמאגר שונים")
    args = ap.parse_args()
    try:
        main_text, notes_text, links_text = build(args.input, args.pics_dir)
    except (ConversionError, post_convert_fixes.PostConvertFixError) as e:
        print(f"נכשל: {e}", file=sys.stderr)
        return 1
    if args.out_dir:
        targets = {args.out_dir / f"{BOOK_TITLE}.txt": main_text, args.out_dir / f"{NOTES_TITLE}.txt": notes_text,
                   args.out_dir / f"{BOOK_TITLE}_links.json": links_text}
    else:
        targets = {BOOKS_DIR / f"{BOOK_TITLE}.txt": main_text, BOOKS_DIR / f"{NOTES_TITLE}.txt": notes_text,
                   LINKS_DIR / f"{BOOK_TITLE}_links.json": links_text}
    status = 0
    for path, text in targets.items():
        if args.check:
            same = path.is_file() and path.read_bytes() == text.encode("utf-8")
            print(("תואם: " if same else "שונה: ") + str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path))
            status |= 0 if same else 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    if not args.check:
        main_n, notes_n = main_text.count("\n"), notes_text.count("\n")
        print(f"נכתב: ספר {main_n:,} שורות, הערות {notes_n:,}, קישורים {notes_n:,}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
