"""Adds a ToUnicode CMap to simple fonts whose Hebrew glyphs carry Latin glyph names.

The fonts encode Windows-1255 Hebrew through Latin-1 (agrave = alef) or Mac Roman
(daggerdbl = alef) glyph names, and ship no ToUnicode, so every reader extracts Latin
letters. The CMap maps each code to the Hebrew letter its glyph really draws.
"""
import sys
import pikepdf
from fontTools.agl import toUnicode as agl_to_unicode

def cp1255_byte_to_hebrew(b):
    if 0xE0 <= b <= 0xFA:
        return chr(0x05D0 + b - 0xE0)
    return None

MAC = {}
for b in range(0x80, 0x100):
    try:
        MAC[bytes([b]).decode('mac_roman')] = b
    except UnicodeDecodeError:
        pass


DAGESH, HOLAM, SHIN, SIN = 'ּ', 'ֹ', 'ׁ', 'ׂ'

# GHodes_Shas: a vowelized font whose glyph names are arbitrary Latin names.
# Identified by rendering every glyph; the names are shared by all its subsets.
GHODES = {
    'grave': 'א', 'ocircumflex': 'אָ', 'otilde': 'אַ',
    'a': 'ב', 'A': 'ב' + DAGESH, 'b': 'ג', 'B': 'ג' + DAGESH,
    'c': 'ד', 'C': 'ד' + DAGESH, 'd': 'ה', 'D': 'ה' + DAGESH,
    'e': 'ו', 'E': 'ו' + DAGESH, 'F': 'ו' + HOLAM, 'f': 'ז', 'G': 'ז' + DAGESH,
    'g': 'ח', 'h': 'ט', 'H': 'ט' + DAGESH, 'i': 'י', 'I': 'י' + DAGESH,
    'k': 'כ', 'M': 'כ' + DAGESH, 'J': 'ך' + DAGESH, 'K': 'ךְ', 'L': 'ךָ',
    'l': 'ל', 'N': 'ל' + DAGESH, 'divide': 'ל' + HOLAM,
    'n': 'מ', 'O': 'מ' + DAGESH, 'm': 'ם', 'p': 'נ', 'P': 'נ' + DAGESH, 'o': 'ן',
    'q': 'ס', 'Q': 'ס' + DAGESH, 'r': 'ע', 't': 'פ', 'R': 'פ' + DAGESH, 's': 'ף',
    'v': 'צ', 'S': 'צ' + DAGESH, 'u': 'ץ', 'w': 'ק', 'T': 'ק' + DAGESH, 'x': 'ר',
    'U': 'ש' + SHIN, 'W': 'ש' + SIN, 'X': 'ש' + DAGESH + SHIN, 'V': 'ש' + DAGESH + SIN,
    'z': 'ת', 'Y': 'ת' + DAGESH,
    'section': 'ְ', 'exclamdown': 'ֱ', 'sterling': 'ֲ', 'cent': 'ֳ',
    'brokenbar': 'ִ', 'yen': 'ֵ', 'currency': 'ֶ', 'copyright': 'ַ',
    'dieresis': 'ָ', 'Ydieresis': HOLAM, 'ordfeminine': 'ֻ', 'colon': '׃',
    'period': '.', 'comma': ',', 'bracketleft': '[', 'bracketright': ']',
    'parenleft': '(', 'parenright': ')',
}

def glyph_char(name):
    s = agl_to_unicode(name)
    return s if len(s) == 1 else None

def mapping_for(font):
    enc = font.get('/Encoding')
    if 'GHodes_Shas' in str(font.get('/BaseFont')):
        names = differences(enc)
        missing = sorted(set(names.values()) - GHODES.keys())
        if missing:
            if '/ToUnicode' in font:
                return None
            raise SystemExit(f'GHodes_Shas glyphs without a mapping: {missing}')
        return {code: GHODES[n] for code, n in names.items()}, 'manual'
    if not isinstance(enc, pikepdf.Dictionary) or '/Differences' not in enc:
        return None
    names = differences(enc)
    latin = mac = 0
    for n in names.values():
        c = glyph_char(n)
        if c is None:
            continue
        if cp1255_byte_to_hebrew(ord(c)) if ord(c) < 0x100 else None:
            latin += 1
        if c in MAC and cp1255_byte_to_hebrew(MAC[c]):
            mac += 1
    if max(latin, mac) < 5:
        return None
    use_mac = mac > latin
    result = {}
    for code, n in names.items():
        c = glyph_char(n)
        if c is None:
            continue
        heb = None
        if use_mac and c in MAC:
            heb = cp1255_byte_to_hebrew(MAC[c])
        elif not use_mac and ord(c) < 0x100:
            heb = cp1255_byte_to_hebrew(ord(c))
        result[code] = heb or c
    return result, ('mac' if use_mac else 'latin1')

import re

def existing_cmap(font):
    """Single-byte code -> text of the font's current ToUnicode."""
    data = font.ToUnicode.read_bytes().decode('latin-1')
    result = {}
    for block in re.findall(r'beginbfchar(.*?)endbfchar', data, re.S):
        for src, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            result[int(src, 16)] = bytes.fromhex(dst).decode('utf-16-be', 'replace')
    for block in re.findall(r'beginbfrange(.*?)endbfrange', data, re.S):
        for a, b, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            start = int(dst, 16)
            for k, code in enumerate(range(int(a, 16), int(b, 16) + 1)):
                result[code] = chr(start + k)
    return result

def is_mojibake(text):
    return any((0xE0 <= ord(c) <= 0xFA) or c in MAC for c in text) and not any('֐' <= c <= '׿' for c in text)

def differences(enc):
    code = None
    names = {}
    for item in enc.Differences:
        if isinstance(item, int):
            code = item
        else:
            names[code] = str(item)[1:]
            code += 1
    return names

def cmap_stream(mapping):
    lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
             "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
             "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def",
             "1 begincodespacerange", "<00> <FF>", "endcodespacerange"]
    items = sorted(mapping.items())
    for i in range(0, len(items), 100):
        chunk = items[i:i + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        for code, text in chunk:
            hexes = ''.join(f"{ord(c):04X}" for c in text)
            lines.append(f"<{code:02X}> <{hexes}>")
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    return "\n".join(lines).encode()

def main(src, dst):
    pdf = pikepdf.open(src)
    fixed = {}
    for page in pdf.pages:
        fonts = page.obj.get('/Resources', {}).get('/Font', {})
        for _, font in fonts.items():
            if font.objgen in fixed or font.get('/Subtype') != '/TrueType':
                continue
            m = mapping_for(font)
            if m is None:
                continue
            mapping, kind = m
            if '/ToUnicode' in font:
                # Keep a map that is already right; replace one that yields mojibake.
                current = existing_cmap(font)
                broken = [c for c, t in current.items() if is_mojibake(t) and c in mapping and any('֐' <= x <= '׿' for x in mapping[c])]
                if not broken:
                    continue
                kind += ' (replaced)'
            font.ToUnicode = pdf.make_stream(cmap_stream(mapping))
            fixed[font.objgen] = (str(font.BaseFont), kind, len(mapping))
    for base, kind, n in sorted(set(fixed.values())):
        print(f"  {base}: {kind}, {n} codes")
    pdf.save(dst, object_stream_mode=pikepdf.ObjectStreamMode.preserve)
    print(f"{len(fixed)} fonts fixed")
    return len(fixed)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
