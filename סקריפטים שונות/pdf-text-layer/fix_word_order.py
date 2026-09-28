"""Redraws multi-word Hebrew text operators with their words left to right.

PDFium treats each text-showing operator as one run and, when it holds Hebrew,
reverses the whole run. A line drawn right to left as a single TJ therefore
comes out with its letters fixed but its words backwards. Drawing the same
glyphs with the words left to right, using kerning to jump between them, makes
that reversal produce the logical order. Every glyph keeps its exact position.
(One operator per word would also work, but PDFium then drops short words that
repeat on neighbouring lines as duplicates.)
"""
import sys
import pikepdf

HEBREW = range(0x0590, 0x0600)


def font_info(font):
    widths = [float(w) for w in font.get('/Widths', [])]
    first = int(font.get('/FirstChar', 0))
    tounicode = {}
    if '/ToUnicode' in font:
        import re
        data = font.ToUnicode.read_bytes().decode('latin-1')
        for block in re.findall(r'beginbfchar(.*?)endbfchar', data, re.S):
            for s, d in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
                tounicode[int(s, 16)] = bytes.fromhex(d).decode('utf-16-be', 'replace')
        for block in re.findall(r'beginbfrange(.*?)endbfrange', data, re.S):
            for a, b, d in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
                for k, c in enumerate(range(int(a, 16), int(b, 16) + 1)):
                    tounicode[c] = chr(int(d, 16) + k)
    simple = font.get('/Subtype') in ('/TrueType', '/Type1')
    return widths, first, tounicode, simple


def mat_mul(a, b):
    # a, b: [a b c d e f] PDF matrices; returns a x b
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def translate(m, tx, ty=0.0):
    return mat_mul([1, 0, 0, 1, tx, ty], m)


def num(x):
    s = f"{x:.4f}".rstrip('0').rstrip('.')
    return pikepdf.Object.parse(s.encode() if s not in ('', '-0') else b'0')


def rewrite_page(pdf, page, stats):
    fonts = page.obj.get('/Resources', {}).get('/Font', {})
    infos = {}
    ops = list(pikepdf.parse_content_stream(page))
    out = []
    tm = tlm = [1, 0, 0, 1, 0, 0]
    tfs = 0.0; tc = 0.0; tw = 0.0; th = 1.0; tl = 0.0
    font = None
    i = 0
    changed = False

    def advance(code, info):
        widths, first, _, _ = info
        w = widths[code - first] if 0 <= code - first < len(widths) else 0.0
        extra = tw if code == 32 else 0.0
        return ((w / 1000.0) * tfs + tc + extra) * th

    while i < len(ops):
        operands, op = ops[i]
        o = str(op)
        if o == 'BT':
            tm = tlm = [1, 0, 0, 1, 0, 0]
        elif o == 'Tf':
            font = str(operands[0]); tfs = float(operands[1])
            if font not in infos and font in fonts:
                infos[font] = font_info(fonts[font])
        elif o == 'Tc':
            tc = float(operands[0])
        elif o == 'Tw':
            tw = float(operands[0])
        elif o == 'Tz':
            th = float(operands[0]) / 100.0
        elif o == 'TL':
            tl = float(operands[0])
        elif o == 'Td':
            tlm = translate(tlm, float(operands[0]), float(operands[1])); tm = tlm
        elif o == 'TD':
            tl = -float(operands[1])
            tlm = translate(tlm, float(operands[0]), float(operands[1])); tm = tlm
        elif o == 'T*':
            tlm = translate(tlm, 0, -tl); tm = tlm
        elif o == 'Tm':
            tlm = [float(x) for x in operands]; tm = tlm
        elif o in ('Tj', 'TJ') and font in infos and infos[font][3]:
            info = infos[font]
            elements = [operands[0]] if o == 'Tj' else list(operands[0])
            # Segments (words and spaces) with their x in text space.
            segments = []
            x = 0.0
            cur = None
            def flush():
                nonlocal cur
                if cur is not None:
                    segments.append(cur); cur = None
            for el in elements:
                if isinstance(el, pikepdf.String):
                    for b in bytes(el):
                        ch = info[2].get(b, '')
                        is_space = ch.isspace() or ch == ''
                        kind = 'space' if is_space else 'word'
                        if cur is None or cur['kind'] != kind:
                            flush()
                            cur = {'kind': kind, 'x0': x, 'parts': [], 'text': ''}
                        if cur['parts'] and isinstance(cur['parts'][-1], bytearray):
                            cur['parts'][-1].append(b)
                        else:
                            cur['parts'].append(bytearray([b]))
                        cur['text'] += ch
                        x += advance(b, info)
                else:
                    k = float(el)
                    x -= k / 1000.0 * tfs * th
                    if cur is not None:
                        cur['parts'].append(k)
            flush()
            words = [s for s in segments if s['kind'] == 'word']
            heb_words = [s for s in words if any(ord(c) in HEBREW for c in s['text'])]
            pairs_ltr = sum(1 for a, b in zip(heb_words, heb_words[1:]) if b['x0'] > a['x0'])
            pairs_rtl = sum(1 for a, b in zip(heb_words, heb_words[1:]) if b['x0'] < a['x0'])
            show_ops = ('Tj', 'TJ', "'", '"')
            continues = (i + 1 < len(ops) and str(ops[i + 1][1]) in show_ops) or (
                i > 0 and str(ops[i - 1][1]) in show_ops)
            # Only runs drawn right to left: those are the ones PDFium reverses into the wrong word order.
            if len(heb_words) >= 2 and pairs_rtl > 0 and pairs_ltr == 0 and not continues:
                # One operator, words left to right: PDFium reverses the run as a
                # whole, which yields the words right to left. Kerning jumps between
                # segments keep every glyph where it was.
                unit = tfs * th / 1000.0
                items = []
                pen = 0.0
                for seg in sorted(segments, key=lambda s: s['x0']):
                    if abs(seg['x0'] - pen) > 1e-6:
                        items.append(num(-(seg['x0'] - pen) / unit))
                    pen = seg['x0']
                    for p in seg['parts']:
                        if isinstance(p, bytearray):
                            items.append(pikepdf.String(bytes(p)))
                            pen += sum(advance(c, info) for c in p)
                        else:
                            items.append(num(p))
                            pen -= p * unit
                out.append(([pikepdf.Array(items)], pikepdf.Operator('TJ')))
                # The next operator positions from the line matrix, which Tm also resets.
                out.append(([num(v) for v in tlm], pikepdf.Operator('Tm')))
                tm = tlm
                stats['lines'] += 1
                changed = True
                i += 1
                continue
            tm = translate(tm, x)
        out.append((operands, op))
        i += 1
    if changed:
        page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(out))
    return changed


def main(src, dst):
    pdf = pikepdf.open(src)
    stats = {'lines': 0, 'pages': 0}
    for page in pdf.pages:
        if rewrite_page(pdf, page, stats):
            stats['pages'] += 1
    pdf.save(dst)
    print(stats)
    return stats['lines']


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
