# -*- coding: utf-8 -*-
"""run_cached.py (toldot_tanaim) - הגרסה המקורית: מריץ ws_book.main() כשתוכן הדפים ורשימת תתי-הדפים מוגשים מה-cache המקומי (prefetch.py).

מוחלף על ידי run_toldot.py (שמוסיף הרחבת <pages> ומיפוי תבניות); נשאר כדוגמה הקטנה ביותר של "הגש דפים מ-cache ל-ws_book" -
monkey-patch של WikiClient.get_page ו-WikiClient.allpages. מריצים בתיקיית העבודה עם pages.json/titles.json.
"""
import json, os, sys
HERE = os.getcwd()  # pages.json / titles.json
SCR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/
sys.path.insert(0, SCR)
import ws_book as W

cache = json.load(open(os.path.join(HERE, "pages.json"), encoding="utf-8"))
titles = json.load(open(os.path.join(HERE, "titles.json"), encoding="utf-8"))
PFX = "תולדות תנאים ואמוראים/"

orig_get = W.WikiClient.get_page
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
                pd = W.PageData(t, "ok", text=text.replace("\r\n", "\n"))
        self.cache[t] = pd
        return pd
    return orig_get(self, title)

orig_all = W.WikiClient.allpages
def allpages(self, prefix, redirects_only=False):
    if prefix == PFX:
        return list(titles["redirects"] if redirects_only else titles["pages"])
    return orig_all(self, prefix, redirects_only)

W.WikiClient.get_page = get_page
W.WikiClient.allpages = allpages
sys.exit(W.main())
