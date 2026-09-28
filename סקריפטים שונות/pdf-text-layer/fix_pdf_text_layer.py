"""Repairs the text layer of the Talmud Bavli PDFs in place.

Usage: python fix_pdf_text_layer.py <folder-or-pdf>...

Two steps, each touching only what it detects as broken:
1. fix_tounicode: fonts that expose Hebrew as Latin-1 / Mac Roman / arbitrary
   glyph names get a correct ToUnicode map.
2. fix_word_order: lines that PDFium would extract with reversed word order are
   redrawn with the same glyphs at the same positions.
A file is rewritten only when something changed. Rendering is unaffected; check
with a pixel diff before committing.
"""
import os
import sys
import tempfile
import contextlib
import io

import fix_tounicode
import fix_word_order


def fix(path):
    with tempfile.TemporaryDirectory() as tmp:
        step1 = os.path.join(tmp, 'step1.pdf')
        step2 = os.path.join(tmp, 'step2.pdf')
        with contextlib.redirect_stdout(io.StringIO()):
            fonts = fix_tounicode.main(path, step1)
            lines = fix_word_order.main(step1, step2)
        if fonts or lines:
            os.replace(step2, path)
        return fonts, lines


def main(args):
    paths = []
    for arg in args:
        if os.path.isdir(arg):
            paths += [os.path.join(arg, n) for n in sorted(os.listdir(arg)) if n.lower().endswith('.pdf')]
        else:
            paths.append(arg)
    for path in paths:
        fonts, lines = fix(path)
        if fonts or lines:
            print(f"{os.path.basename(path)}: {fonts} fonts, {lines} lines")


if __name__ == '__main__':
    main(sys.argv[1:])
