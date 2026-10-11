#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_exists.py - בדיקת קיום של ספר בריפו otzaria-library (שמות קבצים + המרשמים), לפני שמוסיפים אותו.

מחפש כל מונח (אחרי נרמול: בלי ניקוד, בלי גרשיים/מרכאות, מקפים -> רווח):
  1. בנתיבי כל הקבצים בריפו (git ls-files + קבצים שלא במעקב). כל נתיב מסומן:
        [נארז]  = תחת אחד משורשי BOOK_ROOTS (manual_links_packaging.py) - ייכנס לספרייה
        [לא-נארז] = extraBooks/, docxToOtzaria/, MoreBooks/ספרים/<לא אוצריא>, לא רלוונטי, בהמתנה וכו'
     חשוב: עותקים מקבילים באותו שם קיימים כמעט תמיד, ורובם לא נארזים. רק [נארז] נחשב "קיים בספרייה".
  2. במרשמים: metadata.json, ForDB/book_info.csv, ForDB/all_metadata.json, ForDB/sefaria_metadata_changes.csv,
     ForDB/book_moves.csv, ForDB/book_renames.csv, SourcesBooks.csv, all_metadata.json.

מה הכלי אינו עושה: לא מחפש בתוכן הספרים. לשם כך (ספרי ספריא נוצרים בזמן הבנייה ואינם בריפו בכלל!) השתמש ב-
db_search.py מול seforim.db החי - שם גם חיפוש טקסט מלא. שני הבדיקות נדרשות.

שימוש:
    python -X utf8 check_exists.py "תולדות תנאים" "טור ברקת" [--repo <שורש הריפו>] [--no-registries] [--all-paths]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REGISTRIES = ["metadata.json", "ForDB/book_info.csv", "ForDB/all_metadata.json", "ForDB/sefaria_metadata_changes.csv",
              "ForDB/book_moves.csv", "ForDB/book_renames.csv", "SourcesBooks.csv", "all_metadata.json"]
QUOTES = re.compile("[\"״“”„'׳’‘`´]")
DASH = re.compile("[־\\-_‐-―]")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = DASH.sub(" ", s)
    s = QUOTES.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def find_repo(start: Path) -> Path:
    for p in [start.resolve(), *start.resolve().parents]:
        if (p / "manual_links_packaging.py").exists() and (p / "metadata.json").exists():
            return p
    raise SystemExit("לא נמצא שורש הריפו (manual_links_packaging.py + metadata.json). העבר --repo")


def book_roots(repo: Path) -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location("_mlp", repo / "manual_links_packaging.py")
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return tuple(mod.BOOK_ROOTS)


def list_files(repo: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard"], cwd=repo, capture_output=True, check=True).stdout
        return [x for x in out.decode("utf-8").split("\0") if x]
    except Exception:  # noqa: BLE001
        files = []
        for root, dirs, fs in os.walk(repo):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in fs:
                files.append(os.path.relpath(os.path.join(root, f), repo).replace(os.sep, "/"))
        return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--repo")
    ap.add_argument("--no-registries", action="store_true")
    ap.add_argument("--all-paths", action="store_true", help="גם נתיבים של קבצי links/ו-.json (ברירת מחדל: רק ספרים .txt/.pdf/.docx)")
    ap.add_argument("--max", type=int, default=60, help="מקסימום תוצאות לכל מונח לכל חלק")
    a = ap.parse_args()
    repo = Path(a.repo).resolve() if a.repo else find_repo(Path(__file__).parent)
    roots = book_roots(repo)
    files = list_files(repo)
    nfiles = [(f, norm(f)) for f in files if a.all_paths or f.lower().endswith((".txt", ".pdf", ".docx"))]
    print(f"# ריפו: {repo}  ({len(files):,} קבצים)")
    for term in a.terms:
        nt = norm(term)
        print(f"\n===== '{term}' (מנורמל: '{nt}') =====")
        hits = [f for f, nf in nfiles if nt in nf]
        packed = [f for f in hits if any(f.startswith(r + "/") for r in roots)]
        print(f"-- נתיבים: {len(hits)} (מתוכם נארזים: {len(packed)})")
        for f in sorted(hits, key=lambda x: (x not in packed, x))[: a.max]:
            print(f"  [{'נארז' if f in packed else 'לא-נארז'}] {f}")
        if len(hits) > a.max:
            print(f"  ... ועוד {len(hits) - a.max}")
        if not a.no_registries:
            for reg in REGISTRIES:
                p = repo / reg
                if not p.exists():
                    continue
                n = 0
                lines = []
                with p.open(encoding="utf-8", errors="replace", newline="") as fh:
                    for i, line in enumerate(fh, 1):
                        if nt in norm(line):
                            n += 1
                            if len(lines) < 6:
                                lines.append(f"    L{i}: {line.strip()[:220]}")
                if n:
                    print(f"-- {reg}: {n} שורות")
                    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
