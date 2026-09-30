"""מיקום ספר דיקטה חדש בעץ הקטגוריות — לפי עץ ספריא, לא לפי המיפוי של דיקטה.

היעד הוא תמיד "מדף" קיים בעץ: קטגוריה של ספריא (מתוך `sefaria_categories` בטבלה, שנגזרה
מטבלת `category` ב־seforim.db), או תיקייה בעץ דיקטה שיש בה ספרים של 3 מחברים ומעלה.
הקטגוריה/תת־הקטגוריה של דיקטה משמשות רק כמאפיינים.

הכללים לפי הסדר (הראשון שמתאים קובע). הדיוק נמדד ב־leave-one-out על 825 ספרים ממוקמים:

| כלל | תנאי | דרג | דיוק מדף |
| --- | --- | --- | --- |
| R1 סדרה | אותו גזע שם + אותו מחבר + אותה קטגוריה של דיקטה כמו ספר ממוקם | A | 97.8% |
| R3 רמב"ם | קטגוריה "רמב"ם ומפרשיו" או רמב"ם בשם | A | 96.6% |
| R3 שו"ע | קטגוריית הלכה + שם חלק של שו"ע בשם | A | 100% |
| R3 שו"ת | קטגוריה/שם שו"ת | B | 88.1% |
| R3 מסכת | שם מסכת בשם | B | 81.2% |
| R2 מחבר | ≥2 ספרים של המחבר באותה (קטגוריה, תת־קטגוריה), כולם על מדף אחד | B | 86.2% |
| R4 טבלה | (קטגוריה, תת־קטגוריה) → מדף, n≥5 ו־≥80% | B | 75.6% |

דרג A = "מיקום בטוח" (ר' DESIGN §10): 97.7%. כל השאר — לא בטוח.
"""
from __future__ import annotations

import collections
import re

MASECHTOT = ("ברכות שבת עירובין פסחים שקלים יומא סוכה ביצה תענית מגילה חגיגה יבמות כתובות נדרים נזיר "
             "סוטה גיטין קידושין סנהדרין מכות שבועות הוריות זבחים מנחות חולין בכורות ערכין תמורה כריתות "
             "מעילה תמיד נדה עדיות אבות").split() + [
    "ראש השנה", "מועד קטן", "בבא קמא", "בבא מציעא", "בבא בתרא", "עבודה זרה"]
SA_SECTIONS = ["אורח חיים", "יורה דעה", "אבן העזר", "חושן משפט", 'אה"ע', 'יו"ד', 'או"ח', 'חו"מ']
TORAH = ["בראשית", "שמות", "ויקרא", "במדבר", "דברים", "על התורה", 'עה"ת', "התורה"]
_VOL = re.compile(r"""(\s*[-–]\s*[א-ת"']{1,4}$|\s+חלק\s+\S+$|\s+ח"\S+$|\s+(מהדורא|מהדורה)\s+\S+$|\s+\([^)]*\)$"""
                  r"""|\s+[א-ת]{1,2}'?$|\s+(קמא|תנינא|תליתאה|בתרא|החדשות|הישנות)$)""")
_Q = re.compile(r"[\"״'׳]")
TIER_A = {"R1-series", "R3-rambam", "R3-SA"}


def nq(s: str) -> str:
    return _Q.sub("", s or "")


def stem(name: str) -> str:
    n = (name or "").replace('שו"ת ', "").replace("שות ", "").strip()
    suffixes = sorted(SA_SECTIONS + MASECHTOT + TORAH, key=len, reverse=True)
    for _ in range(4):
        cut = False
        for s in suffixes:
            for pre in (" על ", " מסכת ", " "):
                if n.endswith(pre + s):
                    n = n[: -len(pre + s)].rstrip()
                    cut = True
                    break
            if cut:
                break
        n2 = _VOL.sub("", n).strip()
        if n2 == n and not cut:
            break
        n = n2 or n
    return nq(n)


class Placer:
    """`placed`: [{name, author, cat, sub, dirs: [נתיב יחסי ל־אוצריא/]}]; `sefaria_categories`: נתיבים בלי גרשיים."""

    def __init__(self, placed: list[dict], sefaria_categories=(), *, r2k=2, r2s=1.0, r4n=5, r4s=0.8):
        self.placed = placed
        self.sef = {nq(c) for c in sefaria_categories}
        self.r2k, self.r2s, self.r4n, self.r4s = r2k, r2s, r4n, r4s
        au = collections.defaultdict(set)
        for x in placed:
            for d in x["dirs"]:
                parts = d.split("/")
                for i in range(1, len(parts) + 1):
                    au["/".join(parts[:i])].add(x.get("author", ""))
        self.shelves = {k for k, v in au.items() if len(v) >= 3}
        self._stems = collections.defaultdict(list)
        for i, x in enumerate(placed):
            self._stems[stem(x["name"])].append(i)

    def shelf(self, d: str) -> str:
        parts = d.split("/")
        g = []
        for i in range(1, len(parts) + 1):
            k = "/".join(parts[:i])
            if nq(k) in self.sef or k in self.shelves:
                g = parts[:i]
            else:
                break
        return "/".join(g)

    @staticmethod
    def _primary(x) -> str:
        return collections.Counter(x["dirs"]).most_common(1)[0][0]

    def predict(self, x: dict, exclude: int | None = None):
        """מחזיר (נתיב יחסי ל־אוצריא/ או None, שם הכלל, 'A'/'B'/None)."""
        name, sub, cat = x.get("name", ""), x.get("sub", "") or "", x.get("cat", "") or ""
        s = stem(name)
        sib = [self.placed[i] for i in self._stems.get(s, []) if i != exclude and s
               and self.placed[i].get("author") == x.get("author") and self.placed[i].get("cat") == cat]
        if sib:
            p = collections.Counter(self._primary(y) for y in sib).most_common(1)[0][0]
            return p, "R1-series", "A"
        if cat.startswith('רמב"ם') or 'רמב"ם' in name or "רמבם" in name:
            return "הלכה/משנה תורה/מפרשים", "R3-rambam", "A"
        if cat.startswith("שאלות") or name.startswith('שו"ת') or name.startswith("שות") or "תשובות" in name:
            p = "שות/ראשונים" if "ראשונים" in sub else "שות/גאונים" if "גאונים" in sub else "שות/אחרונים"
            return p, "R3-shut", "B"
        if any(f" {m}" in f" {name}" for m in MASECHTOT) and cat in ("תלמוד ומפרשיו", "שונות", "דרשות ודרושים", "חסידות"):
            return ("תלמוד בבלי/ראשונים" if sub == "ראשונים" else "תלמוד בבלי/אחרונים"), "R3-masechet", "B"
        if cat.startswith("הלכה") and any(sct in name for sct in SA_SECTIONS):
            return "הלכה/שולחן ערוך/מפרשים", "R3-SA", "A"
        au = [y for i, y in enumerate(self.placed) if i != exclude and x.get("author")
              and y.get("author") == x.get("author") and (y.get("cat"), y.get("sub")) == (cat, sub)]
        if au:
            c = collections.Counter(self.shelf(self._primary(y)) for y in au)
            top, k = c.most_common(1)[0]
            if top and k >= self.r2k and k / sum(c.values()) >= self.r2s:
                return top, "R2-author", "B"
        c = collections.Counter(self.shelf(self._primary(y)) for i, y in enumerate(self.placed)
                                if i != exclude and (y.get("cat"), y.get("sub")) == (cat, sub))
        if c:
            top, k = c.most_common(1)[0]
            tot = sum(c.values())
            if top and tot >= self.r4n and k / tot >= self.r4s:
                return top, "R4-table", "B"
        return None, "fallback", None

    def leave_one_out(self):
        """(מספר, נכונים) לכל דרג — מדף נכון = אותו shelf() כמו אחת התיקיות בפועל."""
        n = collections.Counter()
        ok = collections.Counter()
        for i, x in enumerate(self.placed):
            p, _rule, tier = self.predict(x, exclude=i)
            t = tier or "F"
            n[t] += 1
            if p and any(self.shelf(p) == self.shelf(d) for d in x["dirs"]):
                ok[t] += 1
        return dict(n), dict(ok)
