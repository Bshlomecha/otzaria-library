"""Span-aware decoder for the HED PRESS KSK PDFs (legacy Advvil/Advfrl fonts).

Glyph names encode cp1255 positions (C224 = alef ...).  This module keeps, per
output line, the list of (font, text) spans so bold (Vilna) runs survive.
Output per page: list of line dicts {col,x0,x1,y,size,spans:[[font,text],..]}.
"""
import re, json, gzip, os
from pypdf import PdfReader
from fontTools.encodings.StandardEncoding import StandardEncoding
import pymupdf

STD = {n: i for i, n in enumerate(StandardEncoding) if n != '.notdef'}
STDPUNCT = {'parenright': ')', 'parenleft': '(', 'zero': '0', 'one': '1', 'two': '2', 'three': '3',
            'four': '4', 'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
            'quotedbl': '"', 'comma': ',', 'period': '.', 'colon': ':', 'semicolon': ';',
            'hyphen': '-', 'bracketleft': '[', 'bracketright': ']', 'question': '?',
            'asterisk': '*', 'quoteright': "'", 'quotesingle': "'", 'space': ' ', 'exclam': '!',
            'slash': '/', 'endash': '–', 'emdash': '—', 'percent': '%', 'plus': '+'}
HEBNAMES = dict(zip(
    'alef bet gimel dalet he vav zayin het tet yod finalkaf kaf lamed finalmem mem finalnun nun '
    'samekh ayin finalpe pe finaltsadi tsadi qof resh shin tav'.split(),
    'אבגדהוזחטיךכלםמןנסעףפץצקרשת'))
# glyphs that are not cp1255 positions; roles established by aligning with the old KSK text
# (see report): dagger/Z/Y = dash separators (old text has an em dash there), B = vav
# ligature, N = shin ligature, equal = editorial marker inside a bracket (old text drops it).
SPECIAL = {'dagger': '—', 'Z': '—', 'Y': '—', 'B': 'ו', 'N': 'ש', 'equal': ''}
# glyph names that are niqqud positions (cp1255 0xC0-0xD2)
SPACE_GAP = 0.8
COMBINING = set(chr(c) for c in range(0x0591, 0x05C8) if c not in (0x05BE, 0x05C0, 0x05C3, 0x05C6))


# Latin-named glyphs inside the Hebrew (Adv*) fonts are pointed letter forms; roles
# established by aligning neighbouring words with the old KSK text (e.g. 'e' = vav with
# holam, 'a' = bet with dagesh).  Unresolved ones (k, t, w) are dropped.
ADV_LETTERS = {'e': 'ו', 'a': 'ב', 'i': 'י', 'n': 'י', 'l': 'ל', 'E': 'ך', 'L': 'ש',
               'p': 'נ', 'd': 'ה', 'z': 'ת', 'k': '', 't': '', 'w': '', 'C217': ''}
DROPPED = {}


def glyph2char(n, adv=True):
    if not adv:
        if n in STDPUNCT:
            return STDPUNCT[n]
        if n == 'onehalf':
            return '\u00bd'
        code = STD.get(n)
        if code is not None and 0x20 < code < 0x7f:
            return chr(code)
        return '{' + n + '}'
    if n in ADV_LETTERS:
        return ADV_LETTERS[n]
    if n in STDPUNCT:
        return STDPUNCT[n]
    if n in SPECIAL:
        return SPECIAL[n]
    if n.endswith('hebrew') and n[:-6] in HEBNAMES:
        return HEBNAMES[n[:-6]]
    mm = re.fullmatch(r'C(\d+)', n)
    code = int(mm.group(1)) if mm else STD.get(n)
    if code is not None and (0xE0 <= code <= 0xFA or 0xC0 <= code <= 0xD2):
        ch = bytes([code]).decode('cp1255', errors='replace')
        if ch != '�':
            return ch
    return '{' + n + '}'


def fontmap(f):
    adv = bool(re.match(r'(vil|frl|tam)', short_font(str(f.get('/BaseFont'))[1:])))
    enc = f.get('/Encoding')
    enc = enc.get_object() if enc is not None else None
    mp = {}
    if hasattr(enc, 'get') and '/Differences' in enc:
        c = 0
        for x in enc['/Differences']:
            if isinstance(x, int) or str(x).lstrip('-').isdigit():
                c = int(x)
            else:
                mp[c] = glyph2char(str(x)[1:], adv); c += 1
    return mp


def tounicode_inv(f):
    tu = f.get('/ToUnicode'); inv = {}
    if not tu:
        return inv
    data = tu.get_object().get_data().decode('latin1')
    for blk in re.findall(r'beginbfchar(.*?)endbfchar', data, re.S):
        for a, b in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
            inv[chr(int(b, 16))] = int(a, 16)
    for blk in re.findall(r'beginbfrange(.*?)endbfrange', data, re.S):
        for a, b, c in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk):
            for i in range(int(a, 16), int(b, 16) + 1):
                inv[chr(int(c, 16) + i - int(a, 16))] = i
    return inv


def page_maps(pg):
    maps = {}
    fonts = pg['/Resources'].get('/Font', {})
    for k, v in fonts.items():
        f = v.get_object(); bf = str(f.get('/BaseFont'))[1:]
        fm = fontmap(f); inv = tounicode_inv(f)
        mp = maps.setdefault(bf.split('+')[-1], {})
        mp.update({chr(c): v for c, v in fm.items() if c < 0x20 and chr(c) not in inv})
        mp.update({u: fm.get(c, u) for u, c in inv.items()})
    return maps


def short_font(fn):
    fn = fn.split('+')[-1]
    return fn[3:] if fn.startswith('Adv') else fn


def decode_page(reader, doc, pi):
    byname = page_maps(reader.pages[pi])
    d = doc[pi].get_text('rawdict')
    chars = []
    for b in d['blocks']:
        for l in b.get('lines', []):
            for sp in l['spans']:
                mp = byname.get(sp['font'].split('+')[-1], {})
                for ch in sp['chars']:
                    x0, y0, x1, y1 = ch['bbox']
                    c = mp.get(ch['c'], ch['c'])
                    if c == '':
                        continue
                    chars.append((round(ch['origin'][1], 1), x0, x1, c, sp['size'], short_font(sp['font'])))
    W = doc[pi].rect.width; mid = W / 2
    # group into lines separately per half-page: the two columns' baselines are
    # offset by ~2pt, so a global y-grouping steals brackets from the other column
    halves = {'R': [], 'L': []}
    for c in chars:
        halves['R' if (c[1] + c[2]) / 2 >= mid else 'L'].append(c)
    hl = []
    for h, cs in halves.items():
        cs.sort(key=lambda c: (c[0], -c[2]))
        cur = []; cy = None
        for c in cs:
            if cy is None or abs(c[0] - cy) > 2:
                if cur: hl.append([h, cy, cur])
                cur = [c]; cy = c[0]
            else:
                cur.append(c)
        if cur: hl.append([h, cy, cur])
    # re-join a line that crosses the gutter (full-width line)
    Rl = [x for x in hl if x[0] == 'R']; Ll = [x for x in hl if x[0] == 'L']
    lines = []
    used = set()
    for r in Rl:
        rx0 = min(c[1] for c in r[2])
        for j, l in enumerate(Ll):
            if j in used or abs(l[1] - r[1]) > 1:
                continue
            lx1 = max(c[2] for c in l[2])
            if rx0 - lx1 < max(12, r[2][0][4] * 1.2) and rx0 < mid + 15 and lx1 > mid - 15:
                r[2] = r[2] + l[2]; used.add(j); break
        lines.append(r[2])
    lines += [l[2] for j, l in enumerate(Ll) if j not in used]
    items = []
    for ln in lines:
        base = [c for c in ln if c[3] not in COMBINING and not all(ch in COMBINING for ch in c[3])]
        marks = [c for c in ln if c not in base]
        base.sort(key=lambda c: -c[2])
        if not base:
            continue
        segs = []; cur = [base[0]]
        for c in base[1:]:
            if cur[-1][1] - c[2] > max(12, c[4] * 1.2):
                segs.append(cur); cur = [c]
            else:
                cur.append(c)
        segs.append(cur)
        # attach each niqqud mark after the base letter whose x-range holds its centre
        attach = {}
        allb = [c for s in segs for c in s]
        for mk in marks:
            cx = (mk[1] + mk[2]) / 2
            best = min(range(len(allb)), key=lambda i: 0 if allb[i][1] - 0.5 <= cx <= allb[i][2] + 0.5
                       else min(abs(cx - allb[i][1]), abs(cx - allb[i][2])))
            attach.setdefault(id(allb[best]), []).append(mk[3])
        for sg in segs:
            spans = []; prev = None
            for c in sg:
                t = ''
                # word space: inter-word gaps are >= 1.6pt, intra-word gaps < 0.3pt in all 14 PDFs
                # (tightly justified Menachot lines go down to ~1.6pt, below the old 0.18*size)
                if prev is not None and prev[1] - c[2] > SPACE_GAP:
                    t = ' '
                t += c[3] + ''.join(attach.get(id(c), []))
                if spans and spans[-1][0] == c[5] and spans[-1][2] == round(c[4], 1):
                    spans[-1][1] += t
                else:
                    if t.startswith(' ') and spans:
                        spans[-1][1] += ' '; t = t[1:]
                    spans.append([c[5], t, round(c[4], 1)])
                prev = c
            x0 = min(c[1] for c in sg); x1 = max(c[2] for c in sg)
            col = 'F' if (x0 < mid - 15 and x1 > mid + 15) else ('R' if x0 >= mid - 15 else 'L')
            items.append(dict(col=col, x0=round(x0, 1), x1=round(x1, 1), y=sg[0][0],
                              size=round(max(c[4] for c in sg), 2), spans=spans))
    items.sort(key=lambda d: (d['y'], -d['x1']))
    return items


def decode_file(path, cache):
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(__file__):
        with gzip.open(cache, 'rt', encoding='utf-8') as f:
            return [json.loads(l) for l in f]
    r = PdfReader(path); doc = pymupdf.open(path)
    pages = [decode_page(r, doc, i) for i in range(len(doc))]
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    tmp = cache + '.tmp'
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    os.replace(tmp, cache)
    return pages
