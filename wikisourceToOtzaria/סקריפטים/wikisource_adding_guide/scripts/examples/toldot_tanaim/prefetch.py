# -*- coding: utf-8 -*-
"""prefetch.py (toldot_tanaim) - הורדה בצובר (POST, 40 כותרים בבקשה) של כל דפי "תולדות תנאים ואמוראים/..." ל-cache מקומי.

למה: 2,242 דפים; בקשה לכל דף (כמו ws_book) איטית וגורמת ל-HTTP 429. כאן: allpages (עם ובלי הפניות) -> titles.json, ואז
pages.json = {כותרת: {"text": ..., "size": ...} | null}. אפשר לחדש (מה שכבר ב-cache לא נמשך שוב). השהיה ראשונה: argv[1] (שניות; 1.0).
חסימה (418/403/non-JSON) -> יציאה בקוד 3, בלי עקיפה. בריצת 2026 הושלמה ההורדה (2,242/2,242) בלי חסימה - ואז ה-POST של
prefetch2.py (עמודי סריקה) נחסם בנטפרי (418) אחרי 40 עמודים; במחשב לא מסונן זה אמור לעבוד.
דוגמה:  python -X utf8 prefetch.py 1.0      (כותב titles.json ו-pages.json לתיקיית הסקריפט -> העתק/הרץ בתיקיית העבודה)
הערה: כותב ל-HERE (תיקיית הסקריפט). ל-run_toldot.py נדרשים הקבצים ב-cwd - הרץ מתוך תיקיית עבודה, או העתק אותם.
"""
import json, sys, time, requests, os
HERE = os.getcwd()  # הקבצים נכתבים ל-cwd
API = "https://he.wikisource.org/w/api.php"
UA = {"User-Agent": "OtzariaLibraryBot/1.0 (https://github.com/Otzaria/otzaria-library)", "Accept-Encoding": "gzip"}
PREFIX = "תולדות תנאים ואמוראים/"
s = requests.Session(); s.headers.update(UA)
DELAY = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0

def req(params):
    for att in range(1, 7):
        time.sleep(DELAY)
        r = s.post(API, data=params, timeout=60)
        hosts = {h.url for h in r.history}
        if "netfree" in " ".join(f"{k}:{v}" for k, v in r.headers.items()).lower() or r.status_code in (403, 418):
            print("BLOCKED", r.status_code, str(params)[:200]); sys.exit(3)
        if r.status_code == 429 or r.status_code >= 500:
            print("retry", r.status_code, flush=True); time.sleep(10 * att); continue
        if "json" not in r.headers.get("content-type", ""):
            print("NONJSON", r.status_code, str(params)[:200]); sys.exit(3)
        d = r.json()
        if "error" in d:
            print("apierr", d["error"]); time.sleep(10 * att); continue
        return d
    print("FAILED", str(params)[:200]); sys.exit(4)

# all subpages (non-redirect and redirect)
def allp(red):
    out, cont = [], None
    while True:
        p = {"action": "query", "list": "allpages", "apprefix": PREFIX, "apnamespace": 0, "aplimit": "max",
             "apfilterredir": "redirects" if red else "nonredirects", "format": "json", "formatversion": 2}
        if cont: p["apcontinue"] = cont
        d = req(p)
        out += [x["title"] for x in d["query"]["allpages"]]
        cont = d.get("continue", {}).get("apcontinue")
        print(len(out), flush=True)
        if not cont: return out
pages = allp(False)
reds = allp(True)
json.dump({"pages": pages, "redirects": reds}, open(os.path.join(HERE, "titles.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("titles", len(pages), "redirects", len(reds), flush=True)
cache_path = os.path.join(HERE, "pages.json")
cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
todo = [t for t in pages if t not in cache]
for i in range(0, len(todo), 40):
    batch = todo[i:i + 40]
    d = req({"action": "query", "prop": "revisions", "titles": "|".join(batch), "rvslots": "main",
             "rvprop": "content|size", "format": "json", "formatversion": 2})
    for p in d["query"]["pages"]:
        if p.get("missing") or "revisions" not in p:
            cache[p["title"]] = None
        else:
            rv = p["revisions"][0]
            cache[p["title"]] = {"text": rv["slots"]["main"]["content"], "size": rv.get("size")}
    if (i // 40) % 5 == 0:
        json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
        print("fetched", len(cache), "/", len(pages), flush=True)
json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
print("DONE", len(cache))
