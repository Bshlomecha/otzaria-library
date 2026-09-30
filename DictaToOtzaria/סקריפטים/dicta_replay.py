"""העברת תיקונים ידניים (תיקוני OCR ברמת מילה) מגרסה אחת של ספר להמרה חדשה.

    fixes, stats = extract(old_text, new_text)   # התיקונים שנעשו: old → new
    text2, st = apply(fixes, fresh_text)          # החלתם על המרה חדשה של אותו ספר

תיקון = (4 מילות הקשר משמאל, המילים הישנות, 4 מילות הקשר מימין, המילים החדשות).
העיגון נעשה על רצף האותיות בלבד (dicta_fp.keys), ולכן הוא עובד גם כשההמרה החדשה
מקטעת שורות אחרת, מסמנת <b> אחרת, או מצרפת/מפרידה מילים אחרת.

מה *לא* מוחל (ומדווח ב־stats):
* זוג שאינו "זוג תיקוני OCR" — יותר מ־1% מילים שנוספו/נמחקו, או יותר מ־20 בלוקים גדולים
  (מהדורה אחרת, החלפת טקסט מ־DBS וכד'): `pair_rejected`.
* דפוס החלפה שחוזר יותר מ־MASS_PATTERN פעמים ויוצר אות סופית באמצע מילה — חתימת
  ההחלפה הגלובלית "סי→סימן" שהשחיתה את בית יצחק: `mass_pattern`.
* עוגן שלא נמצא (`anchor_not_found`), שנמצא יותר מפעם אחת (`ambiguous`), תיקון שכבר
  קיים בהמרה החדשה (`already_fixed`), או תיקון רב־מילי שחוצה סימון (`markup_inside`).

נמדד (DESIGN, §4.3): על 18 ספרים ערוכים הוחלו 96.9% מהתיקונים שניתנים להחלה.
"""
from __future__ import annotations

import bisect
import collections
import difflib
import os
import re
import subprocess
import tempfile

from dicta_fp import FINALS, HEB_RE, TAG_RE, keys

K = 4
MAX_SUB_WORDS = 3
PAIR_MAX_INDEL = 0.01
PAIR_MAX_BLOCKS = 20
MASS_PATTERN = 20
_FINAL_INSIDE = re.compile(r"[ךםןףץ][א-ת]")


def _tokens(text: str) -> list[tuple[str, str]]:
    out = []
    for t in TAG_RE.sub(" ", text.replace("&nbsp;", " ").replace("&amp;", "&")).split():
        k = "".join(HEB_RE.findall(t)).translate(FINALS)
        if k:
            out.append((k, t))
    return out


def opcodes(a: list[str], b: list[str]) -> list[tuple]:
    """(tag, i1, i2, j1, j2) של ההבדלים בלבד. משתמש ב־diff של המערכת (Myers, מהיר
    על ספרים שלמים); אם הוא חסר — difflib."""
    try:
        d = tempfile.mkdtemp()
        fa, fb = os.path.join(d, "a"), os.path.join(d, "b")
        with open(fa, "w", encoding="utf-8") as f:
            f.write("\n".join(a) + "\n")
        with open(fb, "w", encoding="utf-8") as f:
            f.write("\n".join(b) + "\n")
        r = subprocess.run(["diff", "-d", fa, fb], capture_output=True, text=True, encoding="utf-8")  # -d: diff מינימלי; בלעדיו diff של macOS "מוותר" על בלוקים גדולים
        os.remove(fa)
        os.remove(fb)
        os.rmdir(d)
        if r.returncode not in (0, 1):
            raise OSError(r.stderr)
    except OSError:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        return [o for o in sm.get_opcodes() if o[0] != "equal"]
    ops = []
    for line in r.stdout.splitlines():
        m = re.match(r"^(\d+)(?:,(\d+))?([acd])(\d+)(?:,(\d+))?$", line)
        if not m:
            continue
        a1 = int(m.group(1))
        a2 = int(m.group(2) or a1)
        c = m.group(3)
        b1 = int(m.group(4))
        b2 = int(m.group(5) or b1)
        if c == "a":
            ops.append(("insert", a1, a1, b1 - 1, b2))
        elif c == "d":
            ops.append(("delete", a1 - 1, a2, b1, b1))
        else:
            ops.append(("replace", a1 - 1, a2, b1 - 1, b2))
    return ops


def classify(ops, a, b):
    """מפצל את ההבדלים: צירוף/פיצול מילים, החלפות קטנות (תיקוני OCR), הוספה/מחיקה, בלוקים."""
    c = {"joinsplit": 0, "subst": 0, "ins_words": 0, "del_words": 0, "big_blocks": 0}
    subs = []
    for t, i1, i2, j1, j2 in ops:
        A = "".join(a[i1:i2])
        B = "".join(b[j1:j2])
        if t == "replace" and A == B:
            c["joinsplit"] += 1
        elif t == "replace" and i2 - i1 <= MAX_SUB_WORDS and j2 - j1 <= MAX_SUB_WORDS:
            c["subst"] += 1
            subs.append((i1, i2, j1, j2))
        elif t == "insert" or (t == "replace" and i2 - i1 < j2 - j1 and i2 - i1 <= MAX_SUB_WORDS):
            c["ins_words"] += (j2 - j1) - (i2 - i1)
            c["big_blocks"] += t == "replace"
        elif t == "delete" or (t == "replace" and j2 - j1 <= MAX_SUB_WORDS):
            c["del_words"] += (i2 - i1) - (j2 - j1)
            c["big_blocks"] += t == "replace"
        else:
            c["big_blocks"] += 1
    return c, subs


def extract(old_text: str, new_text: str, *, strict_pair: bool = True):
    """התיקונים old→new. מחזיר (fixes, stats). stats['pair_rejected'] אם אינו זוג תיקונים."""
    a = _tokens(old_text)
    b = _tokens(new_text)
    ak = [k for k, _ in a]
    bk = [k for k, _ in b]
    c, subs = classify(opcodes(ak, bk), ak, bk)
    stats = dict(c)
    if strict_pair and ((c["ins_words"] + c["del_words"]) > PAIR_MAX_INDEL * max(1, len(bk))
                        or c["big_blocks"] > PAIR_MAX_BLOCKS):
        stats["pair_rejected"] = 1
        return [], stats
    fixes = []
    for i1, i2, j1, j2 in subs:
        fixes.append(dict(
            left=ak[max(0, i1 - K):i1], old=ak[i1:i2], right=ak[i2:i2 + K],
            new=[TAG_RE.sub("", t) for _, t in b[j1:j2]], newkeys=bk[j1:j2],
            left_new=bk[max(0, j1 - K):j1], right_new=bk[j2:j2 + K]))
    # דפוס המוני שמייצר אות סופית באמצע מילה (סי→סימן) — לא מעבירים.
    pat = collections.Counter((" ".join(f["old"]), " ".join(f["newkeys"])) for f in fixes)
    bad = {p for p, n in pat.items() if n > MASS_PATTERN
           and any(_FINAL_INSIDE.search(w) for f in fixes if (" ".join(f["old"]), " ".join(f["newkeys"])) == p
                   for w in f["new"])}
    if bad:
        kept = [f for f in fixes if (" ".join(f["old"]), " ".join(f["newkeys"])) not in bad]
        stats["mass_pattern"] = len(fixes) - len(kept)
        fixes = kept
    return fixes, stats


def _spans(t: str):
    out = []
    for m in re.finditer(r"<[^>]+>|[^\s<]+", t):
        s = m.group(0)
        if s.startswith("<"):
            continue
        k = "".join(HEB_RE.findall(s)).translate(FINALS)
        if k:
            out.append((k, m.start(), m.end()))
    return out


def _edge(seg: str):
    lead = re.match(r"^[^א-ת]*", seg).group(0)
    trail = re.search(r"[^א-ת]*$", seg).group(0)
    return lead, trail


def apply(fixes: list[dict], text: str):
    """מחיל את התיקונים על text. מחזיר (text, stats)."""
    spans = _spans(text)
    letters = "".join(k for k, _, _ in spans)
    starts = []
    pos = 0
    for k, _, _ in spans:
        starts.append(pos)
        pos += len(k)
    stat = collections.Counter()
    edits = []
    for f in fixes:
        L, O, R = "".join(f["left"]), "".join(f["old"]), "".join(f["right"])
        pat = L + O + R
        if len(pat) < 12:
            stat["context_too_short"] += 1
            continue
        hits = [m.start() for m in re.finditer(re.escape(pat), letters)]
        if not hits:
            newpat_a = L + "".join(f["newkeys"]) + R
            newpat_b = "".join(f["left_new"]) + "".join(f["newkeys"]) + "".join(f["right_new"])
            stat["already_fixed" if (newpat_a in letters or newpat_b in letters) else "anchor_not_found"] += 1
            continue
        if len(hits) > 1:
            stat["ambiguous"] += 1
            continue
        o0 = hits[0] + len(L)
        o1 = o0 + len(O)
        ti = bisect.bisect_right(starts, o0) - 1
        tj = bisect.bisect_right(starts, o1 - 1) - 1
        if starts[ti] != o0 or starts[tj] + len(spans[tj][0]) != o1:
            stat["token_boundary_mismatch"] += 1
            continue
        s, e = spans[ti][1], spans[tj][2]
        if "<" in text[s:e]:
            if tj - ti + 1 == len(f["new"]):   # 1:1 — מחליפים מילה־מילה ומשאירים את הסימון
                for q, nw in zip(range(ti, tj + 1), f["new"]):
                    ss, ee = spans[q][1], spans[q][2]
                    lead, trail = _edge(text[ss:ee])
                    core = re.sub(r"^[^א-ת]*|[^א-ת]*$", "", nw)
                    edits.append((ss, ee, lead + core + trail))
                stat["applied"] += 1
                continue
            stat["markup_inside"] += 1
            continue
        lead, trail = _edge(text[s:e])
        core = re.sub(r"^[^א-ת]*|[^א-ת]*$", "", " ".join(f["new"]))
        edits.append((s, e, lead + core + trail))
        stat["applied"] += 1
    edits.sort(key=lambda x: -x[0])
    last = None
    for s, e, rep in edits:
        if last is not None and e > last:
            stat["overlap_skipped"] += 1
            continue
        text = text[:s] + rep + text[e:]
        last = s
    return text, dict(stat)


def substitution_count(a_text: str, b_text: str) -> int:
    """כמה החלפות־מילים קטנות (שונות באותיות) מפרידות בין שני טקסטים."""
    a = keys(a_text)
    b = keys(b_text)
    return classify(opcodes(a, b), a, b)[0]["subst"]
