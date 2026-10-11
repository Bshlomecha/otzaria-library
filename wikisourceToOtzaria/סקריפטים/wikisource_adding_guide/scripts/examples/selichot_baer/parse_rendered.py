# -*- coding: utf-8 -*-
"""parse_rendered.py (selichot_baer) - הורדת ה-HTML המרונדר (action=parse) של דפי הספר, ל-qa_tokens.py. נכתב עבור: הסליחות לכל השנה.

מוריד html_<שם דף>.html לכל דף ברשימה names (תחת הקידומת). ב-429 ממתין ומנסה שוב (עד 10); קוד אחר שאינו 200 -> STOP.
לספר אחר: שנה את names ואת הקידומת. פלט ה-HTML הוא הבסיס ל"בדיקת שימור" מול ה-wikitext שהכלי עיבד - בדיקה שתופסת גם טקסט
שהגיע מ-<pages> ומתבניות.
"""
import sys, time, requests, json
UA="OtzariaLibraryBot/1.0 (https://github.com/Otzaria/otzaria-library)"
s=requests.Session(); s.headers['User-Agent']=UA
names=["סדר הסליחות","סליחות ליום ראשון","סליחות ליום שני","סליחות ליום שלישי","סליחות ליום רביעי","סליחות ליום חמישי","סליחות ליום שישי","שער"]
for n in names:
    t="הסליחות לכל השנה - זליגמן בער/"+n
    for att in range(10):
        time.sleep(2)
        r=s.get("https://he.wikisource.org/w/api.php",params={"action":"parse","page":t,"prop":"text|wikitext","format":"json","formatversion":2,"disablelimitreport":1},timeout=90)
        if r.status_code in(429,500,502,503,504): time.sleep(10*(att+1)); continue
        break
    if r.status_code!=200 or 'json' not in r.headers.get('content-type',''):
        print("STOP",n,r.status_code); break
    d=r.json()
    open(f"html_{n.replace(' ','_')}.html","w",encoding='utf-8').write(d['parse']['text'])
    print(n,len(d['parse']['text']))
