#!/usr/bin/env python3
"""הר שפר (מהדורת תשפ"ה) — PDF -> מבנה ביניים (events) לפי גופן/גודל/מיקום.

הטקסט וסדר הפיסוק מגיעים מ-poppler (pdftotext -bbox), הסגנון (בולד/קטן/עילי) מ-mupdf.
ראו README.md.

פלט: JSON של רשימת אירועים בסדר קריאה:
  {"k":"h","lvl":..,"runs":[..],"pg":..}     כותרת (lvl לוגי: 'part'/'chap'/'topic'/'sub')
  {"k":"daf","text":..}
  {"k":"p","runs":[[text,style]..],"pg":..}  פסקה (style: b/s/sup)
  {"k":"note","label":..,"runs":..,"pg":..}  הערה (אחרי איחוד שבירות עמוד)
"""
import json, re, sys, collections
import pymupdf, html, subprocess, os

if len(sys.argv) < 3:
    raise SystemExit("usage: extract_pdf.py <pdf> <events.json>")
PDF = sys.argv[1]
OUT = sys.argv[2]

BIDI = re.compile('[‎‏‪-‮⁦-⁩﻿]')
HEB = re.compile('[א-ת]')
GUTTER = 268.0          # אמצע העמוד (עמודות)
HDR_Y = 92.0            # מתחת לכותרת העליונה
FULL_TOL = 4.0          # שורה "מלאה" = x0 עד כך מקצה העמודה

# טווחי עמודים (1-based) לפי תפקיד
# עמודים שאינם נכנסים לספר: כריכה/שער/הקדשה (1, 5), תולדות חיי רבנו (11-18), תוכן עניינים, תמונות,
# דפי הפרדה ועמודים ריקים. השער, ההקדשה והתולדות הוסרו לבקשת המשתמש (2026-10-08).
SKIP = {1, 2, 3, 4, 5, 6, 7, 8, 19, 20, 95, 96, 126, 127, 128, 183, 184, 186} | set(range(11, 19))
FRONT = {}


BBOX = os.path.join(os.path.dirname(os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else ".")), "bbox.html")
_PW = None
HEBR = re.compile("[\u05d0-\u05ea]")
LTRTOK = re.compile("[0-9A-Za-z]")
MANUAL_TOKENS = []
UNASSIGNED = {}   # טוקנים עם ספרות/לטינית — דורשים בדיקה ידנית


def poppler_pages():
    global _PW
    if _PW is None:
        if not os.path.exists(BBOX):
            subprocess.run(["pdftotext", "-bbox", PDF, BBOX], check=True)
        src = open(BBOX, encoding="utf-8").read()
        _PW = []
        for pg in src.split("<page ")[1:]:
            ws = []
            for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', pg):
                x0, y0, x1, y1 = map(float, m.groups()[:4])
                t = BIDI.sub("", html.unescape(m.group(5)))
                ws.append((x0, y0, x1, y1, t))
            _PW.append(ws)
    return _PW


NUMRUN = re.compile(r"[0-9A-Za-z]+(?:[-.,/][0-9A-Za-z]+)*")


def logical_word(t):
    """poppler נותן מילים בסדר חזותי (שמאל->ימין). לוגי (RTL): היפוך סדר הריצות,
    כשריצות ספרות/לטינית נשארות כמות שהן והשאר מתהפך תו-תו."""
    if not LTRTOK.search(t):
        return t[::-1]
    parts, pos = [], 0
    for m in NUMRUN.finditer(t):
        if m.start() > pos:
            parts.append((t[pos:m.start()], False))
        parts.append((m.group(0), True))
        pos = m.end()
    if pos < len(t):
        parts.append((t[pos:], False))
    return "".join(x if keep else x[::-1] for x, keep in reversed(parts))


class Span:
    __slots__ = ("t", "x0", "x1", "y0", "y1", "base", "size", "font", "flags")

    def __init__(self, s):
        self.t = BIDI.sub("", s["text"])
        self.x0, self.y0, self.x1, self.y1 = s["bbox"]
        self.base = s["origin"][1]
        self.size = s["size"]
        self.font = s["font"]
        self.flags = s["flags"]

    @property
    def sup(self):
        return bool(self.flags & 1)

    @property
    def bold(self):
        return bool(self.flags & 16) or "Bold" in self.font

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2


class VLine:
    def __init__(self, spans):
        self.spans = sorted(spans, key=lambda s: -s.x1)   # RTL: מימין לשמאל
        self.x0 = min(s.x0 for s in spans)
        self.x1 = max(s.x1 for s in spans)
        self.y0 = min(s.y0 for s in spans)
        self.y1 = max(s.y1 for s in spans)
        bases = [s.base for s in spans if not s.sup] or [s.base for s in spans]
        self.base = sorted(bases)[len(bases) // 2]

    @property
    def text(self):
        return "".join(s.t for s in self.spans)

    def col(self):
        if self.x0 >= GUTTER:
            return "R"
        if self.x1 <= GUTTER:
            return "L"
        return "W"


SEG_GAP = 12.0     # רווח אופקי שמפצל שורה לשני קטעים (עמודות/חתימות)
SPACE_GAP = 1.0    # רווח בין מילים סמוכות שמצדיק רווח


def make_span(t, x0, x1, y0, y1, base, size, font, flags):
    sp = Span.__new__(Span)
    sp.t, sp.x0, sp.x1, sp.y0, sp.y1 = t, x0, x1, y0, y1
    sp.base, sp.size, sp.font, sp.flags = base, size, font, flags
    return sp


def build_lines(page, pno):
    """שורות חזותיות ברמת המילה: טקסט וסדר מ-poppler (פיסוק נכון), סגנון מהתו הקרוב ב-mupdf."""
    raw = page.get_text("rawdict")
    cells = []       # (x0,x1,y0,y1, size, font, flags, lbase)
    for b in raw["blocks"]:
        for l in b.get("lines", []):
            sps = [sp for sp in l["spans"] if sp["chars"]]
            if not sps:
                continue
            nb = [sp["origin"][1] for sp in sps if not (sp["flags"] & 1)] or [sp["origin"][1] for sp in sps]
            lb = sorted(nb)[len(nb) // 2]
            for sp in sps:
                for c in sp["chars"]:
                    if c["c"].strip() == "":
                        continue
                    x0, y0, x1, y1 = c["bbox"]
                    cells.append((x0, x1, y0, y1, sp["size"], sp["font"], sp["flags"], lb))
    # אינדקס גס לפי y
    words = []
    unassigned = []
    for (wx0, wy0, wx1, wy1, t) in poppler_pages()[pno - 1]:
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        best, bd = None, 1e9
        for c in cells:
            if c[2] - 0.5 <= cy <= c[3] + 0.5 or (c[2] <= wy1 and c[3] >= wy0 and min(c[3], wy1) - max(c[2], wy0) > 0.3 * (wy1 - wy0)):
                d = 0.0 if c[0] - 0.4 <= cx <= c[1] + 0.4 else min(abs(cx - c[0]), abs(cx - c[1]))
                d += 0.01 * abs(cy - (c[2] + c[3]) / 2)
                if d < bd:
                    bd, best = d, c
        if best is None or bd > 4.0:
            unassigned.append((wx0, wy0, wx1, wy1, t))
            continue
        words.append(dict(x0=wx0, x1=wx1, y0=wy0, y1=wy1, t=t, size=best[4], font=best[5], flags=best[6], lb=best[7]))
    UNASSIGNED[pno] = unassigned
    for w in words:
        t = w["t"]
        issup = bool(w["flags"] & 1)
        if issup or ("Medium" in w["font"] and w["size"] > 8.9 and re.fullmatch(r"[\u05d0-\u05ea]{1,3}", t)):
            lt = t
        else:
            lt = logical_word(t)
        if LTRTOK.search(t):
            MANUAL_TOKENS.append((pno, round(w["y0"]), t, lt))
        w["lt"] = lt
    # אשכול לשורות לפי קו בסיס
    words.sort(key=lambda w: (w["lb"], -w["x1"]))
    clusters = []
    for w in words:
        if clusters and abs(clusters[-1][0] - w["lb"]) <= 2.6:
            clusters[-1][1].append(w)
        else:
            clusters.append([w["lb"], [w]])
    out = []
    for lb, ws in clusters:
        ws.sort(key=lambda w: -(w["x0"] + w["x1"]) / 2)
        segs = [[ws[0]]]
        two = classify(pno) == "two"
        for w in ws[1:]:
            prevw = segs[-1][-1]
            gap = prevw["x0"] - w["x1"]
            if two:
                split = (prevw["x0"] + prevw["x1"]) / 2 > GUTTER >= (w["x0"] + w["x1"]) / 2 and gap >= 8.0   # הפער חוצה את המרווח בין העמודות
            else:
                split = gap >= 45.0                                             # שורת חתימה
            if split:
                segs.append([w])
            else:
                segs[-1].append(w)
        for seg in segs:
            spans = []
            prev = None
            for w in seg:
                lead = ""
                if prev is not None and (prev["x0"] - w["x1"]) > SPACE_GAP:
                    lead = " "
                sty = (w["flags"] & 1, bool(w["flags"] & 16) or "Bold" in w["font"], round(w["size"], 1), w["font"])
                if spans and spans[-1]["sty"] == sty:
                    spans[-1]["t"] += lead + w["lt"]
                    spans[-1]["x0"] = min(spans[-1]["x0"], w["x0"])
                    spans[-1]["y0"] = min(spans[-1]["y0"], w["y0"]); spans[-1]["y1"] = max(spans[-1]["y1"], w["y1"])
                else:
                    spans.append(dict(sty=sty, t=lead + w["lt"], x0=w["x0"], x1=w["x1"], y0=w["y0"], y1=w["y1"],
                                      size=w["size"], font=w["font"], flags=w["flags"]))
                prev = w
            sl = [make_span(sp["t"], sp["x0"], sp["x1"], sp["y0"], sp["y1"], lb, sp["size"], sp["font"], sp["flags"]) for sp in spans]
            out.append(VLine(sl))
    return [v for v in out if v.text.strip() != ""]


def sep_y(page):
    """y של קו ההפרדה לפני ההערות (הקו השני של הזוג), או None."""
    ys = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if abs(r.x0 - 86) < 1.5 and abs(r.x1 - 454) < 1.5 and r.height < 1.5 and r.y0 > 100:
            ys.append(r.y0)
    return max(ys) if ys else None


def runs_of(spans, base_size):
    """spans (בסדר חזותי ימין->שמאל) -> [[text, style]], style: '' | 'b' | 's' | 'sup'"""
    out = []
    prev = None
    for s in spans:
        t = s.t
        if s.sup:
            st = "sup"
            t = t.strip()
        else:
            st = "b" if s.bold else ("s" if s.size < base_size - 1.4 else "")
        # רווח בין ספאנים צמודים שלא מופרדים ברווח
        if prev is not None and not s.sup and not prev.sup:
            gap = prev.x0 - s.x1
            if gap > 0.9 and out and not out[-1][0].endswith((" ", "\u00a0")) and not t.startswith((" ", "\u00a0")):
                out[-1][0] += " "
        if out and out[-1][1] == st and st != "sup":
            out[-1][0] += t
        else:
            out.append([t, st])
        prev = s
    return out


def classify(page_no):
    if page_no in FRONT:
        return FRONT[page_no]
    if page_no in SKIP:
        return "skip"
    if 9 <= page_no <= 10:
        return "single"
    if page_no == 185:
        return "single"
    if page_no == 308:
        return "appendix"
    return "two"


def wide_title_kind(v, mode):
    """כותרת: שורה רחבה שכולה בולד (פרט לסימן)."""
    sp = [s for s in v.spans if not s.sup and s.t.strip()]
    if not sp or not all(s.bold for s in sp):
        return None
    size = max(s.size for s in sp)
    if mode == "two" and v.col() != "W":
        return None
    if mode in ("single", "appendix") and size < 12.0:
        return None
    if mode == "single" and size < 17.0:
        return None
    if size >= 17.0:
        return "chap"
    if size >= 14.5:
        return "topic"
    if size >= 12.0:
        return "sub"
    return None


def parse_page(doc, pno):
    page = doc[pno - 1]
    mode = classify(pno)
    if mode == "skip":
        return None
    lines = build_lines(page, pno)
    sy = sep_y(page)
    if pno == 185:
        sy = 583.0
    body, notes = [], []
    for v in lines:
        if v.y0 < HDR_Y:
            continue
        if sy is not None and v.y0 >= sy - 2:
            notes.append(v)
        else:
            body.append(v)
    return dict(pno=pno, mode=mode, body=body, notes=notes)


def order_body(body, mode):
    """סדר קריאה: פסים (bands) מופרדים בשורות רחבות; בכל פס ימין ואז שמאל."""
    wides = sorted([v for v in body if v.col() == "W"], key=lambda v: v.base)
    cols = [v for v in body if v.col() != "W"]
    res = []
    bands = [[] for _ in range(len(wides) + 1)]
    for v in cols:
        k = sum(1 for w in wides if w.base < v.base - 3)
        bands[k].append(v)
    for k in range(len(wides) + 1):
        right = sorted([v for v in bands[k] if v.col() == "R"], key=lambda v: v.base)
        left = sorted([v for v in bands[k] if v.col() == "L"], key=lambda v: v.base)
        res.extend(right); res.extend(left)
        if k < len(wides):
            res.append(wides[k])
    return res


def has_lead(v):
    """שורה שפותחת בולד גדול (>=13.5) = תחילת פסקה."""
    sp = [s for s in v.spans if s.t.strip()]
    s = sp[0]
    return s.bold and s.size >= 13.5 and not s.sup


def is_short(v, single):
    left = 84.0 if v.col() in ("L", "W") else 276.0
    return v.x0 > left + FULL_TOL


def main():
    doc = pymupdf.open(PDF)
    events = []
    cur = None        # פסקה פתוחה
    pending_notes = []   # הערות של העמוד הנוכחי
    last_note = None

    def flush():
        nonlocal cur
        if cur is not None:
            runs = cur["runs"]
            # נקה רווחים כפולים
            events.append(dict(k="p", runs=runs, pg=cur["pg"], sub=bool(cur.get("sub"))))
            cur = None

    def add_line_to(cur_runs, v, base_size):
        rr = runs_of(v.spans, base_size)
        if cur_runs and cur_runs[-1][1] != "sup":
            last = cur_runs[-1]
        # רווח בין שורות
        if cur_runs:
            if cur_runs[-1][0].endswith(" ") or (rr and rr[0][0].startswith(" ")):
                pass
            elif cur_runs[-1][1] == "sup":
                cur_runs.append([" ", ""])
            else:
                cur_runs[-1][0] += " "
        for r in rr:
            cur_runs.append(r)

    for pno in range(1, len(doc) + 1):
        pg = parse_page(doc, pno)
        if pg is None:
            continue
        mode = pg["mode"]
        if mode in ("title", "dedic"):
            lines = sorted(pg["body"] + pg["notes"], key=lambda v: v.base)
            flush()
            events.append(dict(k="front", kind=mode, pg=pno,
                               lines=[runs_of(v.spans, 13.0) for v in lines]))
            continue
        ordered = order_body(pg["body"], mode)
        single = mode in ("single", "appendix")
        base_size = 13.0
        for v in ordered:
            t = v.text.strip()
            tk = wide_title_kind(v, mode)
            sp0 = v.spans[0]
            if tk:
                flush()
                rr = runs_of(v.spans, base_size)
                events.append(dict(k="h", kind=tk, runs=rr, pg=pno, y=v.base))
                continue
            if any("Thin" in s.font for s in v.spans) and re.match(r"^\s*דף\s", t):
                flush()
                events.append(dict(k="daf", text=t, pg=pno))
                continue
            if v.text.strip() in ("·", "•"):
                flush()
                continue
            # גוף
            sp_ns = [x for x in v.spans if not x.sup and x.t.strip()]
            is_sub = bool(sp_ns) and all(x.bold and x.size < 13.5 for x in sp_ns) and v.col() != "W" and not single
            if is_sub and cur is not None and cur.get("sub"):
                start_new = False
            elif cur is not None and cur.get("sub") != is_sub:
                start_new = True
            else:
                start_new = cur is None or has_lead(v)
                if cur is not None and cur.get("short"):
                    start_new = True
            if start_new:
                flush()
                cur = dict(runs=[], pg=pno, short=False, sub=is_sub)
            add_line_to(cur["runs"], v, base_size)
            cur["short"] = False if is_sub else is_short(v, single)
        # הערות
        nl = sorted(pg["notes"], key=lambda v: v.base)
        for v in nl:
            sp = [s for s in v.spans if s.t.strip()]
            lab = None
            for s in sp:
                if "Medium" in s.font and not s.sup and HEB.search(s.t) and re.fullmatch(r"\s*[א-ת]{1,3}\.?\s*", s.t) and s.size > 8.9:
                    lab = s.t.strip().rstrip(".")
                    break
            if lab is not None:
                # הסר את הספאן של התווית וניקוד מקדים
                rest = []
                seen = False
                for s in v.spans:
                    if s is None:
                        continue
                    if (not seen) and "Medium" in s.font and not s.sup and re.fullmatch(r"\s*[א-ת]{1,3}\.?\s*", s.t):
                        seen = True
                        continue
                    rest.append(s)
                # נקודה מקדימה / אחרי תווית
                # סדר ויזואלי: spans מימין לשמאל; ספאנים שלפני התווית (מימין) הם שוליים/נקודות בלבד
                before = []
                after = []
                lab_x = [s for s in v.spans if "Medium" in s.font and not s.sup and re.fullmatch(r"\s*[א-ת]{1,3}\.?\s*", s.t)][0]
                for s in rest:
                    (before if s.x1 > lab_x.x1 - 0.5 and s.cx > lab_x.cx else after).append(s)
                rr = runs_of(after, 11.0)
                if rr: rr[0][0] = re.sub(r"^[\s.]+", "", rr[0][0])
                events.append(dict(k="note", label=lab, pg=pno, runs=rr, before=[b.t for b in before], new=True, x0=v.x0))
            else:
                events.append(dict(k="note", label=None, pg=pno, runs=runs_of(sp, 11.0), new=False, x0=v.x0))
    flush()
    # איחוד כותרות שנשברו לשתי שורות
    merged = []
    for e in events:
        if (e["k"] == "h" and merged and merged[-1]["k"] == "h" and merged[-1]["pg"] == e["pg"]
                and merged[-1]["kind"] == e["kind"] and 0 < e["y"] - merged[-1]["y"] < 26):
            m = merged[-1]
            if m["runs"] and not m["runs"][-1][0].endswith(" "):
                m["runs"][-1][0] += " "
            m["runs"].extend(e["runs"]); m["y"] = e["y"]
        else:
            merged.append(e)
    events = merged
    json.dump(events, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("manual tokens:", MANUAL_TOKENS)
    un = {k: v for k, v in UNASSIGNED.items() if v and k not in SKIP}
    print("unassigned words (non-skipped pages):", sum(len(v) for v in un.values()), {k: [w[4] for w in v][:6] for k, v in list(un.items())[:10]})
    print("events:", len(events), collections.Counter(e["k"] for e in events))


if __name__ == "__main__":
    main()
