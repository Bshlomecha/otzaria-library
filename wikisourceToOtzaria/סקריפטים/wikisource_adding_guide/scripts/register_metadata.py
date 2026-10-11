#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""register_metadata.py - רישום ספרים חדשים בשלושת המרשמים (פורמט מדויק, LF) מתוך קובץ רשומות JSON אחד.

המרשמים (ADDING_BOOKS.md סעיף 5 - פורמט אחר משכתב כל שורה בקובץ ונכשל ב-CI):
  1. metadata.json (שורש)            - שורה דחוסה אחת לספר, הוספה בסוף המערך. מזין את טבלת המחברים.
  2. ForDB/book_info.csv              - (bookName, authorName, generationName, subGenerationName, startYear, endYear)
                                         דרך make_metadata.py --book-info-csv (שמוסיף זהויות חסרות בלבד, וממיין).
  3. ForDB/sefaria_metadata_changes.csv - תיאור קצר/ארוך (הדרך היחידה של תיאור להגיע ל-DB).
  (ForDB/all_metadata.json: אופציונלי - רק 6 ספרי wikiSource רשומים שם; הכלי אינו נוגע בו.)

למה כלי ולא make_metadata.py ישירות: (א) book_info_writer דוחה CR (CRLF) - בחלונות עם core.autocrlf=true הקבצים בעץ
העבודה הם CRLF, ולכן הכלי עובד על עותקי LF זמניים וכותב בסוף חזרה רק אם --write; (ב) round-trip: הכלי מוודא
ש-metadata.json הקיים משוחזר בית-בבית מהקידוד הדחוס לפני שמוסיפים; (ג) קטגוריה נגזרת מהמיקום האמיתי של קובץ
הספר בעץ, ולא מהקלט; (ד) בדיקות התנגשות שם (כותרת קיימת באחד המרשמים) לפני כל כתיבה.

פורמט קובץ הרשומות (מערך; כל אובייקט = ספר בסיס אחד; ספר "הערות על X" אינו נרשם):
  {"fileName": "שם הקובץ בלי .txt", "author": "מחבר כפי שנהוג ב-metadata.json" | null,
   "generationName": "ראשונים|אחרונים|חז\\"ל|מחברי זמננו|תורה שבכתב|", "subGenerationName": "", "startYear": "", "endYear": "",
   "heShortDesc": "משפט אחד", "heDesc": "(אופציונלי) תיאור ארוך", "pubDate": "ה' תרמח" | null, "pubPlace": "ברלין" | null,
   "title": "(מידע בלבד)", "notes": "(מידע בלבד)", "partial": false}
  דוגמאות: examples/meta_samples/*.json. אל תמציא מחבר/שנים/דור - מה שלא ידוע נשאר ריק.
  pubDate: צורת הכתיבה הנפוצה ב-metadata.json היא "ה' <אותיות>" (למשל "ה' תרמח") או null.
  מחבר: author.name הוא מפתח ייחודי - חפש קודם את הצורות הקיימות ב-metadata.json (check_exists.py) והשתמש בהן.

שימוש:
    python -X utf8 register_metadata.py --records meta.json            # בדיקה בלבד (dry-run) + דוח שורות שיתווספו
    python -X utf8 register_metadata.py --records meta.json --write    # כתיבה לריפו (LF)
אחרי --write: הרץ run_validators.py, ובדוק git diff (רק שורות שנוספו, בלי שינוי בשאר הקובץ).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BOOK_ROOT = Path("wikisourceToOtzaria") / "ספרים" / "אוצריא"
NIQQUD = re.compile(r"[֑-ׇ]")
ILLEGAL = re.compile('[\\\\/:*"״?<>|]')


def sanitize_filename(name: str) -> str:
    s = NIQQUD.sub("", name)
    s = ILLEGAL.sub("", s)
    return s.replace("_", " ").replace("''", "").replace("'", "").strip()


def find_repo(start: Path) -> Path:
    for p in [start.resolve(), *start.resolve().parents]:
        if (p / "manual_links_packaging.py").exists() and (p / "metadata.json").exists():
            return p
    raise SystemExit("לא נמצא שורש הריפו. העבר --repo")


def lf_bytes(p: Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


def encode_metadata(meta: list) -> str:
    return "[\n" + ",\n".join(json.dumps(m, ensure_ascii=False, separators=(",", ":")) for m in meta) + "\n]\n"


def find_book_file(repo: Path, stem: str) -> Path:
    base = repo / BOOK_ROOT
    hits = [p for p in base.rglob(stem + ".txt")]
    if len(hits) != 1:
        raise SystemExit(f"'{stem}.txt': נמצאו {len(hits)} קבצים תחת {BOOK_ROOT} (נדרש בדיוק אחד): {hits}")
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", required=True, help="קובץ JSON עם מערך רשומות")
    ap.add_argument("--repo")
    ap.add_argument("--write", action="store_true", help="לכתוב לריפו (ברירת מחדל: dry-run)")
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    repo = Path(a.repo).resolve() if a.repo else find_repo(Path(__file__).parent)
    mm = repo / ".claude" / "skills" / "otzaria-book-format" / "scripts" / "make_metadata.py"
    if not mm.exists():
        raise SystemExit(f"לא נמצא {mm}")
    raw_json = Path(a.records).read_text(encoding="utf-8")
    try:
        records = json.loads(raw_json)
    except json.JSONDecodeError:
        # קבצים שנכתבו עם נתיבי Windows (\\) - מנסה לשמר לוכסן הפוך לא חוקי
        records = json.loads(re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", raw_json))
    if not isinstance(records, list) or not records:
        raise SystemExit("הקובץ חייב להיות מערך לא ריק של רשומות")

    tmp = Path(tempfile.mkdtemp(prefix="register-meta-"))
    try:
        (tmp / "ForDB").mkdir()
        for rel in ("ForDB/book_info.csv", "ForDB/sefaria_metadata_changes.csv", "metadata.json"):
            (tmp / rel).write_bytes(lf_bytes(repo / rel))
        original = {rel: (tmp / rel).read_bytes() for rel in ("ForDB/book_info.csv", "ForDB/sefaria_metadata_changes.csv",
                                                              "metadata.json")}
        meta_raw = original["metadata.json"].decode("utf-8")
        meta = json.loads(meta_raw)
        if encode_metadata(meta) != meta_raw:
            raise SystemExit("metadata.json הקיים לא משוחזר בית-בבית מקידוד דחוס (separators=(',',':')) - לא נוגעים. "
                             "בדוק אם הקובץ השתנה ידנית או אם יש בו CR בתוך מחרוזת.")
        titles = {m["title"].strip() for m in meta}
        bi_rows = list(csv.reader(io.StringIO(original["ForDB/book_info.csv"].decode("utf-8"), newline="")))
        bi_titles = {r[0] for r in bi_rows[1:]}
        desc_rows = list(csv.reader(io.StringIO(original["ForDB/sefaria_metadata_changes.csv"].decode("utf-8"), newline="")))
        desc_titles = {r[1] for r in desc_rows[1:] if len(r) > 1}
        new_meta = []
        for rec in records:
            stem = rec.get("fileName") or sanitize_filename(rec["title"])
            if stem != sanitize_filename(stem):
                raise SystemExit(f"fileName '{stem}' אינו שם קובץ מנוקה (צפוי: '{sanitize_filename(stem)}')")
            book = find_book_file(repo, stem)
            cat = book.parent.relative_to(repo / BOOK_ROOT).as_posix()
            clash = [n for n, s in (("metadata.json", titles), ("book_info.csv", bi_titles), ("sefaria_metadata_changes.csv", desc_titles))
                     if stem in s]
            if clash:
                raise SystemExit(f"'{stem}' כבר רשום ב: {', '.join(clash)} - זו התנגשות שם (בחר שם מבדיל או הסר את הרישום הישן)")
            author = rec.get("author")
            cmd = [a.python, "-X", "utf8", str(mm), "--title", stem, "--category-path", cat,
                   "--desc-csv", str(tmp / "ForDB" / "sefaria_metadata_changes.csv"),
                   "--book-info-csv", str(tmp / "ForDB" / "book_info.csv")]
            if author:
                cmd += ["--author", author]
            if rec.get("heShortDesc"):
                cmd += ["--he-short-desc", rec["heShortDesc"]]
            if rec.get("heDesc"):
                cmd += ["--he-desc", rec["heDesc"]]
            for key, flag in (("generationName", "--generation"), ("subGenerationName", "--sub-generation"),
                              ("startYear", "--start-year"), ("endYear", "--end-year")):
                if rec.get(key):
                    cmd += [flag, str(rec[key])]
            r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
            print(f"{stem}: make_metadata rc={r.returncode} {(r.stdout or '').strip().splitlines()[:1]} {r.stderr.strip()[:200]}")
            if r.returncode:
                return 1
            new_meta.append({"title": stem, "author": author, "pubDate": rec.get("pubDate"), "pubPlace": rec.get("pubPlace"),
                             "compPlace": None, "compDate": None, "תיאור_חדש": None, "heShortDesc": None, "heDesc": None,
                             "Unnamed: 9": None, "order": None})
        (tmp / "metadata.json").write_text(encode_metadata(meta + new_meta), encoding="utf-8", newline="\n")

        # דוח שינויים
        for rel in ("ForDB/book_info.csv", "ForDB/sefaria_metadata_changes.csv", "metadata.json"):
            new = (tmp / rel).read_bytes()
            old = original[rel]
            ol, nl = old.decode("utf-8").split("\n"), new.decode("utf-8").split("\n")
            added = [x for x in nl if x not in set(ol)]
            removed = [x for x in ol if x not in set(nl)]
            if rel == "metadata.json" and removed and removed == [r for r in removed if r + "," in nl]:
                # השורה האחרונה במערך קיבלה פסיק בסוף כי נוספו אחריה שורות - שינוי תקין, לא "הסרה"
                added = [x for x in added if x.rstrip(",") not in removed]
                removed = []
            has_cr = bytes([13]) in new
            print(f"\n== {rel}: שורות {len(ol)} -> {len(nl)} | נוספו {len(added)} | הוסרו {len(removed)} | CR בחדש: {has_cr}")
            for x in added:
                print("  +", x[:230])
            for x in removed:
                print("  -", x[:230], "   <-- לא צפוי! בדוק")
            if removed:
                print("  (שורות הוסרו: זה לא אמור לקרות בהוספת ספרים בלבד; לא כותבים)")
                return 1
        if a.write:
            for rel in ("ForDB/book_info.csv", "ForDB/sefaria_metadata_changes.csv", "metadata.json"):
                (repo / rel).write_bytes((tmp / rel).read_bytes())
            print("\nנכתב לריפו (LF). הרץ run_validators.py ובדוק git diff.")
        else:
            print("\n[dry-run] לא נכתב דבר. הוסף --write כדי לכתוב.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
