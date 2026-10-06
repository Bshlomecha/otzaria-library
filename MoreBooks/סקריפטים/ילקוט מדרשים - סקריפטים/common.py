import os,re
SRC="/Users/david/Downloads/ילקוט מדרשים - אוצריא"
def mask(s): return re.sub(r'[֐-׿]+',lambda x:str(len(x.group())) if False else '*'*len(x.group()),s)
def vols():
    out={}
    for x in sorted(os.listdir(SRC)):
        if len(x)<10: continue
        key='A' if x.endswith('ראשון.txt') else 'B'
        out[key]=(x,open(os.path.join(SRC,x),encoding='utf-8').read().split('\n'))
    return out
G={c:v for c,v in zip('אבגדהוזחטיכלמנסעפצקרשת',[1,2,3,4,5,6,7,8,9,10,20,30,40,50,60,70,80,90,100,200,300,400])}
G.update({'ך':20,'ם':40,'ן':50,'ף':80,'ץ':90})
def gem(s):
    s=re.sub(r'[^א-ת]','',s)
    return sum(G.get(c,0) for c in s) if s else None
KW=['מדרש','תדשא','פירוש','החיד','הוספות','הערות','מבוא','פתיחה','חופת אליהו','שער','ברייתא','פנחס','פרק','קיצור','שם הספר','זמנו','או ']
