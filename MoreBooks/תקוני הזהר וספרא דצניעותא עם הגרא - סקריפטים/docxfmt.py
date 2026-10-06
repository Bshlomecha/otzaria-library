"""קריאת docx מפורק (word/*.xml) עם עיצוב אפקטיבי לכל ריצה.

כל הריצות בשני הקבצים מסומנות rtl, ולכן ההדגשה והגודל שמוצגים בעברית הם
bCs / szCs (לא b / sz). הערך האפקטיבי נקבע לפי סדר העדיפויות של Word:
rPr ישיר > סגנון התו (rStyle, כולל basedOn) > סגנון הפסקה (pStyle, כולל basedOn)
> docDefaults.

segments(p) מחזיר רשימה של:
  ('t', text, fmt)   — fmt = dict(bold, small, sup, color, hidden)
  ('fn', id)         — סמן הערת שוליים
  ('img', rId)       — תמונה inline
  ('br',)            — שבירת שורה בתוך פסקה
"""
import re
from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
V = '{urn:schemas-microsoft-com:vml}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'


def _onoff(e):
    if e is None:
        return None
    return e.get(W + 'val') not in ('0', 'false', 'off')


class Styles:
    def __init__(self, root):
        st = etree.parse(root + '/word/styles.xml').getroot()
        self.by_id = {s.get(W + 'styleId'): s for s in st.iter(W + 'style')}
        self.default_para = None
        for s in st.iter(W + 'style'):
            if s.get(W + 'type') == 'paragraph' and s.get(W + 'default') in ('1', 'true'):
                self.default_para = s.get(W + 'styleId')
        self.defaults = {}
        dd = st.find(W + 'docDefaults')
        if dd is not None:
            rpr = dd.find('.//' + W + 'rPr')
            if rpr is not None:
                self.defaults = self._props(rpr)
        self._cache = {}

    def name(self, sid):
        s = self.by_id.get(sid)
        if s is None or s.find(W + 'name') is None:
            return sid or ''
        return s.find(W + 'name').get(W + 'val')

    @staticmethod
    def _props(rpr):
        d = {}
        v = _onoff(rpr.find(W + 'bCs'))
        if v is not None:
            d['bold'] = v
        v = _onoff(rpr.find(W + 'iCs'))
        if v is not None:
            d['ital'] = v
        e = rpr.find(W + 'szCs')
        if e is not None:
            d['sz'] = int(e.get(W + 'val'))
        e = rpr.find(W + 'color')
        if e is not None:
            d['color'] = e.get(W + 'val')
        e = rpr.find(W + 'vertAlign')
        if e is not None:
            d['va'] = e.get(W + 'val')
        e = rpr.find(W + 'u')
        if e is not None:
            d['u'] = e.get(W + 'val') not in (None, 'none', '0')
        v = _onoff(rpr.find(W + 'vanish'))
        if v is not None:
            d['hidden'] = v
        return d

    def chain(self, sid):
        """מאפייני הריצה של סגנון כולל basedOn (הבסיס קודם, הנגזר דורס)."""
        if sid in self._cache:
            return self._cache[sid]
        out = {}
        s = self.by_id.get(sid)
        if s is not None:
            b = s.find(W + 'basedOn')
            if b is not None and b.get(W + 'val') != sid:
                out.update(self.chain(b.get(W + 'val')))
            rpr = s.find(W + 'rPr')
            if rpr is not None:
                out.update(self._props(rpr))
        self._cache[sid] = out
        return out


def pstyle(p):
    ppr = p.find(W + 'pPr')
    if ppr is not None and ppr.find(W + 'pStyle') is not None:
        return ppr.find(W + 'pStyle').get(W + 'val')
    return None


def in_textbox(el):
    return any(a.tag == W + 'txbxContent' for a in el.iterancestors())


def in_fallback(el):
    return any(a.tag == MC + 'Fallback' for a in el.iterancestors())


def segments(p, styles):
    """סגמנטים של פסקה לפי סדר, עם עיצוב אפקטיבי."""
    psid = pstyle(p) or styles.default_para
    base = dict(styles.defaults)
    base.update(styles.chain(psid))
    out = []
    for r in p.iter(W + 'r'):
        if in_textbox(r) or in_fallback(r):
            continue
        # ריצה בתוך ריצה (למשל בתוך שדה) — רק הריצה הפנימית
        rpr = r.find(W + 'rPr')
        f = dict(base)
        if rpr is not None:
            rs = rpr.find(W + 'rStyle')
            if rs is not None:
                f.update(styles.chain(rs.get(W + 'val')))
            f.update(Styles._props(rpr))
        fmt = {
            'bold': bool(f.get('bold')),
            'sz': f.get('sz', 22),
            'sup': f.get('va') == 'superscript',
            'color': f.get('color'),
            'hidden': bool(f.get('hidden')),
            'u': bool(f.get('u')),
        }
        for ch in r:
            if ch.tag == W + 't':
                out.append(('t', ch.text or '', fmt))
            elif ch.tag == W + 'tab':
                out.append(('t', ' ', fmt))
            elif ch.tag in (W + 'br', W + 'cr'):
                out.append(('br',))
            elif ch.tag == W + 'noBreakHyphen':
                out.append(('t', '-', fmt))
            elif ch.tag == W + 'footnoteReference':
                out.append(('fn', ch.get(W + 'id')))
            elif ch.tag == W + 'footnoteRef':
                out.append(('fnref',))
            elif ch.tag == W + 'drawing':
                blips = list(ch.iter(A + 'blip'))
                out.append(('img', blips[0].get(R + 'embed') if blips else None))
            elif ch.tag == W + 'pict' or ch.tag == W + 'object':
                ims = list(ch.iter(V + 'imagedata'))
                out.append(('img', ims[0].get(R + 'id') if ims else None))
            elif ch.tag == MC + 'AlternateContent':
                chs = ch.find(MC + 'Choice')
                if chs is not None:
                    blips = list(chs.iter(A + 'blip'))
                    if blips:
                        out.append(('img', blips[0].get(R + 'embed')))
    return out


def plain(segs):
    return ''.join(s[1] if s[0] == 't' else (' ' if s[0] == 'br' else '') for s in segs)


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
