# -*- coding: utf-8 -*-
"""fetch_raw.py (tur_bareket) - הורדת ה-wikitext הגולמי של כל דפי "טור ברקת" לתיקיית raw/ (לצורך השוואה, לא להמרה).

אחרי שהרצת:  python -X utf8 ../ws_book.py --page "טור ברקת" --out <WORK>/out --plan-only
הדוח <WORK>/out/_report/טור ברקת.report.txt מכיל את תוכנית הדפים (שורות "[content] טור ברקת/<סימן>") ואת הדפים החסומים.
הסקריפט הזה קורא את הדוח, מוריד כל דף (דרך WikiClient של ws_book - עם אותו זיהוי חסימה) לקובץ raw/<כותרת עם __>.wiki,
וכותב raw_status.json: {status: {דף: ok|missing|blocked|failed}, blocked_known: [...]}.
חסימה נרשמת ואין לעקוף אותה. שימוש:  python -X utf8 fetch_raw.py <WORK> [--delay 0.5]
(ב-2026 הורדו 210 דפים מתוך 211 - 54 נחסמו בהרצת הרקע; raw_status.json שבתיקייה זו הוא התוצאה ההיא, לעיון.)
"""
import argparse, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.dont_write_bytecode = True
import ws_book as w

ap = argparse.ArgumentParser()
ap.add_argument("work")
ap.add_argument("--delay", type=float, default=0.5)
ap.add_argument("--page", default="טור ברקת")
a = ap.parse_args()
base = a.work
os.makedirs(os.path.join(base, "raw"), exist_ok=True)
rep = open(os.path.join(base, "out", "_report", a.page + ".report.txt"), encoding="utf-8").read()
blocked = set(re.findall(r"נחסם בנטפרי: (" + re.escape(a.page) + r"/\S+)", rep))
plan = re.findall(r"\[content\] (" + re.escape(a.page) + r"/\S+)", rep)
titles = [a.page] + plan
c = w.WikiClient(a.delay)
status = {}
for t in titles:
    pd = c.get_page(t)
    status[t] = pd.status
    if pd.status == "ok":
        fn = t.replace("/", "__") + ".wiki"
        open(os.path.join(base, "raw", fn), "w", encoding="utf-8").write(pd.text)
    elif pd.status == "blocked":
        blocked.add(t)
json.dump({"status": status, "blocked_known": sorted(blocked)}, open(os.path.join(base, "raw_status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("done", sum(1 for s in status.values() if s == "ok"), "ok of", len(status), "| blocked:", len(blocked))
