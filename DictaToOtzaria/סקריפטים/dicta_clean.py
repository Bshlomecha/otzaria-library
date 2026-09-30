#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dicta_clean.py — ניקוי דטרמיניסטי (ללא AI) לקבצי TXT של ספרי דיקטה.

רץ אחרי ההמרה (`dicta_convert.py`) ולפני עבודת הכותרות. ממשק שורת הפקודה
הוותיק נשאר בשם `ניקוי_דטרמיניסטי.py` (עוטף את המודול הזה).

כללים (לפי סדר ההרצה):
  G — נירמול תווים: NFC, הסרת BOM / רוחב־אפס / סימני כיווניות / מקף רך,
      רווחים מיוחדים → רווח, רווחים כפולים וסופיים.
  E — <b>X</b> של 1–3 אותיות דבוק לאותיות משני צדדיו (הדגשה באמצע מילה):
      מסיר את התג.
  F — שורה יתומה שכל תוכנה `ע"א` / `ע"ב` / `עמוד א|ב` — מוצמדת לשורה הקודמת,
      כדי שכלי כותרות הדף יזהו `דף X ע"א`.
  B — (לקבצים ישנים בלבד, כבוי כברירת מחדל) מיזוג שורה שמתחילה ב־<b> אל
      הקודמת, כשהקודמת אינה נגמרת בסימן סיום. תיקון לבאג של הממיר הישן, שפתח
      שורה לפני כל מילה מודגשת. על פלט `dicta_convert.py` הוא מזיק: שם כל
      שורה היא פסקה של דיקטה או סוף עניין — ר' README.
  H — (כבוי כברירת מחדל) הסרת <b> משורה שכל תוכנה מספר גימטריה **עם**
      גרש/גרשיים (`<b>ל"ה</b>`). בגרסה הקודמת הכלל תפס כל 1–3 אותיות
      (`<b>שם</b>`, `<b>ר'</b>`, `<b>כסף</b>`) והרס דיבורים המתחילים אמיתיים.
  P, S, R, T — תיקוני OCR חוזרים (פעילים; פונקציות טהורות לשורה, מיוצאות
      כ־OCR_RULES כדי להריץ אותן גם על ספרים קיימים):
      P — "ודף כ"ג)" → "(דף כ"ג)": ו' שנקראה במקום "(" לפני מילת הפניה.
      S — אות סופית באמצע מילה ("דאםור" → "דאסור", "המיםשל" → "המים של"),
          רק כשמילון השכיחות dicta_word_freq.tsv.gz מוכיח את התיקון.
      R — "רמב"מ" → "רמב"ם".   T — "התוס" → "התוס'" (קיצור תוספות).
  M — (אחרון) איחוד רצפי <b> סמוכים: `<b>א</b> <b>ב</b>` → `<b>א ב</b>`
      (merge_bold_runs). לא מאחד מעבר לתג אחר, מעבר לשורה, תג עם תכונות,
      או כשאחד הצדדים הוא סמן מקור (תוס' / רש"י / פירש"י / ד"ה / בא"ד / גמ' / מתני').

שימוש:
  python3 dicta_clean.py FILE [FILE ...]
  python3 dicta_clean.py --dir PATH [--glob "*.txt"]
  python3 dicta_clean.py FILE --only M          # רק איחוד רצפי <b>
  python3 dicta_clean.py FILE --only S          # רק כלל OCR אחד (גם FINALS/PAREN/RAMBAM/TOSAFOT)
  python3 dicta_clean.py FILE --only OCR        # ארבעת כללי ה־OCR בלבד
  python3 dicta_clean.py --build-word-freq REPO # בנייה מחדש של מילון השכיחות
  python3 dicta_clean.py FILE --enable B        # כולל B לקובץ מהממיר הישן
  python3 dicta_clean.py FILE --dry-run --json

קוד יציאה: 0 = הצלחה, 2 = שגיאה. הרצה חוזרת על קובץ נקי לא משנה דבר.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ----------------------------------------------------------------------------
# תוצאות
# ----------------------------------------------------------------------------


@dataclass
class FileReport:
    file: str
    changed: bool = False
    counts: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    error: str | None = None


def _bump(report: FileReport, key: str, n: int = 1) -> None:
    if n:
        report.counts[key] = report.counts.get(key, 0) + n


# ----------------------------------------------------------------------------
# G — נירמול תווים
# ----------------------------------------------------------------------------

_INVISIBLE_RE = re.compile(
    "[﻿​‌‍‎‏‪-‮⁦-⁩­]")
_SPACE_LIKE_RE = re.compile("[\t  -   　]")


def fix_g_normalize(text: str, report: FileReport) -> str:
    original = text
    nfc = unicodedata.normalize("NFC", text)
    if nfc != text:
        _bump(report, "G_nfc_normalized", 1)
        text = nfc
    new = _INVISIBLE_RE.sub("", text)
    if new != text:
        _bump(report, "G_invisible_removed", len(text) - len(new))
        text = new
    n_sp = len(_SPACE_LIKE_RE.findall(text))
    if n_sp:
        text = _SPACE_LIKE_RE.sub(" ", text)
        _bump(report, "G_special_spaces_collapsed", n_sp)
    trailing = multi = 0
    fixed = []
    for ln in text.split("\n"):
        s = ln.rstrip()
        if s != ln:
            trailing += 1
        s2 = re.sub(r" {2,}", " ", s)
        if s2 != s:
            multi += 1
        fixed.append(s2)
    text = "\n".join(fixed)
    _bump(report, "G_trailing_ws_lines", trailing)
    _bump(report, "G_double_spaces_lines", multi)
    if text != original:
        report.changed = True
    return text


# ----------------------------------------------------------------------------
# E — <b> באמצע מילה
# ----------------------------------------------------------------------------

_MIDWORD_BOLD_RE = re.compile(
    r"(?P<before>[א-ת])<b>(?P<inner>[א-ת]{1,3})</b>(?P<after>[א-ת])")


def fix_e_midword_bold(text: str, report: FileReport) -> str:
    count = 0

    def _repl(m):
        nonlocal count
        count += 1
        return m.group("before") + m.group("inner") + m.group("after")

    new = text
    while True:
        nxt = _MIDWORD_BOLD_RE.sub(_repl, new)
        if nxt == new:
            break
        new = nxt
    if count:
        _bump(report, "E_midword_bold_unwrapped", count)
        report.changed = True
    return new


# ----------------------------------------------------------------------------
# H — מספר עמוד מדומה מודגש (כבוי כברירת מחדל)
# ----------------------------------------------------------------------------

# רק מספר גימטריה עם גרש/גרשיים: ל"ה / קי"א / ט' — לא "שם", "ר'" (=רבי) וכד'.
_GEMATRIA_NUM_RE = re.compile(
    r"^\s*<b>\s*(?:[קרשת]?[יכלמנסעפצ]?[א-ט]?)[\"״]?[א-ת][\"'״׳]?\s*</b>\s*$")
_GEMATRIA_WITH_MARK_RE = re.compile(r"[\"'״׳]")
# אותיות בודדות עם גרש שהן גם מילה נפוצה (ר' = רבי, ש' = שם...) — לא נוגעים
_H_EXCLUDE = {"ר'", "ר׳", "ש'", "ש׳", "ס'", "ס׳", "פ'", "פ׳", "ד'", "ד׳", "ה'", "ה׳"}


def fix_h_fake_bold_pages(text: str, report: FileReport) -> str:
    out, count = [], 0
    for ln in text.split("\n"):
        inner = re.sub(r"</?b>", "", ln).strip()
        if (_GEMATRIA_NUM_RE.match(ln) and _GEMATRIA_WITH_MARK_RE.search(inner)
                and inner not in _H_EXCLUDE):
            out.append(inner)
            count += 1
        else:
            out.append(ln)
    if count:
        _bump(report, "H_fake_bold_pages_unwrapped", count)
        report.changed = True
    return "\n".join(out)


# ----------------------------------------------------------------------------
# B — מיזוג המשכים מודגשים (לפלט הממיר הישן בלבד)
# ----------------------------------------------------------------------------

_BOLD_LEAD_RE = re.compile(r"^\s*<b>(?P<first>[^<>\n]+)</b>")
_HEADING_TRIGGERS = {
    "פרק", "סימן", "סעיף", "דף", "מסכת", "פתיחה", "הקדמה", "הקדמת",
    "אות", "סי'", "סי", "פ'", "ס'", "מבוא", "חלק", "ספר", "פתחי",
    "שער", "מאמר", "תשובה", "שאלה", "קונטרס", "הלכות", "הלכה", "משנה",
    "כלל", "פלג", "ענף", "דרוש", "דרשה", "פרשת", "פרשה", "מצוה", "שורש",
}
_AYIN_FORMS = {'ע"א', 'ע"ב', "ע'א", "ע'ב", "ע״א", "ע״ב", "עמוד"}
_SENTENCE_END = (".", ":", "!", "?", "׃", ";", ")", "]", "}")
_CLOSING_TAGS = tuple(f"</h{i}>" for i in range(1, 7)) + ("</big>", "</small>")
_BOLD_ONLY_LINE_RE = re.compile(r"^\s*(?:<b>[^<>\n]+</b>\s*)+$")


def _words(line: str) -> list[str]:
    return re.sub(r"<[^>]+>", " ", line).split()


def _ends_sentence(line: str) -> bool:
    s = line.rstrip()
    if not s:
        return True
    return s.endswith(_SENTENCE_END) or s.endswith(_CLOSING_TAGS) or \
        re.sub(r"</b>$", "", s).rstrip().endswith(_SENTENCE_END)


def _is_protected_line(line: str) -> bool:
    s = line.strip()
    return not s or bool(re.match(r"^<h[1-6]>", s))


def fix_b_merge_bold_continuations(text: str, report: FileReport) -> str:
    lines = text.split("\n")
    if len(lines) < 3:
        return text
    head, body = lines[:2], lines[2:]
    merged: list[str] = []
    count = 0
    for ln in body:
        if not merged:
            merged.append(ln)
            continue
        prev = merged[-1]
        m = _BOLD_LEAD_RE.match(ln)
        if (_is_protected_line(prev) or _is_protected_line(ln) or not m
                or _ends_sentence(prev)):
            merged.append(ln)
            continue
        first_word = m.group("first").strip().split()[0] if m.group("first").strip() else ""
        if first_word in _HEADING_TRIGGERS or first_word in _AYIN_FORMS:
            merged.append(ln)
            continue
        # שורה קודמת שכולה הדגשה קצרה (כותרת לא מסומנת: "<b>הלכות תשובה</b>")
        # או שורה נוכחית כזו — לא ממזגים.
        if (_BOLD_ONLY_LINE_RE.match(prev) and len(_words(prev)) <= 6) or \
                (_BOLD_ONLY_LINE_RE.match(ln) and len(_words(ln)) <= 6
                 and _ends_sentence(ln) is False and len(_words(prev)) <= 3):
            merged.append(ln)
            continue
        merged[-1] = prev.rstrip() + " " + ln.lstrip()
        count += 1
    if count:
        _bump(report, "B_bold_continuations_merged", count)
        report.changed = True
        return "\n".join(head + merged)
    return text


# ----------------------------------------------------------------------------
# F — ע"א / ע"ב יתום
# ----------------------------------------------------------------------------

_AYIN_AB_RE = re.compile(
    r'^\s*(?:<b>\s*)?(?:ע["\'״׳]+?[אב]|עמוד\s+[אב])\s*[.,:]?\s*(?:</b>\s*)?[.,:]?\s*$')


def fix_f_orphan_ayin(text: str, report: FileReport) -> str:
    lines = text.split("\n")
    if len(lines) < 3:
        return text
    head, body = lines[:2], lines[2:]
    out: list[str] = []
    count = 0
    for ln in body:
        if _AYIN_AB_RE.match(ln) and out and not _is_protected_line(out[-1]):
            # רק התגים יורדים; הפיסוק (ע"ב:) הוא טקסט המקור ונשמר
            inner = re.sub(r"</?b>", "", ln).strip()
            out[-1] = out[-1].rstrip() + " " + inner
            count += 1
            continue
        out.append(ln)
    if count:
        _bump(report, "F_orphan_ayin_merged", count)
        report.changed = True
        return "\n".join(head + out)
    return text


# ----------------------------------------------------------------------------
# M — איחוד רצפי <b> סמוכים
# ----------------------------------------------------------------------------

# סמני מקור: רצף מודגש שכולו אחד מאלה, או שמתחיל באחד מאלה, הוא יחידה
# נפרדת (<b>תוס'</b> <b>ד"ה ולא</b> נשארים שניים — מוסכמה §6).
_G = "['׳’`]"          # גרש
_GG = "[\"״”“]"   # גרשיים
_SOURCE_MARKERS = [
    f"תוס{_G}", "תוספות", f"רש{_GG}י", f"פי?רש{_GG}י", f"ד{_GG}ה", f"בא{_GG}ד",
    f"גמ{_G}", "גמרא", f"מתני{_G}", "מתניתין",
]
_MARKER_WORD_RE = re.compile(
    r"^(?:[ובד]{0,2})(?:" + "|".join(_SOURCE_MARKERS) + r")[.,:;]*$")
# </b> + רווחים (לא ירידת שורה) + <b> — ללא תכונות
_BOLD_GAP_RE = re.compile(r"</b>([ \t]*)<b>")
_B_OPEN_ANY_RE = re.compile(r"<b(?:\s[^>]*)?>")


def _is_marker_run(inner: str) -> bool:
    ws = re.sub(r"<[^>]+>", " ", inner).split()
    return len(ws) == 1 and bool(_MARKER_WORD_RE.match(ws[0]))


def _starts_with_marker(inner: str) -> bool:
    ws = re.sub(r"<[^>]+>", " ", inner).split()
    return bool(ws) and bool(_MARKER_WORD_RE.match(ws[0]))


def _merge_bold_line(line: str, keep_markers: bool, stats: dict) -> str:
    if "<b>" not in line:
        return line
    # רווחים בקצוות התג → מחוץ לתג; תגים ריקים → הסרה
    s = re.sub(r"<b>([ \t]+)", r"\1<b>", line)
    s = re.sub(r"([ \t]+)</b>", r"</b>\1", s)
    while True:
        s2 = re.sub(r"<b></b>", "", s)
        if s2 == s:
            break
        s = s2
    out = []
    pos = 0
    for m in _BOLD_GAP_RE.finditer(s):
        # הרצף השמאלי: מתג ה־<b…> הפתוח האחרון לפני m.start()
        opens = list(_B_OPEN_ANY_RE.finditer(s, 0, m.start()))
        right_close = s.find("</b>", m.end())
        if not opens or right_close < 0:
            continue
        lo = opens[-1]
        if lo.group(0) != "<b>":
            continue  # <b> עם תכונות — לא נוגעים
        left = s[lo.end():m.start()]
        right = s[m.end():right_close]
        if keep_markers and (_is_marker_run(left) or _starts_with_marker(right)):
            stats["kept_marker"] = stats.get("kept_marker", 0) + 1
            continue
        if re.search(r"[.:]\s*$", re.sub(r"<[^>]+>", "", left)):
            stats["merged_after_sentence_end"] = stats.get("merged_after_sentence_end", 0) + 1
        stats["merged"] = stats.get("merged", 0) + 1
        out.append(s[pos:m.start()])
        out.append(" " if m.group(1) else "")
        pos = m.end()
    out.append(s[pos:])
    res = "".join(out)
    # הוצאת רווחים מקצות התג לא תיצור רווח בתחילת/סוף שורה או רווח כפול
    # שלא היו במקור (M רץ אחרי G; בלי זה finalize_text אינו אידמפוטנטי)
    if not line[:1].isspace():
        res = res.lstrip(" \t")
    if not line[-1:].isspace():
        res = res.rstrip(" \t")
    if "  " not in line:
        res = re.sub(r" {2,}", " ", res)
    return res


def merge_bold_runs(text: str, keep_markers: bool = True,
                    stats: dict | None = None) -> str:
    """מאחד `</b>` + רווחים בלבד + `<b>` לרצף מודגש אחד, שורה־שורה.

    `<b>הקדמת</b> <b>המחבר.</b> <b>בשפה</b>` → `<b>הקדמת המחבר. בשפה</b>`.
    - רק `<b>` ללא תכונות; לא מעבר לתג אחר (`</big> <b>` אינו רווח בלבד),
      לא מעבר לירידת שורה; הרווח שבין הרצפים נשמר כרווח יחיד.
    - `keep_markers`: לא לאחד כשהרצף השמאלי כולו סמן מקור או כשהימני מתחיל
      בסמן מקור (תוס' / רש"י / ד"ה / בא"ד / גמ' / מתני', גם עם ו/ב/ד בתחילה).
    - `stats` (אופציונלי) מקבל: merged, kept_marker, merged_after_sentence_end.
    """
    st = stats if stats is not None else {}
    return "\n".join(_merge_bold_line(ln, keep_markers, st) for ln in text.split("\n"))


def fix_m_merge_bold_runs(text: str, report: FileReport) -> str:
    st: dict = {}
    new = merge_bold_runs(text, stats=st)
    for k, v in st.items():
        _bump(report, "M_" + k, v)
    if new != text:
        report.changed = True
    return new


# ----------------------------------------------------------------------------
# OCR — טעויות OCR חוזרות (P, S, R, T)
# ----------------------------------------------------------------------------
#
# כל כלל הוא פונקציה טהורה על שורה אחת: `fn(line, log=None) -> line`. `log`
# (רשימה, אופציונלי) מקבל (עמדה, ישן, חדש) לכל החלפה. OCR_RULES מייצא את
# ארבעתן לפי סדר ההרצה, כדי שאפשר יהיה להריץ אותן שורה־שורה על ספרים קיימים.
# הכללים אינם נוגעים בתגים, אינם מוסיפים/מוחקים שורות, והרצה שנייה לא משנה.

_TAG_RE = re.compile(r"<[^>]*>")
_NIKUD_CH = "֑-ׇ"
_Q1 = "'׳"            # גרש
_Q2 = "\"״"           # גרשיים
_QALL = "\"'״׳`’‘”“"


def _mask_tags(line: str) -> str:
    """תגים → \\0 באותו אורך (העמדות נשמרות, ואין אות עברית בתוך תג)."""
    return _TAG_RE.sub(lambda m: "\0" * len(m.group()), line)


def _apply_edits(line: str, edits: list, log: list | None) -> str:
    """edits = [(start, end, new)] לא חופפים, על עמדות השורה המקורית."""
    if not edits:
        return line
    out, pos = [], 0
    for s, e, new in sorted(edits):
        out.append(line[pos:s])
        out.append(new)
        if log is not None:
            log.append((s, line[s:e], new))
        pos = e
    out.append(line[pos:])
    return "".join(out)


# --- מספר גימטריה (לכלל P) ---------------------------------------------------

_GEM_VAL = dict(zip("אבגדהוזחטיכלמנסעפצקרשת",
                    (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80,
                     90, 100, 200, 300, 400)))
# ראשי תיבות שנראים כמספר יורד (מג"א = 40,3,1) ואינם מספר דף/סימן
_NOT_NUMBERS = {"מגא", "מא", "רמא", "טז", "שך", "רן", "רי", "רח", "תהד", "רמ",
                "מב", "רא", "שם", "ים", "כל", "לא", "גם", "יש", "כן", "מן", "זה"}
# מילות מראה מקום שמותרות בין מילת ההפניה ל־")"
_REF_TOKENS = {"סק", "סעיף", "סע", "ס", "אות", "עמוד", "עמ", "ע", "דף", "ד", "סי",
               "סימן", "הל", "הלכה", "ה", "מ", "מה", "מהל", "פ", "פרק", "ח",
               "חא", "חב", "חג", "חד", "שם", "בד", "דה", "בדה", "וסי", "ודף",
               "וסעיף", "וס", "ואות", "וע", "ועא", "ועב", "סוף", "ריש", "סס",
               "ססי", "בסוף", "בריש", "סוס", "סוסי"}


def _bare(tok: str) -> str:
    return re.sub("[" + _QALL + ".,:;]", "", tok)


def _is_gematria(tok: str) -> bool:
    t = _bare(tok)
    if not 1 <= len(t) <= 4 or t in _NOT_NUMBERS or not all(c in _GEM_VAL for c in t):
        return False
    if t in ("טו", "טז"):
        return True
    v = [_GEM_VAL[c] for c in t]
    return all(a > b or a == b == 400 for a, b in zip(v, v[1:]))


# --- P: "ו" במקום "(" לפני מילת הפניה ----------------------------------------
#
# "כדאיתא בשבת ודף כ"ג) והובא" → "כדאיתא בשבת (דף כ"ג) והובא".
# תנאים: הו' בתחילת מילה ולא בתוך סוגריים פתוחים; הסוגר הראשון אחריה הוא ")"
# (בלי פותח), עד 30 תווים; בין מילת ההפניה ל־")" רק מראה מקום (מספר / ס"ק /
# אות...) — לפרק/פ' גם שם (פ' קדושים), ל"שם" רק מספרים; בלי סוף משפט באמצע;
# לא מיד אחרי הפניה אחרת ("דף י"ב ודף ל"ג)"); ורק מועמד אחד לכל ")"
# (ב"סי' א' וסי' ב')" לא ברור איזו ו' היא הסוגר).

_P_NUM_REFS = ("דף", "ד'", "סי'", "סימן", "סעיף", "סע'", "עמוד", "עמ'")
_P_NAME_REFS = ("פרק", "פ'")
_P_REF_BARE = {"דף", "ד", "סי", "סימן", "סעיף", "סע", "עמוד", "עמ", "פרק", "פ", "ס"}
_P_REF_RE = re.compile(
    r"(?:(?<=[\s\0])|^)ו(?P<ref>דף|ד[" + _Q1 + r"]|סי[" + _Q1 + r"]|סימן|סעיף|סע["
    + _Q1 + r"]|עמוד|עמ[" + _Q1 + r"]|פרק|פ[" + _Q1 + r"]|שם)(?![א-ת" + _QALL
    + _NIKUD_CH + r"])")


def _p_seg_ok(ref: str, seg: str) -> bool:
    vis = seg.replace("\0", "")
    if len(vis) > 30 or re.search(r"[:;\[\]]|\.\s", vis):
        return False
    toks = seg.replace("\0", " ").split()
    ref = ref.replace("׳", "'")
    if toks and len(toks) >= 2 and len(_bare(toks[-1])) == 1 \
            and not re.search("[" + _QALL + "]", toks[-1]):
        return False  # "…שנתאלמנה ו)" — תווית רשימה, לא מספר
    if ref in _P_NUM_REFS:
        return bool(toks) and _is_gematria(toks[0]) and all(
            _is_gematria(t) or _bare(t) in _REF_TOKENS for t in toks[1:])
    if ref in _P_NAME_REFS:
        return 1 <= len(toks) <= 4
    # שם
    return all(_is_gematria(t) or _bare(t) in _REF_TOKENS - {"שם"} for t in toks)


def ocr_paren_vav(line: str, log: list | None = None) -> str:
    """P — "ודף כג.)" → "(דף כג.)": ו' שהיא בעצם "(" שנקרא לא נכון."""
    if ")" not in line or "ו" not in line:
        return line
    t = _mask_tags(line)
    by_close: dict = {}
    for m in _P_REF_RE.finditer(t):
        depth = 0
        for ch in t[:m.start()]:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth:
                depth -= 1
        if depth:
            continue
        # "זבחים דף י"ב ודף ל"ג)" — ו' החיבור בין שתי הפניות, לא סוגר
        prev = t[:m.start()].replace("\0", " ").split()
        if prev and (_bare(prev[-1]) in ("עא", "עב") or (
                len(prev) >= 2 and _bare(prev[-2]) in _P_REF_BARE
                and _is_gematria(prev[-1]))):
            continue
        rest = t[m.end():]
        k = re.search(r"[()]", rest)
        if not k or k.group() != ")":
            continue
        if _p_seg_ok(m.group("ref"), rest[:k.start()]):
            by_close.setdefault(m.end() + k.start(), []).append(m.start())
    edits = [(v[0], v[0] + 1, "(") for v in by_close.values() if len(v) == 1]
    return _apply_edits(line, edits, log)


# --- S: אות סופית באמצע מילה ---------------------------------------------------
#
# "דאםור" → "דאסור", "ןאם" → "ואם", "המיםשל" → "המים של". מתקן רק כשזה מוכח
# ממילון השכיחות (dicta_word_freq.tsv.gz — מילים מהספרייה הנארזת, ≥3 מופעים):
# המילה המקורית אינה מוכרת, והמועמד הטוב ביותר (החלפה בצורה הרגילה: ם→ס/מ,
# ן→ו/נ, ך→כ, ף→פ, ץ→צ; או פיצול אחרי האות הסופית) שכיח (≥100) ועדיף פי 10
# לפחות על השני. פיצול לא יוצר חלק של אות אחת. "לכןף" (לכן + ף) — סימן
# הערה דבוק למילה, לא טעות אות — לא נוגעים.

WORD_FREQ_FILE = Path(__file__).with_name("dicta_word_freq.tsv.gz")
_S_NONFINAL = {"ם": "סמ", "ן": "ונ", "ך": "כ", "ף": "פ", "ץ": "צ"}
_S_TOKEN_RE = re.compile(
    r"(?<![\w" + _QALL + r"\-־" + _NIKUD_CH + r"])[א-ת]*[ךםןףץ][א-ת]+(?![\w"
    + _QALL + r"\-־" + _NIKUD_CH + r"])")
_S_GLUE_RE = re.compile(r"[\w" + _QALL + r"\-־" + _NIKUD_CH + r"]")
_S_MIN_FREQ = 100        # מועמד החלפה: ≥100 מופעים ("ץמות" → "צמות" 21 — לא)
_S_MIN_SPLIT = 500       # פיצול: כל חלק ≥500 ("יהםחתה" ≠ "יהם חתה")…
_S_RATIO = 10
_S_KNOWN_ABS = 20        # מילה עם ≥20 מופעים במילון נחשבת מוכרת
_S_KNOWN_RATIO = 1000    # …או ≥ 1/1000 משכיחות המועמד
_word_freq_cache: dict | None = None
_LFS_POINTER_MAGIC = b"version https://git-lfs"


def load_word_freq(path: Path | None = None) -> dict:
    """טוען (פעם אחת) את מילון השכיחות: word\\tcount בכל שורה, gzip."""
    global _word_freq_cache
    if path is None and _word_freq_cache is not None:
        return _word_freq_cache
    import gzip
    p = Path(path) if path else WORD_FREQ_FILE
    d: dict = {}
    if p.exists():
        with open(p, "rb") as raw:
            if raw.read(len(_LFS_POINTER_MAGIC)) == _LFS_POINTER_MAGIC:
                # checkout עם lfs: false מביא את קובץ המצביע במקום המילון; מילון ריק היה
                # מכבה את כלל S בשקט ומשנה את פלט ההמרה — עדיף להיכשל בקול.
                raise RuntimeError(
                    f"{p} הוא קובץ מצביע של git-lfs ולא מילון gzip "
                    "(ר' .gitattributes — הקובץ אמור להישמר כ-blob רגיל)")
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for ln in f:
                w, _, c = ln.rstrip("\n").partition("\t")
                if c:
                    d[w] = int(c)
    if path is None:
        _word_freq_cache = d
    return d


# קריאות מתחרות — לא מתקנים אליהן, אבל אם אחת מהן סבירה ("ןכר": נכר / זכר,
# "מםני": ממני / מפני) התיקון אינו מוכח.
_S_RIVALS = {"ם": "סמפט", "ן": "ונזי", "ך": "כרד", "ף": "פק", "ץ": "צ"}
# חלק של שתי אותיות אחרי נקודת הפיצול — רק מילה נפוצה ("מן כה", "דרים יח" — לא)
_S_TWO_LETTER_WORDS = set(
    "אז כן מן לא אם זה של על גם כי אך רק אף הן הם לו לי לך לן בו בה בי מה כל עם את או אל"
    " זו יש אי די הא לה מת חד בא".split())


def _s_options(w: str, table: dict | None = None) -> list:
    table = table or _S_NONFINAL
    pos = [i for i, ch in enumerate(w[:-1]) if ch in _S_NONFINAL]
    if not pos or len(pos) > 2:
        return []
    import itertools
    res = []
    for combo in itertools.product(*[list(table[w[i]]) + [" "] for i in pos]):
        cur = []
        for i, ch in enumerate(w):
            if i in pos:
                x = combo[pos.index(i)]
                cur.append(ch + " " if x == " " else x)
            else:
                cur.append(ch)
        res.append("".join(cur))
    return res


def best_final_letter_fix(w: str, freq: dict) -> str | None:
    """המועמד המוכח ל־w (מילה עם אות סופית באמצע), או None."""
    def score(c):
        parts = c.split(" ")
        if any(len(p) < 2 for p in parts):
            return None
        sc = min(freq.get(p, 0) for p in parts)
        if len(parts) > 1 and (sc < _S_MIN_SPLIT or any(
                len(p) == 2 and p not in _S_TWO_LETTER_WORDS for p in parts[1:])):
            return None  # "בגיטןין" ≠ "בגיטן ין", "אונסיםילא" ≠ "אונסים ילא"
        return sc

    opts = []
    for c in _s_options(w):
        sc = score(c)
        if sc is not None:
            opts.append((sc, c))
    if not opts:
        return None
    opts.sort(reverse=True)
    best, cand = opts[0]
    # "לכןף" / "תמןת" / "דןי": קידומת מוכרת + אות אחת — כנראה סימן דבוק
    # (אבל "משןם": "משן" נדיר לעומת "משום")
    pre = freq.get(w[:-1], 0)
    if w[-2] in _S_NONFINAL and pre >= 50 and pre * _S_RATIO > best:
        return None
    orig = freq.get(w, 0)
    if best < _S_MIN_FREQ:
        return None
    if orig >= _S_KNOWN_ABS or orig * _S_KNOWN_RATIO > best:
        return None
    for c in _s_options(w, _S_RIVALS):
        sc = score(c)
        if c != cand and sc is not None and sc * _S_RATIO > best:
            return None
    return cand


def ocr_final_letters(line: str, log: list | None = None,
                      freq: dict | None = None) -> str:
    """S — אות סופית באמצע מילה, רק כשהתיקון מוכח ממילון השכיחות."""
    t = _mask_tags(line)
    ms = list(_S_TOKEN_RE.finditer(t))
    if not ms:
        return line
    if freq is None:
        freq = load_word_freq()
    if not freq:
        return line
    edits = []
    for m in ms:
        # תג צמוד מותר רק כגבול מילה: "<b>סןף</b>" כן, "דא<b>םור</b>" לא
        before = t[:m.start()].rstrip("\0")[-1:]
        after = t[m.end():].lstrip("\0")[:1]
        if (before and _S_GLUE_RE.match(before)) or (after and _S_GLUE_RE.match(after)):
            continue
        fix = best_final_letter_fix(m.group(), freq)
        if fix:
            edits.append((m.start(), m.end(), fix))
    return _apply_edits(line, edits, log)


# --- R: רמב"מ → רמב"ם ----------------------------------------------------------

_R_RE = re.compile(r"(?<![א-ת" + _QALL + r"])((?:[ובדלהכשמ]{0,3})רמב[" + _Q2
                   + r"])מ(?![א-ת" + _QALL + _NIKUD_CH + r"])")


def ocr_rambam(line: str, log: list | None = None) -> str:
    """R — "הרמב"מ" → "הרמב"ם" (גם עם ״)."""
    if "רמב" not in line:
        return line
    t = _mask_tags(line)
    edits = [(m.end() - 1, m.end(), "ם") for m in _R_RE.finditer(t)]
    return _apply_edits(line, edits, log)


# --- T: תוס → תוס' -------------------------------------------------------------
#
# "התוס ד"ה" → "התוס' ד"ה". רק עם קידומת (ו)(ב/ד/ל/כ/מ/ש)(ה) — לא "ביתוס"
# (בייתוסים), לא "אל תוס" (פסוק), לא כשכבר יש גרש/גרשיים (גם "תוס '" עם רווח
# או "תוס.'"). הגרש לפי מה שנפוץ בשורה (' או ׳).

_T_RE = re.compile(r"(?<![\w" + _QALL + r"\-־" + _NIKUD_CH + r"])((?:ו?[בדלכמש]?ה?)תוס)(?![\w"
                   + _QALL + r"\-־" + _NIKUD_CH + r"])")
_T_PREV_BLOCK = {"אל", "לא", "ואל", "ולא"}


def ocr_tosafot(line: str, log: list | None = None) -> str:
    """T — "תוס"/"התוס"/"ובתוס" בלי גרש (קיצור של תוספות) → עם גרש."""
    if "תוס" not in line:
        return line
    t = _mask_tags(line)
    geresh = "׳" if line.count("׳") > line.count("'") else "'"
    edits = []
    for m in _T_RE.finditer(t):
        after = t[m.end():].replace("\0", "")
        if re.match(r"\s*[" + _QALL + r"]|\.[" + _QALL + r"]", after):
            continue
        prev = t[:m.start()].replace("\0", " ").split()
        if prev and prev[-1] in _T_PREV_BLOCK:
            continue
        edits.append((m.end(), m.end(), geresh))
    return _apply_edits(line, edits, log)


ocr_paren_vav.rule_name = "P"
ocr_final_letters.rule_name = "S"
ocr_rambam.rule_name = "R"
ocr_tosafot.rule_name = "T"
OCR_RULES = [ocr_paren_vav, ocr_final_letters, ocr_rambam, ocr_tosafot]
OCR_RULE_ALIASES = {"PAREN": "P", "FINALS": "S", "RAMBAM": "R", "TOSAFOT": "T"}


def apply_ocr_rules(line: str, rules=None, log: list | None = None) -> str:
    """מריץ את כללי ה־OCR על שורה אחת. log מקבל (rule, עמדה, ישן, חדש)."""
    for fn in (OCR_RULES if rules is None else rules):
        sub: list = []
        line = fn(line, sub)
        if log is not None:
            log.extend((fn.rule_name,) + e for e in sub)
    return line


def _ocr_text_rule(fn, key: str):
    def rule(text: str, report: FileReport) -> str:
        lines = text.split("\n")
        n = 0
        for i, ln in enumerate(lines):
            if ln.startswith("<h1>"):
                continue  # שורת שם הספר — מתאימה לשם הקובץ
            sub: list = []
            new = fn(ln, sub)
            if sub:
                lines[i] = new
                n += len(sub)
        if n:
            _bump(report, key, n)
            report.changed = True
            return "\n".join(lines)
        return text
    rule.__name__ = "fix_" + fn.__name__
    return rule


fix_p_paren_vav = _ocr_text_rule(ocr_paren_vav, "P_vav_to_paren")
fix_s_final_letters = _ocr_text_rule(ocr_final_letters, "S_final_letter_fixed")
fix_r_rambam = _ocr_text_rule(ocr_rambam, "R_rambam_fixed")
fix_t_tosafot = _ocr_text_rule(ocr_tosafot, "T_tosafot_geresh")


def build_word_freq(repo_root: Path, out: Path = WORD_FREQ_FILE,
                    min_count: int = 3) -> int:
    """בונה את מילון השכיחות מכל BOOK_ROOTS (manual_links_packaging.py).

    מילה = רצף אותיות עבריות בלי ניקוד/טעמים, לא צמוד לגרש/גרשיים (כך
    ש"תוס'" אינו נספר כ"תוס"). מחזיר את מספר המילים שנשמרו.
    """
    import collections
    import gzip
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mlp", Path(repo_root) / "manual_links_packaging.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    marks = re.compile("[֑-ׇֽֿׁׂׅׄ]")
    seps = re.compile("[־׀׃׆]")
    tok = re.compile("(?<![א-ת" + _QALL + "])[א-ת]+(?![א-ת" + _QALL + "])")
    cnt: collections.Counter = collections.Counter()
    for root in mod.BOOK_ROOTS:
        for f in sorted((Path(repo_root) / root).rglob("*.txt")):
            t = f.read_text(encoding="utf-8", errors="replace")
            cnt.update(tok.findall(seps.sub(" ", marks.sub("", _TAG_RE.sub(" ", t)))))
    items = sorted(((w, c) for w, c in cnt.items() if c >= min_count),
                   key=lambda x: (-x[1], x[0]))
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as f:
        for w, c in items:
            f.write(f"{w}\t{c}\n")
    return len(items)


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

PIPELINE = [
    ("G", fix_g_normalize),
    ("E", fix_e_midword_bold),
    ("H", fix_h_fake_bold_pages),
    ("F", fix_f_orphan_ayin),
    ("P", fix_p_paren_vav),
    ("S", fix_s_final_letters),
    ("R", fix_r_rambam),
    ("T", fix_t_tosafot),
    ("B", fix_b_merge_bold_continuations),
    ("M", fix_m_merge_bold_runs),
]
DEFAULT_DISABLED = {"B", "H"}


def clean_text(text: str, skip: set[str] | None = None,
               report: FileReport | None = None,
               enable: set[str] | None = None,
               only: set[str] | None = None) -> tuple[str, FileReport]:
    """מריץ את הכללים. ברירת מחדל: G,E,F,P,S,R,T,M (B,H כבויים — `enable` מדליק)."""
    if report is None:
        report = FileReport(file="<memory>")
    skip = set(skip or ())
    active = {n for n, _ in PIPELINE} - DEFAULT_DISABLED
    active |= set(enable or ())
    if only:
        active = set(only)
    active -= skip
    for name, fn in PIPELINE:
        if name not in active:
            report.skipped.append(name)
            continue
        text = fn(text, report)
    # M יכול ליצור שורת ע"א/ע"ב יתומה חדשה (<b>ע"א</b><b>.</b> → <b>ע"א.</b>) ש־F לא
    # ראה — חוזרים על F ואז M עד נקודת שבת, כדי שהרצה שנייה לא תשנה דבר.
    if "F" in active and "M" in active:
        for _ in range(5):
            before = text
            text = fix_m_merge_bold_runs(fix_f_orphan_ayin(text, report), report)
            if text == before:
                break
    return text, report


def process_file(path: Path, skip: set[str], dry_run: bool,
                 enable: set[str] | None = None,
                 only: set[str] | None = None) -> FileReport:
    report = FileReport(file=str(path))
    if not path.exists():
        report.error = f"הקובץ לא נמצא: {path}"
        return report
    if path.suffix.lower() != ".txt":
        report.error = "סוג הקובץ אינו נתמך - נדרש .txt"
        return report
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.error = f"קריאה נכשלה: {exc}"
        return report
    cleaned, _ = clean_text(original, skip=skip, report=report,
                            enable=enable, only=only)
    if cleaned != original and not dry_run:
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(cleaned)
        except OSError as exc:
            report.error = f"כתיבה נכשלה: {exc}"
    return report


def _format_human(report: FileReport) -> str:
    if report.error:
        return f"[שגיאה] {report.file} :: {report.error}"
    if not report.changed:
        return f"[ללא שינוי] {report.file}"
    parts = [f"{k}={v}" for k, v in sorted(report.counts.items()) if v]
    return f"[נוקה] {report.file} :: " + ", ".join(parts)


def _letters(s: str) -> set[str]:
    out = set()
    for x in s.split(","):
        x = x.strip().upper()
        if x == "OCR":
            out |= {fn.rule_name for fn in OCR_RULES}
        elif x:
            out.add(OCR_RULE_ALIASES.get(x, x))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ניקוי דטרמיניסטי לקבצי TXT של דיקטה.")
    p.add_argument("files", nargs="*", help="קבצי TXT לניקוי")
    p.add_argument("--dir", help="ספרייה — מעבד רקורסיבית את כל הקבצים בה")
    p.add_argument("--glob", default="*.txt")
    p.add_argument("--skip", default="",
                   help="כללים לדילוג (B,E,F,G,H,M,P,S,R,T; OCR = P,S,R,T)")
    p.add_argument("--enable", default="", help="הדלקת כללים כבויים (B,H)")
    p.add_argument("--only", default="",
                   help="להריץ רק את הכללים האלה (למשל M, או S / FINALS, או OCR)")
    p.add_argument("--build-word-freq", metavar="REPO_ROOT",
                   help="בנייה מחדש של dicta_word_freq.tsv.gz מ־BOOK_ROOTS ויציאה")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    if args.build_word_freq:
        n = build_word_freq(Path(args.build_word_freq))
        sys.stderr.write(f"נכתבו {n} מילים ל־{WORD_FREQ_FILE}\n")
        return 0

    targets = [Path(f) for f in args.files]
    if args.dir:
        d = Path(args.dir)
        if not d.exists():
            sys.stderr.write(f"שגיאה: הספרייה לא קיימת: {d}\n")
            return 2
        targets.extend(sorted(d.rglob(args.glob)))
    if not targets:
        sys.stderr.write("שגיאה: לא צוינו קבצים. השתמש ב-FILE או --dir\n")
        return 2
    known = {n for n, _ in PIPELINE}
    skip, enable, only = _letters(args.skip), _letters(args.enable), _letters(args.only)
    unknown = (skip | enable | only) - known
    if unknown:
        sys.stderr.write(f"שגיאה: כלל לא מוכר: {','.join(sorted(unknown))}\n")
        return 2
    reports = [process_file(t, skip, args.dry_run, enable, only or None) for t in targets]
    if args.json:
        print(json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2))
    else:
        for r in reports:
            sys.stderr.write(_format_human(r) + "\n")
    return 0 if all(r.error is None for r in reports) else 2


if __name__ == "__main__":
    sys.exit(main())
