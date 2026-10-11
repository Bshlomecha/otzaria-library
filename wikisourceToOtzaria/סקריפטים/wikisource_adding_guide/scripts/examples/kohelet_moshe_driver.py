#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kohelet_moshe_driver.py - דוגמה: ספר שבנוי מדפים שטוחים (בלי "/") ותוכן עניינים ידני. נכתב עבור: קהלת משה.

הבעיה: "קהלת משה" (משה הכהן מטשודנוב, לבוב תקנ"ג; חידושי דרוש) אינו בנוי מתתי-דפים "קהלת משה/א" אלא מדפים
בשמות שטוחים: "קהלת משה שער הספר", "קהלת משה א" (דף חלק), "קהלת משה א א", "קהלת משה א ב" ... "קהלת משה ז יט".
ws_book.py מחפש תתי-דפים לפי "/" ולכן מוצא כמעט כלום ("נמצאו 1 תתי-דפים"). הפתרון: להחליף את build_plan של ws_book
בתוכנית משלנו (monkey-patch), ולהריץ את ws_book.main() כרגיל:

  * allpages על 'קהלת משה/' מוחלף כך שה-main נראה כבעל תת-דף מדומה (כדי להיכנס למצב chapters ולא single);
  * my_build_plan: שער הספר -> לכל חלק (א..ז) כותרת חלק + הדפים שלו לפי סדר הקישורים בדף החלק (LINK_RE), כולל
    קבוצות (חלק ז: "חידושים מהבעל שם טוב", "...מרבי העשיל מקראקא");
  * כותרת כל דף נלקחת מתווית הקישור בדף החלק; ההערות (<ref>) שבדף החלק נדבקות לכותרת;
  * סרגל הניווט {{סרגל ניווט|...}} ו-"== הערות שוליים == <references/>" בסוף כל דף מוסרים;
  * "קהלת משה ח" (שריד - קישורים אדומים בלבד) אינו נכלל בכוונה.

דפים שהם קישור אדום בדף החלק (לא קיימים בוויקיטקסט - "missing") ייכשלו את הריצה (קוד 4). ב-ACCEPT_MISSING למטה רשומים
הדפים שנקבע שהחסר הוא אמיתי (קהלת משה ה כ, ה כא, ה כב - ב-2026): הם מדולגים ונרשמים בדוח כמידע. בדוק מחדש שהם עדיין
חסרים בוויקיטקסט; דף שקיים אך נחסם (HTTP 418) *אינו* "חסר" - הוא ייכשל ויידרש לטפל בו.

הרצה (שם הקובץ בספרייה חייב להיות מבדיל - "קהלת משה" אחר כבר קיים בספרייה (דיקטה, משה אליקים בריעה, חסידות)):

    python -X utf8 examples/kohelet_moshe_driver.py --page "קהלת משה" --name "קהלת משה (משה הכהן)" \\
        --author "משה הכהן מטשודנוב" --out <תיקיית פלט> [--plan-only] [--delay 1]

(--author: בדוק את הצורה המקובלת ב-metadata.json; 'שם הספר' בקובץ ה-h1 יהיה "קהלת משה (משה הכהן)".)
הקובץ ws_book.py נטען מהתיקייה שמעל התיקייה הזו (scripts/).
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
SC = Path(__file__).resolve().parent.parent  # scripts/
spec = importlib.util.spec_from_file_location("ws_book", SC / "ws_book.py")
ws = importlib.util.module_from_spec(spec)
sys.modules["ws_book"] = ws
spec.loader.exec_module(ws)

MAIN = "קהלת משה"
PARTS = [
    ("א", "חלק א – חידושי רבי שמשון מאוסטרופולי"),
    ("ב", "חלק ב – חידושי רב האי גאון"),
    ("ג", "חלק ג – חידושי ר' יונתן מפראג (אייבשיץ)"),
    ("ד", "חלק ד – חידושי ר' משה נתן מגיד דק\"ק מאקוו"),
    ("ה", "חלק ה – חידושי הדרשן ר' משה כהן"),
    ("ו", "חלק ו – חידושי ר' יצחק מהמבורג"),
    ("ז", "חלק ז – חידושי גאונים שונים"),
]
GROUPS_Z = {"קהלת משה ז יז": "חידושים מהבעל שם טוב", "קהלת משה ז יח": "חידושים מרבי העשיל מקראקא"}
# קישורים אדומים אמיתיים (הדף לא קיים בוויקיטקסט). לבדוק מחדש בכל ריצה!
ACCEPT_MISSING = {"קהלת משה ה כ", "קהלת משה ה כא", "קהלת משה ה כב"}
NAV_RE = re.compile(r"^\s*\{\{סרגל ניווט\|[^{}]*\}\}[ \t]*\n?")
TAIL_RE = re.compile(r"\n*==\s*הערות שוליים\s*==\s*\n*<references\s*/>\s*$")
LINK_RE = re.compile(r"\[\[(קהלת משה [^|\]]+)\|([^\]]+)\]\]'*\s*(<ref>.*?</ref>)?", re.S)


def body_of(client, title, rep, demote=False):
    pd = ws.get_resolved(client, title, rep)
    if pd.status != "ok":
        if pd.status == "missing" and title in ACCEPT_MISSING:
            rep.info.append(f"דף שלא קיים בוויקיטקסט (קישור אדום) - מדולג: {title}")
            return None
        rep.failed.append((title, f"{pd.status} {pd.note}"))
        return None
    t = NAV_RE.sub("", pd.resolved)
    t = TAIL_RE.sub("", t)
    if demote:
        t = re.sub(r"(?m)^(=+)([^=\n].*?)(=+)[ \t]*$", lambda m: "=" + m.group(1) + m.group(2) + m.group(3) + "=", t)
    return t.strip("\n") + "\n"


def mkitem(title, seg, depth, text, kind="content"):
    it = ws.PlanItem(title, seg, depth, kind, "ok", resolved=text)
    it.own_heading_level = 2
    it.words = ws.count_words(text)
    return it


def my_build_plan(client, main_title, main_resolved, subpages, redirects, args, rep):
    items = []
    main_text = client.get_page(main_title).text
    part_refs = {}
    for ln in main_text.split("\n"):
        m = re.search(r"\[\[קהלת משה ([א-ת])\|", ln)
        r = re.search(r"<ref>.*?</ref>", ln)
        if m and r:
            part_refs[m.group(1)] = r.group(0)
    # שער הספר
    t = body_of(client, "קהלת משה שער הספר", rep, demote=True)
    if t is not None:
        items.append(mkitem("קהלת משה שער הספר", "שער הספר", 1, "==שער הספר==\n" + t))
    seen = {"קהלת משה שער הספר"}
    for letter, label in PARTS:
        ptitle = f"קהלת משה {letter}"
        ptext = client.get_page(ptitle).text
        items.append(mkitem(ptitle, label, 1, f"=={label}{part_refs.get(letter, '')}==\n", ))
        items[-1].words = 0
        seen.add(ptitle)
        # סדר העמודים לפי רשימת הקישורים בדף החלק
        in_group = False
        for m in LINK_RE.finditer(ptext):
            ctitle, clabel, ref = m.group(1), m.group(2).strip(), (m.group(3) or "")
            if not re.match(r"קהלת משה %s [א-ת]+$" % letter, ctitle):
                continue
            ref = re.sub(r"'''(</ref>)$", r"\1", ref)
            if ctitle in GROUPS_Z:
                g = GROUPS_Z[ctitle]
                items.append(mkitem(g + "(קבוצה)", g, 2, f"=={g}==\n"))
                items[-1].words = 0
                in_group = True
            depth = 3 if in_group else 2
            t = body_of(client, ctitle, rep)
            if t is None:
                continue
            items.append(mkitem(ctitle, clabel, depth, f"=={clabel}{ref}==\n" + t))
            seen.add(ctitle)
    # כיסוי: כל הדפים הממשיים בקידומת
    allp = client.real_allpages
    rep.info.append("דפי ויקיטקסט בקידומת 'קהלת משה' שלא נכללו בתוכנית: " + (", ".join(p for p in allp if p not in seen and not p.endswith("(הכל)")) or "אין"))
    return items


orig_allpages = ws.WikiClient.allpages


def fake_allpages(self, prefix, redirects_only=False):
    if prefix == MAIN + "/":
        return [] if redirects_only else [MAIN + "/__plan"]
    return orig_allpages(self, prefix, redirects_only)


ws.WikiClient.allpages = fake_allpages
ws.build_plan = my_build_plan

orig_init = ws.WikiClient.__init__


def init2(self, delay=0.25):
    orig_init(self, delay)
    self.real_allpages = None


ws.WikiClient.__init__ = init2
orig_get = ws.WikiClient.get_page


def get2(self, title):
    if self.real_allpages is None:
        self.real_allpages = orig_allpages(self, MAIN, False)
    return orig_get(self, title)


ws.WikiClient.get_page = get2
sys.exit(ws.main())
