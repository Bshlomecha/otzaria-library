# -*- coding: utf-8 -*-
"""prefetch2.py (toldot_tanaim) - הורדה בצובר של עמודי הסריקה ("עמוד:<index>/<n>") שכל דפי הערכים מצביעים עליהם (<pages .../>).

קורא את pages.json (prefetch.py), אוסף את כל (index, from..to), ומוריד אותם ל-pagens.json (40 בבקשה). 690 עמודי סריקה ייחודיים.
ב-2026 נחסם (418) אחרי 40 עמודים. אל תעקוף: במחשב לא מסונן זה אמור לעבור; אם נחסם גם שם - דווח.
שים לב: ה-"size" שנשמר הוא של האחסון ואינו שווה לאורך הטקסט (תוכן ProofreadPage) - אל תשווה אותם (ראה LESSONS.md).
מריצים בתיקיית העבודה (cwd) שבה pages.json.
"""
import json, sys, time, requests, os, re
HERE = os.getcwd()
API = "https://he.wikisource.org/w/api.php"
s = requests.Session(); s.headers.update({"User-Agent": "OtzariaLibraryBot/1.0 (https://github.com/Otzaria/otzaria-library)", "Accept-Encoding": "gzip"})
DELAY = 1.5
def req(params):
    for att in range(1, 7):
        time.sleep(DELAY)
        r = s.post(API, data=params, timeout=60)
        if "netfree" in " ".join(f"{k}:{v}" for k, v in r.headers.items()).lower() or r.status_code in (403, 418):
            print("BLOCKED", r.status_code); sys.exit(3)
        if r.status_code == 429 or r.status_code >= 500:
            print("retry", r.status_code, flush=True); time.sleep(10 * att); continue
        if "json" not in r.headers.get("content-type", ""):
            print("NONJSON", r.status_code); sys.exit(3)
        d = r.json()
        if "error" in d:
            print("apierr", d["error"]); time.sleep(10 * att); continue
        return d
    print("FAILED"); sys.exit(4)
c = json.load(open(os.path.join(HERE, "pages.json"), encoding="utf-8"))
need = set()
for k, v in c.items():
    if k.count('/') != 2: continue
    for m in re.finditer(r"<pages\b[^>]*?/>", v["text"], re.S):
        m = m.group(0)
        i = re.search(r'index="([^"]*)"', m).group(1)
        a = int(re.search(r'from=(\d+)', m).group(1)); b = int(re.search(r'to=(\d+)', m).group(1))
        for n in range(a, b + 1): need.add(f"עמוד:{i}/{n}")
need = sorted(need)
print("need", len(need), flush=True)
cp = os.path.join(HERE, "pagens.json")
cache = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {}
todo = [t for t in need if t not in cache]
for i in range(0, len(todo), 40):
    d = req({"action": "query", "prop": "revisions", "titles": "|".join(todo[i:i+40]), "rvslots": "main",
             "rvprop": "content|size", "format": "json", "formatversion": 2})
    for p in d["query"]["pages"]:
        if p.get("missing") or "revisions" not in p: cache[p["title"]] = None
        else:
            rv = p["revisions"][0]; cache[p["title"]] = {"text": rv["slots"]["main"]["content"], "size": rv.get("size")}
    if (i // 40) % 5 == 0:
        json.dump(cache, open(cp, "w", encoding="utf-8"), ensure_ascii=False); print("fetched", len(cache), flush=True)
json.dump(cache, open(cp, "w", encoding="utf-8"), ensure_ascii=False)
print("DONE", len(cache), "missing", sum(1 for v in cache.values() if v is None))
