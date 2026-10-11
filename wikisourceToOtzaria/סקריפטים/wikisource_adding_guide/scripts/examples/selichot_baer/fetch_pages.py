
# -*- coding: utf-8 -*-
"""fetch_pages.py (selichot_baer) - הורדת קבוצת עמודים (מספרים רצופים) מוויקיטקסט ל-pages.json: {כותרת: [contentmodel, content]}.

שימוש:  python -X utf8 fetch_pages.py <out.json> <קידומת> <מס' ראשון> <מס' אחרון>
דוגמה:  python -X utf8 fetch_pages.py pages.json "עמוד:The Seliḥot for the Entire Year.pdf/" 1 74
בקשות של עד 25 כותרים כל אחת (המגבלה הרגילה ל-API ללא הרשאה: 50), עם המתנה ארוכה יותר ב-429.
חסימה (קוד שאינו 200 / תגובה שאינה JSON) עוצרת את הריצה: STOP - אין לעקוף (ראה LESSONS.md).
כותרים חסרים נרשמים עם content=None; מודפס "missing".
"""
import json, sys, time
import requests

UA = "OtzariaLibraryBot/1.0 (https://github.com/Otzaria/otzaria-library)"
s = requests.Session()
s.headers["User-Agent"] = UA


def fetch(titles):
    """titles list (<=50) -> dict title->(model,content)"""
    for att in range(12):
        time.sleep(1.5)
        r = s.get("https://he.wikisource.org/w/api.php", params={"action": "query", "prop": "revisions", "titles": "|".join(titles), "rvslots": "main", "rvprop": "content|contentmodel", "format": "json", "formatversion": 2}, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            print("retry", r.status_code, file=sys.stderr)
            time.sleep(10 * (att + 1))
            continue
        if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
            raise SystemExit(f"STOP status {r.status_code} {r.headers.get('content-type')}")
        d = r.json()
        out = {}
        for pg in d["query"]["pages"]:
            rv = pg.get("revisions", [{}])[0].get("slots", {}).get("main", {})
            out[pg["title"]] = (rv.get("contentmodel"), rv.get("content"))
        return out
    raise SystemExit("rate limited too long")


if __name__ == "__main__":
    out_path, prefix, a, b = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    nums = list(range(a, b + 1))
    allr = {}
    for i in range(0, len(nums), 25):
        allr.update(fetch([prefix + str(n) for n in nums[i:i + 25]]))
    json.dump(allr, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    print("fetched", len(allr), "missing", [t for t, (m, c) in allr.items() if c is None])
