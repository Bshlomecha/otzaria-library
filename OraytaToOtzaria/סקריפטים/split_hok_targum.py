"""מפריד מילים מחוברות בתרגום של "חק לישראל" (אוריתא) לפי מקור תורת אמת.

בתורת אמת מילים בתרגום מופרדות ב-<j> (בכותרת: רווח רחב) ולא ברווח, ואוריתא
השמיטה אותו - כך נוצרו מילים מחוברות כמו "שְׁמַיָּאוְיָת". הסקריפט אוסף מכל כרך
את רצפי המילים המופרדים ב-<j>, ומוסיף רווח בכל מילה בספר שאותיותיה שוות
לחיבור של רצף כזה. רק רווחים נוספים; שורות ושאר התווים לא משתנים.

חיבור שהוא בעצמו מילה אמיתית במקורות תורת אמת (למשל שתי מילים שמחוברות
נותנות מילה קיימת) מדולג ומדווח, כי אין לדעת אם לפצל אותו.

הרצה (מתיקיית השורש של המאגר):
    python OraytaToOtzaria/סקריפטים/split_hok_targum.py          # מתקן
    python OraytaToOtzaria/סקריפטים/split_hok_targum.py --check  # רק מדווח
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TE_DIR = ROOT / "ToratEmetToOtzaria/סקריפטים/books/תורה/חק לישראל"
BOOK_DIR = ROOT / "OraytaToOtzaria/ספרים/אוצריא/לימוד יומי/חק לישראל"
VOLUMES = ("בראשית", "שמות", "ויקרא", "במדבר", "דברים")

LETTERS = "א-ת"
# ניקוד וטעמים בלבד - בלי מקף (05BE), פסק (05C0) וסוף פסוק (05C3), שמפרידים מילים.
MARKS = "֑-ׇֽֿׁׂׅׄ"
PRESENTATION = "יִ-ﭏ"
WORD = re.compile(f"[{LETTERS}{MARKS}{PRESENTATION}]+")
J_CHAIN = re.compile(f"[{LETTERS}{MARKS}]+(?:<j>[{LETTERS}{MARKS}]+)+")
COMMENT = re.compile(r"<!--.*?-->", re.S)


def skel(word: str) -> str:
    """האותיות בלבד, בלי ניקוד וטעמים."""
    return re.sub(f"[^{LETTERS}]", "", unicodedata.normalize("NFKD", word))


def read_te(path: Path) -> str:
    return COMMENT.sub("", path.read_bytes().decode("cp1255"))


def te_sources(volume: str, te_dir: Path = TE_DIR) -> list[Path]:
    return sorted(p for p in (te_dir / volume).glob("y_hok??.txt"))


def joined_parts(te_texts: list[str]) -> dict[str, tuple[str, ...]]:
    """חיבור-אותיות -> המילים שמרכיבות אותו, לכל תת-רצף רציף של שרשרת <j>."""
    parts: dict[str, tuple[str, ...]] = {}
    for text in te_texts:
        for m in J_CHAIN.finditer(text):
            words = [skel(w) for w in m.group().split("<j>")]
            for i in range(len(words)):
                for k in range(i + 2, len(words) + 1):
                    parts.setdefault("".join(words[i:k]), tuple(words[i:k]))
    return parts


def real_words(te_texts: list[str]) -> set[str]:
    """המילים במקורות תורת אמת כשה-<j> מתפרש כרווח."""
    found: set[str] = set()
    for text in te_texts:
        found.update(skel(w) for w in WORD.findall(text.replace("<j>", " ")))
    return found


def split_word(word: str, lengths: tuple[int, ...]) -> str:
    """מכניס רווח אחרי כל קבוצת אותיות לפי lengths, כשהניקוד נשאר על האות שלו."""
    cuts = set()
    total = 0
    for n in lengths[:-1]:
        total += n
        cuts.add(total)
    out = []
    letters = 0
    for ch in word:
        if skel(ch):
            if letters in cuts:
                out.append(" ")
            letters += 1
        out.append(ch)
    return "".join(out)


class Splitter:
    def __init__(self, parts: dict[str, tuple[str, ...]], real: set[str]):
        self.parts = {k: v for k, v in parts.items() if k not in real}
        self.ambiguous = {k: v for k, v in parts.items() if k in real}
        self.added = 0
        self.skipped: collections.Counter[tuple[str, ...]] = collections.Counter()

    def _replace(self, m: re.Match) -> str:
        word = m.group()
        key = skel(word)
        if key in self.parts:
            pieces = self.parts[key]
            self.added += len(pieces) - 1
            return split_word(word, tuple(len(p) for p in pieces))
        if key in self.ambiguous:
            self.skipped[self.ambiguous[key]] += 1
        return word

    def line(self, line: str) -> str:
        return WORD.sub(self._replace, line)


def splitter_for(volume: str, te_dir: Path = TE_DIR) -> Splitter:
    texts = [read_te(p) for p in te_sources(volume, te_dir)]
    if not texts:
        raise FileNotFoundError(f"אין מקור תורת אמת עבור {volume} ב-{te_dir}")
    all_texts = [read_te(p) for v in VOLUMES for p in te_sources(v, te_dir)]
    return Splitter(joined_parts(texts), real_words(all_texts))


def same_but_spaces(old: str, new: str) -> bool:
    return old.count("\n") == new.count("\n") and old.replace(" ", "") == new.replace(" ", "")


def process(path: Path, splitter: Splitter, write: bool) -> None:
    old = path.read_text(encoding="utf-8")
    new = "\n".join(splitter.line(line) for line in old.split("\n"))
    if not same_but_spaces(old, new):
        raise AssertionError(f"{path}: שינוי שאינו הוספת רווחים")
    if write and new != old:
        path.write_text(new, encoding="utf-8", newline="")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="לא לכתוב, רק לדווח")
    ap.add_argument("--te-dir", type=Path, default=TE_DIR)
    ap.add_argument("files", nargs="*", type=Path,
                    help="קבצים לתיקון (ברירת מחדל: חמשת כרכי אוריתא); שם הכרך נלקח מסוף שם הקובץ")
    args = ap.parse_args(argv)
    files = args.files or [BOOK_DIR / f"חק לישראל - {v}.txt" for v in VOLUMES]
    for path in files:
        volume = next((v for v in VOLUMES if path.stem.endswith(v) or path.parent.name == v), None)
        if volume is None:
            raise SystemExit(f"{path}: לא זוהה כרך")
        sp = splitter_for(volume, args.te_dir)
        process(path, sp, write=not args.check)
        print(f"{path.name}: נוספו {sp.added} רווחים, דולגו {sum(sp.skipped.values())} "
              f"מופעים של {len(sp.skipped)} חיבורים דו-משמעיים")
        for pieces, n in sorted(sp.skipped.items()):
            print(f"  דולג: {' '.join(pieces)} ({n})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
