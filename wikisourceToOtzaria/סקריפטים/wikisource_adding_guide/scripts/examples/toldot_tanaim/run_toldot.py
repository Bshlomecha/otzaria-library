# -*- coding: utf-8 -*-
"""run_toldot.py (toldot_tanaim) - מריץ ws_book.main() על "תולדות תנאים ואמוראים" עם cache מקומי והרחבת <pages>. טיוטה - נבדקה על מדגם.

מחליף את run_cached.py המקורי (שרק שירת דפים מה-cache) בשני דברים נוספים:
  1. כל דף ערך (תולדות תנאים ואמוראים/<אות>/<ערך>) עובר expand_pages: <pages index=.. from=.. to=.. onlysection=../> מוחלף בטקסט עמודי הסריקה
     (expand_pages_tag.py). עמוד סריקה שאינו ב-cache (pagens.json) נטען מהרשת באמצעות WikiClient של ws_book (עם אותו זיהוי חסימה), ונשמר ב-cache.
  2. מיפוי תבניות ברירת מחדל: "ספר חול" (תבנית ניווט) -> remove, "תותו\"א" (ניווט) -> remove. לבדוק בדוח "תבניות לא ממופות" ולהוסיף עם --template-map.

שימוש (מתוך התיקייה עם pages.json / titles.json / pagens.json - ראה prefetch.py ו-prefetch2.py):
    python -X utf8 run_toldot.py --page "תולדות תנאים ואמוראים" --out out --delay 1 [--letters צ,ק] [--plan-only]
  --letters  (דגל של הסקריפט הזה, לא של ws_book): מגביל לאותיות; ל"נבדק על מדגם" - מומלץ להתחיל באות קטנה (צ: ~10 ערכים).
  כל שאר הדגלים מועברים ל-ws_book. הקישורים האדומים (~36% מהערכים, דפים שלא קיימים) אינם כשל - הם פשוט אינם בתוכנית הדפים,
    ולכן --allow-partial אינו נדרש בגללם (הוא רק לדפים שנחסמו/נכשלו; חסימה = לא מכניסים ספר חלקי ללא אישור - ראה PROCESS.md). הספר חלקי
    בוויקיטקסט - המשתמש הורה במפורש להכניס גם חלקי (BLOCKED_BOOKS.md סעיף 5).
דגלים חשובים לפני ריצה מלאה:
  * ב-ws_book דפי האותיות ("תולדות תנאים ואמוראים/א") הם container (רשימת קישורים בלבד) ולכן הופכים לכותרת ברמה 2; כל ערך מביא כותרת משלו
    (==שם הערך== מתוך עמוד הסריקה). לוודא ברמות הכותרות (inspect_book.py --toc).
  * קישורים אדומים בדפי האותיות אינם מדווחים אוטומטית ב-ws_book (רק בדף הראשי) - ראה analyze_letters.py.
  * "הקדמות" (הקדמה/סימני הש"ס/מנין שטרות) ו"הערכים לפי אותיות" בדף הראשי: לבדוק --include-main (הדף הראשי כולל טבלאות קישורים בלבד - כנראה לא).
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SC = os.path.dirname(os.path.dirname(HERE))  # scripts/
sys.path.insert(0, SC)
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import ws_book as W
from expand_pages_tag import expand_pages

PFX = "תולדות תנאים ואמוראים/"
cache_path = os.path.join(os.getcwd(), "pages.json")
titles_path = os.path.join(os.getcwd(), "titles.json")
scan_path = os.path.join(os.getcwd(), "pagens.json")
cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
titles = json.load(open(titles_path, encoding="utf-8")) if os.path.exists(titles_path) else None
scans = json.load(open(scan_path, encoding="utf-8")) if os.path.exists(scan_path) else {}

# --- דגל של הסקריפט (לפני ws_book.main): --letters מסנן ב-allpages למטה ---
letters = None
argv = sys.argv[1:]
if "--letters" in argv:
    i = argv.index("--letters")
    letters = [x.strip() for x in argv[i + 1].split(",") if x.strip()]
    del argv[i:i + 2]
sys.argv = [sys.argv[0]] + argv

_client_ref = {}
orig_get = W.WikiClient.get_page
orig_all = W.WikiClient.allpages
orig_init = W.WikiClient.__init__
EXTRA_WARN = []


def init2(self, delay=0.25):
    orig_init(self, delay)
    _client_ref["c"] = self


W.WikiClient.__init__ = init2


def get_scan_page(index, n):
    """עמוד סריקה ממרחב 'עמוד:' - מה-cache, ואם אינו שם - מהרשת.

    לא משתמשים ב-WikiClient.get_page: הוא משווה את הגודל המוצהר (size) לתוכן שהתקבל, ובמרחב 'עמוד:' (תוכן ProofreadPage)
    ה-API מחזיר wikitext מומר בעוד size הוא של האחסון - ולכן כל עמוד היה מסומן 'mismatch' (נחשב חסר). לכן בקשה ישירה."""
    key = f"עמוד:{index}/{n}"
    if key in scans:
        return scans[key]["text"] if scans[key] else None
    c = _client_ref["c"]
    d = c._request({"action": "query", "prop": "revisions", "titles": key, "rvslots": "main", "rvprop": "content|size",
                    "format": "json", "formatversion": 2}, key)  # חסימה -> Blocked (מועבר הלאה ל-get_page)
    pg = d.get("query", {}).get("pages", [{}])[0]
    if pg.get("missing") or "revisions" not in pg:
        scans[key] = None
        return None
    rv = pg["revisions"][0]
    text = rv["slots"]["main"]["content"]
    scans[key] = {"text": text, "size": rv.get("size")}
    return text


def get_page(self, title):
    t = W.norm_title(title)
    if t in self.cache:
        return self.cache[t]
    if t.startswith(PFX) and t in cache:
        e = cache[t]
        if e is None:
            pd = W.PageData(t, "missing")
        else:
            text = e["text"]
            if e.get("size") is not None and len(text.encode("utf-8")) != e["size"]:
                pd = W.PageData(t, "mismatch", note="size mismatch")
            elif not text.strip():
                pd = W.PageData(t, "empty")
            else:
                try:
                    warns = []
                    text = text.replace("\r\n", "\n")
                    # תבנית הניווט {{ספר חול ...}} (רב-שורתית) מוסרת כאן: ב-ws_book leading_heading_level מזהה רק תבנית מוסרת בשורה אחת,
                    # ובלי זה הכותרת ==ערך== שמגיעה מעמוד הסריקה אינה נחשבת "ראשונה" והכלי מוסיף כותרת נוספת משם הדף (כפילות).
                    text = re.sub(r"\{\{\s*ספר חול\b.*?\n\}\}[ \t]*\n?", "", text, count=1, flags=re.S)
                    text = expand_pages(text, get_scan_page, warns)
                    EXTRA_WARN.extend(f"{t}: {w}" for w in warns)
                    pd = W.PageData(t, "ok", text=text)
                except W.Blocked as b:
                    pd = W.PageData(t, "blocked", note=b.reason)
        self.cache[t] = pd
        return pd
    return orig_get(self, title)


def allpages(self, prefix, redirects_only=False):
    if prefix == PFX and titles is not None:
        lst = list(titles["redirects"] if redirects_only else titles["pages"])
        if letters and not redirects_only:
            lst = [x for x in lst if x.split("/")[1] in letters or x.split("/")[1] in ("הקדמה", "סימני הש\"ס", "מנין שטרות")]
        return lst
    return orig_all(self, prefix, redirects_only)


W.WikiClient.get_page = get_page
W.WikiClient.allpages = allpages
tm = os.path.join(HERE, "tm_toldot.json")
if "--template-map" not in sys.argv:
    sys.argv += ["--template-map", tm]
rc = W.main()
json.dump(scans, open(scan_path, "w", encoding="utf-8"), ensure_ascii=False)  # cache עמודי הסריקה שנטענו
if EXTRA_WARN:
    print(f"אזהרות הרחבת <pages>: {len(EXTRA_WARN)} (ראה toldot_pages_warnings.txt)", file=sys.stderr)
    open("toldot_pages_warnings.txt", "w", encoding="utf-8").write("\n".join(EXTRA_WARN))
sys.exit(rc)
