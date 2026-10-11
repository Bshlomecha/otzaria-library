#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db_search.py - חיפוש בקובץ seforim.db (ה-DB החי של אוצריא) לצורך "בדיקת קיום" של ספר לפני הוספה.

קריאה בלבד (sqlite עם mode=ro). דורש:  pip install zstandard   (רק לפקודות שקוראות טקסט: text, lines)

למה צריך את זה: שם הספר ב-DB הוא שם הקובץ, ולעיתים שונה משם הספר בוויקיטקסט (למשל טור ברקת נמצא כ-
"מקור חיים - ג (טור ברקת ...)"). ולכן חיפוש לפי שם לא מספיק - חייבים גם חיפוש טקסט מלא על שורות
(ספר תגין נראה "חלקי" לסוכן שבדק רק חלק מהערך; הוא נמצא כולו בתוך "אוצר מדרשים").

פקודות:
  find                         מחפש קובצי seforim.db במיקומים מקובלים (ProgramData, Documents, Downloads, HOME...)
  title  טקסט [טקסט ...]       חיפוש בשמות ספרים (בלי ניקוד/גרשיים/מקפים) -> מזהה, שם, קטגוריה, מקור, שורות
  text   ביטוי [ביטוי ...]     חיפוש טקסט מלא בכל שורות ה-DB (~7 מיליון שורות; כ-6-7 דקות. ראה --book-id/--title-filter לצמצום)
  lines  BOOK_ID FROM [TO]     הדפסת שורות (1-based, כמו מספרי השורות בקבצי הספר) של ספר
  tree   [טקסט]                עץ קטגוריות (אפשר לסנן לפי טקסט בנתיב) - כדי לבחור קטגוריה קיימת
  where  שם-ספר                הקטגוריה של ספר/ים לפי שם (קיצור ל-title)

דוגמאות:
  python -X utf8 db_search.py find
  python -X utf8 db_search.py --db /path/seforim.db title "תולדות תנאים" "טור ברקת" "סדר תנאים"
  python -X utf8 db_search.py --db /path/seforim.db text "רפואה למכה" --max-hits 5
  python -X utf8 db_search.py --db /path/seforim.db text "חיים ביד" --title-filter "שו\"ת" --max-hits 20
  python -X utf8 db_search.py --db /path/seforim.db tree "ספרות עזר"

מיקום ה-DB: --db, או משתנה הסביבה OTZARIA_DB, או גילוי אוטומטי (find). בחלונות ברירת המחדל באפליקציה היא
C:\\ProgramData\\otzaria\\books\\seforim.db; במחשב אחר - השתמש ב-find. התוכן ב-line_content דחוס zstd עם מילון
שנמצא בטבלה zstd_dict (השורה הראשונה); הכלי מטפל בזה לבד.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

QUOTES_RE = re.compile("[\"\u05f4\u201c\u201d\u201e'\u05f3\u2019\u2018`\u00b4]")
DASH_RE = re.compile("[\u05be\\-_\u2010-\u2015]")
TAG_RE = re.compile(r"<[^>]*>")


def norm(s: str) -> str:
    """נרמול להשוואה: בלי ניקוד/טעמים, גרשיים כולם נמחקים, מקפים -> רווח, רווחים מכווצים."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = DASH_RE.sub(" ", s)
    s = QUOTES_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def candidate_dirs() -> list[Path]:
    home = Path.home()
    out: list[Path] = []
    for env in ("ProgramData", "ProgramFiles", "LOCALAPPDATA", "APPDATA", "PUBLIC"):
        v = os.environ.get(env)
        if v:
            out.append(Path(v) / "otzaria")
            out.append(Path(v))
    out += [home / "Downloads", home / "Documents", home / "Desktop", home / "otzaria", home / ".otzaria",
            home / ".local" / "share" / "otzaria", home / ".local" / "share", home / "Library" / "Application Support",
            Path("/opt/otzaria"), Path("/usr/share/otzaria"), Path("/var/lib/otzaria")]
    return [d for d in out if d.exists()]


def find_dbs(max_depth: int = 5) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for base in candidate_dirs():
        base_depth = len(base.parts)
        for root, dirs, files in os.walk(base):
            rp = Path(root)
            if len(rp.parts) - base_depth >= max_depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "__pycache__", "Windows", "System32", "Temp", "tmp"}]
            if "seforim.db" in files:
                p = (rp / "seforim.db").resolve()
                if p not in seen:
                    seen.add(p)
                    found.append(p)
    return sorted(found, key=lambda x: -x.stat().st_size)  # ה-DB המלא (גיגות) קודם


def open_db(path: str | None) -> sqlite3.Connection:
    path = path or os.environ.get("OTZARIA_DB")
    if not path:
        cands = find_dbs()
        if not cands:
            raise SystemExit("לא נמצא seforim.db. העבר --db <נתיב> או הגדר OTZARIA_DB (ראה: db_search.py find)")
        path = str(cands[0])
        print(f"[DB: {path}]", file=sys.stderr)
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"הקובץ לא קיים: {p}")
    return sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True)


class Decoder:
    def __init__(self, con: sqlite3.Connection):
        try:
            import zstandard
        except ImportError:
            raise SystemExit("חסרה החבילה zstandard:  pip install zstandard")
        self.z = zstandard
        row = con.execute("select dict from zstd_dict limit 1").fetchone()
        self.dc = zstandard.ZstdDecompressor(dict_data=zstandard.ZstdCompressionDict(row[0])) if row else None
        self.plain = zstandard.ZstdDecompressor()

    def __call__(self, b) -> str:
        if b is None:
            return ""
        if isinstance(b, str):
            return b
        if self.dc is not None:
            try:
                return self.dc.decompress(b, max_output_size=50_000_000).decode("utf-8")
            except Exception:  # noqa: BLE001
                pass
        try:
            return self.plain.decompress(b, max_output_size=50_000_000).decode("utf-8")
        except Exception:  # noqa: BLE001
            try:
                return bytes(b).decode("utf-8")
            except Exception as e:  # noqa: BLE001
                return f"<ERR {e}>"


def category_paths(con: sqlite3.Connection) -> dict[int, str]:
    cats = {r[0]: (r[1], r[2]) for r in con.execute("select id,parentId,title from category")}
    cache: dict[int, str] = {}

    def path(cid: int) -> str:
        if cid in cache:
            return cache[cid]
        parts, c, guard = [], cid, 0
        while c and guard < 50:
            par, t = cats[c]
            parts.append(t)
            c = par
            guard += 1
        cache[cid] = "/".join(reversed(parts))
        return cache[cid]

    for cid in cats:
        path(cid)
    return cache


def book_rows(con: sqlite3.Connection):
    cats = category_paths(con)
    sql = ("select b.id, b.title, b.categoryId, s.name, b.totalLines from book b "
           "left join source s on s.id=b.sourceId order by b.title")
    for bid, title, cid, src, total in con.execute(sql):
        yield bid, title, cats.get(cid, "?"), src, total


def cmd_find(_a, _con=None):
    dbs = find_dbs()
    if not dbs:
        print("לא נמצא seforim.db במיקומים המקובלים. חפש ידנית (למשל: find / -name seforim.db) או בקש מהמשתמש את הנתיב.")
        return 1
    for p in dbs:
        print(f"{p}  ({p.stat().st_size / 1e6:.0f} MB)")
    return 0


def cmd_title(a, con):
    terms = [norm(t) for t in a.terms]
    n = 0
    for bid, title, cat, src, total in book_rows(con):
        nt = norm(title)
        if any(t in nt for t in terms):
            print(f"{bid}\t{title}\t| {cat}\t| {src}\t| {total} שורות")
            n += 1
    print(f"-- {n} ספרים", file=sys.stderr)
    return 0


def cmd_text(a, con):
    dec = Decoder(con)
    phrases = list(a.phrases)
    nphr = [norm(p) for p in phrases]
    books = {bid: (title, cat, src) for bid, title, cat, src, _ in book_rows(con)}
    if a.title_filter:
        tf = norm(a.title_filter)
        allowed = {b for b, (t, _, _) in books.items() if tf in norm(t)}
    elif a.book_id:
        allowed = set(a.book_id)
    else:
        allowed = None
    if allowed is not None:
        print(f"[מצומצם ל-{len(allowed)} ספרים]", file=sys.stderr)
    counts = [dict() for _ in phrases]
    shown = [dict() for _ in phrases]
    examples: list[list[str]] = [[] for _ in phrases]
    t0 = time.time()
    if allowed is not None:
        q = ("select l.bookId,l.lineIndex,lc.content from line l join line_content lc on lc.id=l.id "
             f"where l.bookId in ({','.join(str(int(x)) for x in allowed)})")
    else:
        q = "select l.bookId,l.lineIndex,lc.content from line l join line_content lc on lc.id=l.id"
    n = 0
    for bid, li, cb in con.execute(q):
        s = dec(cb)
        n += 1
        if a.loose:
            ls = norm(TAG_RE.sub(" ", s))
        for i, p in enumerate(phrases):
            hit = (nphr[i] in ls) if a.loose else (p in s)
            if hit:
                counts[i][bid] = counts[i].get(bid, 0) + 1
                if shown[i].get(bid, 0) < a.per_book:
                    shown[i][bid] = shown[i].get(bid, 0) + 1
                    snippet = TAG_RE.sub("", s)
                    k = snippet.find(p) if p in snippet else 0
                    snippet = snippet[max(0, k - 60): k + a.snippet].replace("\n", " ")
                    examples[i].append(f"  ספר {bid} {books[bid][0]} | {books[bid][1]} | שורה {li + 1}: {snippet}")
        if n % 1_000_000 == 0:
            print(f"[נסרקו {n:,} שורות, {time.time() - t0:.0f}s]", file=sys.stderr)
    for i, p in enumerate(phrases):
        tot = sum(counts[i].values())
        print(f"=== '{p}': {tot} מופעים ב-{len(counts[i])} ספרים")
        for bid, k in sorted(counts[i].items(), key=lambda kv: -kv[1])[: a.max_books]:
            t, cat, src = books[bid]
            print(f"  ספר {bid}\t{t}\t| {cat}\t| {src}\tx{k}")
        if a.max_hits:
            for ln in examples[i][: a.max_hits]:
                print(ln)
    print(f"-- נסרקו {n:,} שורות ב-{time.time() - t0:.0f}s", file=sys.stderr)
    return 0


def cmd_lines(a, con):
    dec = Decoder(con)
    to = a.to if a.to is not None else a.frm
    row = con.execute("select b.title from book b where b.id=?", (a.book_id,)).fetchone()
    print(f"# ספר {a.book_id}: {row[0] if row else '?'}")
    for li, cb in con.execute("select l.lineIndex, lc.content from line l join line_content lc on lc.id=l.id "
                              "where l.bookId=? and l.lineIndex between ? and ? order by l.lineIndex",
                              (a.book_id, a.frm - 1, to - 1)):
        print(f"[{li + 1}] {dec(cb)}")
    return 0


def cmd_tree(a, con):
    paths = sorted(set(category_paths(con).values()))
    f = norm(a.filter) if a.filter else None
    for p in paths:
        if f is None or f in norm(p):
            print(p)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="נתיב ל-seforim.db (או OTZARIA_DB)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("find")
    p = sub.add_parser("title")
    p.add_argument("terms", nargs="+")
    p = sub.add_parser("where")
    p.add_argument("terms", nargs="+")
    p = sub.add_parser("text")
    p.add_argument("phrases", nargs="+")
    p.add_argument("--max-books", type=int, default=15, help="כמה ספרים להציג לכל ביטוי")
    p.add_argument("--max-hits", type=int, default=0, help="כמה קטעי דוגמה להדפיס לכל ביטוי (0 = בלי)")
    p.add_argument("--per-book", type=int, default=2, help="דוגמאות לכל היותר מכל ספר")
    p.add_argument("--snippet", type=int, default=160, help="אורך קטע הדוגמה")
    p.add_argument("--title-filter", help="לסרוק רק ספרים ששמם מכיל טקסט זה")
    p.add_argument("--book-id", type=int, action="append", help="לסרוק רק ספר זה (חוזר)")
    p.add_argument("--loose", action="store_true", help="השוואה מנורמלת (בלי תגיות/ניקוד/גרשיים) - איטי יותר")
    p = sub.add_parser("lines")
    p.add_argument("book_id", type=int)
    p.add_argument("frm", type=int)
    p.add_argument("to", type=int, nargs="?")
    p = sub.add_parser("tree")
    p.add_argument("filter", nargs="?")
    a = ap.parse_args()
    if a.cmd == "find":
        return cmd_find(a)
    con = open_db(a.db)
    fn = {"title": cmd_title, "where": cmd_title, "text": cmd_text, "lines": cmd_lines, "tree": cmd_tree}[a.cmd]
    return fn(a, con)


if __name__ == "__main__":
    sys.exit(main())
