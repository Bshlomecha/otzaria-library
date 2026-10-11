#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recompute_lineage.py - חישוב מחדש של שלושת שדות ה-sha256 ב-manual_links_lineage.json, תמיד לפי LF.

למה צריך: כל הוספה/שינוי של קובץ ב-wikisourceToOtzaria/links (או שינוי של manual_links_sync.json) משנה את
source_links_tree_sha256 ו-packaged_links_tree_sha256 (ואם הקונפיג השתנה - גם config_sha256). אם ה-lineage לא
מעודכן, `manual_links_packaging.py package` נופל בבניית השחרור (lineage mismatch) והספרייה לא נארזת.

המלכודת: במחשב עם core.autocrlf=true (חלונות) קבצי העבודה הם CRLF, ו-`manual_links_packaging.py check` על עץ העבודה
נותן hashes שונים מאלה ש-CI (לינוקס, LF) מחשב. לכן הכלי הזה לא מחשב על עץ העבודה כמות שהוא: הוא בונה עותק זמני
(LF בלבד) של manual_links_sync.json + שורשי ה-links, מריץ עליו את הפונקציות של manual_links_packaging.py עצמו,
ומעדכן את ה-lineage ב-canonical_bytes(lineage)+b"\\n" (בדיוק כמו ש-validate_lineage דורש).

מצבים:
  (ברירת מחדל)   קורא את עץ העבודה של הריפו (מנרמל CRLF->LF), מחשב, ומדווח האם ה-lineage שבדיסק תואם. לא כותב.
                 קוד יציאה 0 = תואם, 1 = לא תואם (ומדפיס את הערכים הנכונים).
  --write         כותב את ה-lineage המעודכן לריפו (רק שלושת השדות; שאר הקובץ נשאר) ואז מאמת בעותק הזמני עם
                  `python -I manual_links_packaging.py check --require-lineage`.
  --ref REF       במקום עץ העבודה - קורא הכול מאובייקטי git של REF (קומיט). לאימות/דיבוג של קומיט קיים; לא כותב.

דוגמאות:
    python -X utf8 recompute_lineage.py                 # בדיקה: האם ה-lineage שבעץ העבודה נכון?
    python -X utf8 recompute_lineage.py --write         # עדכון אחרי הוספת קבצי links
    python -X utf8 recompute_lineage.py --ref HEAD      # האם ה-lineage שבקומיט HEAD נכון?

הערות: (1) הכלי אינו מריץ git add/commit. (2) קבצי links שנוספו חייבים להיות שטוחים (בלי תתי-תיקיות) ובלי התנגשות שם
בין שורשים - manual_links_packaging.py ידחה אחרת. (3) אחרי --write, הקובץ נכתב עם LF; git ב-Windows עשוי להזהיר
"LF will be replaced by CRLF" - זה תקין. (4) מצב ברירת המחדל מדפיס גם אילו קבצי links נוספו/השתנו/נמחקו ביחס ל-HEAD.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG = "manual_links_sync.json"
LINEAGE = "manual_links_lineage.json"
PACKAGING = "manual_links_packaging.py"
TOOLCHAIN = "packaging_toolchain.json"
FIELDS = ("config_sha256", "source_links_tree_sha256", "packaged_links_tree_sha256")


def find_repo(start: Path) -> Path:
    for p in [start.resolve(), *start.resolve().parents]:
        if (p / PACKAGING).exists() and (p / CONFIG).exists():
            return p
    raise SystemExit(f"לא נמצא שורש הריפו ({PACKAGING} + {CONFIG}). העבר --repo")


def git(repo: Path, *args: str, check: bool = True) -> bytes:
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=repo, capture_output=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)} נכשל: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("manual_links_packaging_ws", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class BlobReader:
    """git cat-file --batch: תהליך git אחד לכל הקריאות (אחרת מאות הרצות מאטות מאוד ב-Windows)."""

    def __init__(self, repo: Path):
        self.p = subprocess.Popen(["git", "-c", "core.quotepath=false", "cat-file", "--batch"], cwd=repo,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, spec: str) -> bytes | None:
        assert self.p.stdin and self.p.stdout
        self.p.stdin.write(spec.encode("utf-8") + bytes([10]))
        self.p.stdin.flush()
        header = self.p.stdout.readline().decode("utf-8", "replace").rstrip(chr(10))
        if header.endswith(" missing") or header.endswith(" ambiguous"):
            return None
        _sha, kind, size = header.rsplit(" ", 2)
        data = self.p.stdout.read(int(size))
        self.p.stdout.read(1)  # LF שאחרי התוכן
        return data if kind == "blob" else None

    def close(self) -> None:
        if self.p.stdin:
            self.p.stdin.close()
        self.p.wait()


class Source:
    """מקור הקבצים: עץ העבודה (מנורמל LF) או אובייקטי git של REF."""

    def __init__(self, repo: Path, ref: str | None):
        self.repo, self.ref = repo, ref
        self.batch = BlobReader(repo) if ref else None

    def read(self, rel: str) -> bytes | None:
        if self.batch:
            return self.batch.read(f"{self.ref}:{rel}")
        p = self.repo / rel
        return lf(p.read_bytes()) if p.is_file() else None

    def tree_files(self, root: str) -> list[str] | None:
        """כל הקבצים (רקורסיבית, יחסית לשורש הריפו) תחת root; None אם ה-root לא קיים."""
        if self.ref:
            out = git(self.repo, "ls-tree", "-r", "-z", "--name-only", self.ref, "--", root, check=False)
            names = [x for x in out.decode("utf-8").split("\0") if x]
            return names or None
        base = self.repo / root
        if not base.exists():
            return None
        res = []
        for dp, _dn, fn in os.walk(base):
            for f in fn:
                res.append(os.path.relpath(os.path.join(dp, f), self.repo).replace(os.sep, "/"))
        return sorted(res)


def materialize(src: Source, tmp: Path) -> dict:
    """בונה בתוך tmp עותק של הקונפיג, כלי האריזה, ה-lineage ושורשי ה-links (LF). מחזיר את הקונפיג."""
    for name in (CONFIG, PACKAGING, LINEAGE, TOOLCHAIN):
        data = src.read(name)
        if data is None:
            if name in (CONFIG, PACKAGING):
                raise SystemExit(f"{name} לא נמצא ב-{src.ref or 'עץ העבודה'}")
            continue
        (tmp / name).write_bytes(data)
    config = json.loads((tmp / CONFIG).read_text(encoding="utf-8"))
    for entry in config["links_roots"]:
        root = entry["path"]
        names = src.tree_files(root)
        if names is None:
            continue  # לא קיים: המודול יטפל (present חסר = שגיאה; absent = תקין)
        for rel in names:
            data = src.read(rel)
            if data is None:
                continue
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    return config


def compare_with_head(repo: Path, src: Source, config: dict) -> list[str]:
    """מי נוסף / השתנה / נמחק בשורשי ה-links ביחס ל-HEAD (רק בעץ העבודה)."""
    if src.ref:
        return []
    lines = []
    head_files: dict[str, bytes] = {}
    reader = BlobReader(repo)
    for entry in config["links_roots"]:
        out = git(repo, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", entry["path"], check=False)
        for rel in [x for x in out.decode("utf-8").split("\0") if x]:
            data = reader.read(f"HEAD:{rel}")
            if data is not None:
                head_files[rel] = data
    reader.close()
    now: dict[str, bytes] = {}
    for entry in config["links_roots"]:
        for rel in src.tree_files(entry["path"]) or []:
            d = src.read(rel)
            if d is not None:
                now[rel] = d
    for rel in sorted(set(now) - set(head_files)):
        lines.append(f"  + נוסף:   {rel}")
    for rel in sorted(set(head_files) - set(now)):
        lines.append(f"  - נמחק:   {rel}")
    for rel in sorted(set(now) & set(head_files)):
        if lf(head_files[rel]) != now[rel]:
            lines.append(f"  ~ השתנה:  {rel}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="שורש הריפו (ברירת מחדל: מחפש כלפי מעלה מהסקריפט)")
    ap.add_argument("--ref", help="קומיט לקריאה מתוך git במקום עץ העבודה (לא כותב)")
    ap.add_argument("--write", action="store_true", help="לכתוב את ה-lineage המעודכן לריפו")
    ap.add_argument("--keep-tmp", action="store_true", help="לא למחוק את העותק הזמני (לדיבוג)")
    a = ap.parse_args()
    if a.write and a.ref:
        raise SystemExit("--write לא תואם --ref")
    repo = Path(a.repo).resolve() if a.repo else find_repo(Path(__file__).parent)
    src = Source(repo, a.ref)
    tmp = Path(tempfile.mkdtemp(prefix="lineage-ws-"))
    try:
        config = materialize(src, tmp)
        mod = load_module(tmp / PACKAGING)
        cfg = mod.validate_config(mod.load_json(tmp / CONFIG))
        try:
            source_hash, packaged_hash, files = mod.tree_hashes(tmp, cfg)
        except mod.PackagingError as e:
            print(f"שגיאת אריזה (תקן לפני שממשיכים): {e}", file=sys.stderr)
            return 2
        new = {
            "config_sha256": mod.sha256_file(tmp / CONFIG),
            "source_links_tree_sha256": source_hash,
            "packaged_links_tree_sha256": packaged_hash,
        }
        print(f"# מקור: {a.ref or 'עץ העבודה (CRLF->LF)'} | קבצי links ארוזים: {len(files)}")
        for k in FIELDS:
            print(f"{k}: {new[k]}")
        lineage_raw = src.read(LINEAGE)
        if lineage_raw is None:
            print("אין manual_links_lineage.json", file=sys.stderr)
            return 2
        lineage = json.loads(lineage_raw.decode("utf-8"))
        diff = [k for k in FIELDS if lineage.get(k) != new[k]]
        for line in compare_with_head(repo, src, config):
            print(line)
        if not diff:
            print("ה-lineage תואם (אין מה לעדכן).")
        else:
            print("ה-lineage לא תואם בשדות: " + ", ".join(diff))
        if a.write:
            if diff:
                for k in FIELDS:
                    lineage[k] = new[k]
                out = mod.canonical_bytes(lineage) + b"\n"
                (repo / LINEAGE).write_bytes(out)
                (tmp / LINEAGE).write_bytes(out)
                print(f"נכתב {repo / LINEAGE}")
            # אימות סופי: ה-lineage הכתוב מול check --require-lineage בעותק הזמני (באותו מצב -I כמו ב-CI)
            r = subprocess.run([sys.executable, "-I", str(tmp / PACKAGING), "check", "--workspace", str(tmp),
                                "--require-lineage"], capture_output=True, encoding="utf-8", errors="replace")
            print("check --require-lineage:", "OK" if r.returncode == 0 else f"נכשל (rc={r.returncode})")
            print((r.stdout or r.stderr).strip())
            return r.returncode
        return 1 if diff else 0
    finally:
        if src.batch:
            src.batch.close()
        if a.keep_tmp:
            print(f"[העותק הזמני נשאר ב-{tmp}]")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
