#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_validators.py - מריץ את כל הוולידטורים של הריפו על ספרים חדשים (לפני קומיט) בצעד אחד, כולל "טריק ה-index הזמני".

מה הוא מריץ (כל שלב מדווח PASS / FAIL / SKIP, ובסוף סיכום):
  1. validate_book.py על כל קובץ ספר ששונה/חדש תחת wikisourceToOtzaria/ספרים/אוצריא (כולל "הערות על ...").
  2. validate_sidecars.py לכל זוג ספר + הערות + _links.json ששונה/חדש תחת wikisourceToOtzaria/links.
  3. בניית קומיט זמני (git commit-tree) מה-index הזמני: HEAD + הקבצים ששונו. אינו נוגע ב-index האמיתי, לא בענף
     ולא בעץ העבודה (נוצרים רק אובייקטים "יתומים" שנאספים בהמשך על ידי git gc).
  4. validate_fordb_book_names.py (SEFARIA_FETCH=0) פעמיים: על HEAD (קו בסיס) ועל הקומיט הזמני (--tree). הוולידטור
     קורא את רשימת הקבצים הנארזים מ-git ולא מעץ העבודה, ולכן בלי הטריק כל הכותרים החדשים ידווחו "לא נמצא".
     קיימות שגיאות "לא נמצא" ישנות (מאות; בעיקר ספרי ספריא) - מה שחשוב: אין שגיאות חדשות והמספר לא גדל.
  5. validate_manual_links_refs.py --base HEAD ב-index זמני עם git add -N (הוא משתמש ב-git diff ואינו רואה untracked).
  5ב. check_duplicates.py של הריפו: שמות הקבצים החדשים (ספרים וקבצי links) אינם כפולים בין שורשים נארזים.
  6. recompute_lineage.py (בדיקה בלבד): האם manual_links_lineage.json תואם לקבצי ה-links ו-config (LF).
  7. (עם --tests) בדיקות היחידה: test_manual_links_packaging, test_source_lists_contract, test_validate_fordb_book_names,
     test_library_tree. ב-Windows 4 בדיקות נכשלות בגלל CRLF (test_book_info_writer, test_fordb_book_renames) - לא קשור.

אילו קבצים נחשבים "ששונו": הפלט של git status (כולל untracked) תחת: wikisourceToOtzaria/, ForDB/, metadata.json,
all_metadata.json, manual_links_lineage.json, manual_links_sync.json. אפשר לצמצם/להרחיב עם --paths.
הכלי לא מריץ git add/commit/stash/checkout על ה-index/העץ האמיתיים.

שימוש:
    python -X utf8 run_validators.py [--repo <שורש>] [--paths P1 P2 ...] [--tests] [--no-fordb] [--keep]
קוד יציאה: 0 אם כל השלבים שרצו עברו, אחרת 1.
דרישות: python 3.12+, git, וחבילות openpyxl/tqdm ל-test_library_tree אם משתמשים ב---tests (ראה TOOLS.md).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BOOK_ROOT = "wikisourceToOtzaria/ספרים/אוצריא/"
LINKS_ROOT = "wikisourceToOtzaria/links/"
DEFAULT_PATHS = ["wikisourceToOtzaria/", "ForDB/", "metadata.json", "all_metadata.json",
                 "manual_links_lineage.json", "manual_links_sync.json"]
RESULTS: list[tuple[str, str, str]] = []


def find_repo(start: Path) -> Path:
    for p in [start.resolve(), *start.resolve().parents]:
        if (p / "manual_links_packaging.py").exists() and (p / ".github" / "scripts").is_dir():
            return p
    raise SystemExit("לא נמצא שורש הריפו. העבר --repo")


def run(cmd: list[str], cwd: Path, env: dict | None = None, check: bool = False) -> subprocess.CompletedProcess:
    e = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True)
    r.out = r.stdout.decode("utf-8", "replace")  # type: ignore[attr-defined]
    r.err = r.stderr.decode("utf-8", "replace")  # type: ignore[attr-defined]
    if check and r.returncode:
        raise SystemExit(f"נכשל: {' '.join(cmd)}\n{r.err}")
    return r


def record(name: str, status: str, detail: str = "") -> None:
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))


def changed_files(repo: Path, prefixes: list[str]) -> list[str]:
    r = run(["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z", "-uall"], repo, check=True)
    out = r.stdout.decode("utf-8").split("\0")
    files: list[str] = []
    i = 0
    while i < len(out):
        ent = out[i]
        i += 1
        if len(ent) < 4:
            continue
        xy, path = ent[:2], ent[3:]
        if xy[0] in "RC":  # rename/copy: הערך הבא הוא המקור
            i += 1
        if (repo / path).is_file() and any(path == p or path.startswith(p) for p in prefixes):
            files.append(path)
    return sorted(set(files))


def show(text: str, limit: int = 25) -> None:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    for ln in lines[:limit]:
        print("    " + ln[:300])
    if len(lines) > limit:
        print(f"    ... (+{len(lines) - limit} שורות)")


def count_not_found(text: str) -> int:
    m = re.search(r"נמצאו (\d+) שמות ספרים", text)
    return int(m.group(1)) if m else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo")
    ap.add_argument("--paths", nargs="+", help="קידומות נתיב להכללה בקומיט הזמני (ברירת מחדל: ראה למעלה)")
    ap.add_argument("--tests", action="store_true", help="גם להריץ את בדיקות היחידה של הריפו")
    ap.add_argument("--no-fordb", action="store_true", help="לדלג על validate_fordb_book_names (איטי יחסית)")
    ap.add_argument("--keep", action="store_true", help="לא למחוק את ה-index הזמני")
    a = ap.parse_args()
    repo = Path(a.repo).resolve() if a.repo else find_repo(Path(__file__).parent)
    py = sys.executable
    skill = repo / ".claude" / "skills" / "otzaria-book-format" / "scripts"
    changed = changed_files(repo, a.paths or DEFAULT_PATHS)
    books = [c for c in changed if c.startswith(BOOK_ROOT) and c.endswith(".txt")]
    links = [c for c in changed if c.startswith(LINKS_ROOT) and c.endswith("_links.json")]
    print(f"# ריפו: {repo}\n# קבצים ששונו/חדשים: {len(changed)} (ספרים: {len(books)}, links: {len(links)})")
    for c in changed:
        print("   ", c)

    # 1. validate_book
    for b in books:
        r = run([py, "-X", "utf8", "-I", str(skill / "validate_book.py"), b], repo)
        ok = r.returncode == 0
        record(f"validate_book {Path(b).name}", "PASS" if ok else "FAIL")
        if not ok or "אזהר" in r.out or "warn" in r.out.lower():
            show(r.out + r.err, 12)

    # 2. validate_sidecars
    for l in links:
        stem = Path(l).name[: -len("_links.json")]
        base = next((b for b in books if Path(b).name == stem + ".txt"), None)
        notes = next((b for b in books if Path(b).name == f"הערות על {stem}.txt"), None)
        if base is None:
            record(f"validate_sidecars {Path(l).name}", "SKIP", "קובץ הספר לא נמצא בין הקבצים ששונו")
            continue
        cmd = [py, "-X", "utf8", "-I", str(skill / "validate_sidecars.py"), "--links", l, "--book", base]
        if notes:
            cmd += ["--target", notes]
        r = run(cmd, repo)
        record(f"validate_sidecars {Path(l).name}", "PASS" if r.returncode == 0 else "FAIL")
        if r.returncode:
            show(r.out + r.err)

    # 3. קומיט זמני מ-index זמני
    tmpdir = Path(tempfile.mkdtemp(prefix="validators-idx-"))
    idx = tmpdir / "index"
    env = {"GIT_INDEX_FILE": str(idx)}
    temp_commit = None
    try:
        run(["git", "read-tree", "HEAD"], repo, env, check=True)
        if changed:
            r = run(["git", "add", "-f", "--", *changed], repo, env)
            if r.returncode:
                record("git add (index זמני)", "FAIL", r.err.strip()[:200])
        tree = run(["git", "write-tree"], repo, env, check=True).out.strip()
        temp_commit = run(["git", "commit-tree", tree, "-p", "HEAD", "-m", "tmp-validators"], repo, env, check=True).out.strip()
        record("קומיט זמני", "PASS", temp_commit[:12])

        # 4. validate_fordb_book_names
        if a.no_fordb:
            record("validate_fordb_book_names", "SKIP", "--no-fordb")
        else:
            script = repo / ".github" / "scripts" / "validate_fordb_book_names.py"
            e = {"SEFARIA_FETCH": "0"}
            base_r = run([py, "-X", "utf8", str(script)], repo, e)
            new_r = run([py, "-X", "utf8", str(script), "--tree", temp_commit], repo, e)
            nb, na = count_not_found(base_r.out + base_r.err), count_not_found(new_r.out + new_r.err)
            crashed = [n for n, rr in (("HEAD", base_r), ("קומיט זמני", new_r)) if "Traceback" in rr.err]
            if crashed:
                record("validate_fordb_book_names", "FAIL", "הוולידטור קרס (" + ", ".join(crashed) + ") - חסר קובץ בעץ?")
                show(base_r.err if "Traceback" in base_r.err else new_r.err, 12)
            elif "unrecognized arguments: --tree" in new_r.err:
                record("validate_fordb_book_names", "SKIP", "הגרסה בריפו אינה תומכת ב---tree (ראה ADDING_BOOKS §7: sed על ls-tree)")
            else:
                mine = []
                for b in books:
                    stem = Path(b).stem
                    mine += [ln.strip() for ln in (new_r.out + new_r.err).splitlines() if stem in ln]
                status = "PASS" if (na <= nb and not mine) else "FAIL"
                record("validate_fordb_book_names", status, f"שגיאות 'לא נמצא': לפני={nb}, אחרי={na}")
                if status == "FAIL":
                    show("\n".join(mine) or (new_r.out + new_r.err), 30)
                elif new_r.returncode and nb == na:
                    print("    (קוד יציאה לא-0 נובע מהשגיאות הקיימות מראש - לא חדשות)")

        # 5. validate_manual_links_refs
        if links:
            run(["git", "add", "-N", "--", *links], repo, env)
            r = run([py, "-X", "utf8", str(repo / ".github" / "scripts" / "validate_manual_links_refs.py"),
                     "--base", "HEAD"], repo, env)
            record("validate_manual_links_refs --base HEAD", "PASS" if r.returncode == 0 else "FAIL")
            show(r.out + r.err, 12)
        else:
            record("validate_manual_links_refs", "SKIP", "אין קבצי links ששונו")
    finally:
        if not a.keep:
            for f in tmpdir.glob("*"):
                f.unlink(missing_ok=True)
            tmpdir.rmdir()

    # 5ב. כפילויות שם קובץ בין שורשי הספרים הנארזים (ו-links): check_duplicates.py של הריפו. שמות הספרים/הקישורים החדשים לא אמורים להופיע
    dup = repo / "check_duplicates.py"
    if dup.exists() and (books or links):
        r = run([py, "-X", "utf8", str(dup)], repo)
        mine = [ln.strip() for ln in (r.out + r.err).splitlines() if any(Path(f).name in ln for f in (books + links))]
        record("check_duplicates (שם קובץ כפול בין שורשים)", "PASS" if not mine else "FAIL")
        if mine:
            show("\n".join(mine), 20)

    # 6. lineage
    r = run([py, "-X", "utf8", str(Path(__file__).parent / "recompute_lineage.py"), "--repo", str(repo)], repo)
    record("lineage (recompute_lineage.py)", "PASS" if r.returncode == 0 else "FAIL",
           "" if r.returncode == 0 else "הרץ recompute_lineage.py --write")
    if r.returncode:
        show(r.out + r.err, 12)

    # 7. בדיקות יחידה
    if a.tests:
        for cwd, mod in [(repo, "test_manual_links_packaging"), (repo, "test_source_lists_contract"),
                         (repo / ".github" / "scripts", "test_validate_fordb_book_names"),
                         (repo / ".github" / "scripts", "test_library_tree")]:
            r = run([py, "-X", "utf8", "-m", "unittest", mod], cwd)
            tail = (r.out + r.err).strip().splitlines()[-3:]
            record(f"unittest {mod}", "PASS" if r.returncode == 0 else "FAIL", " | ".join(tail)[:160])

    fails = [x for x in RESULTS if x[1] == "FAIL"]
    print(f"\n== סיכום: {sum(1 for x in RESULTS if x[1] == 'PASS')} עברו, {len(fails)} נכשלו, "
          f"{sum(1 for x in RESULTS if x[1] == 'SKIP')} דולגו ==")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
