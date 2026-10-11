# -*- coding: utf-8 -*-
"""wrap.py (shlosha_dikduk) - עוטף את ws_book.main() ומוסיף מיפוי תבניות סימון אפור + שמירת צבע רקע. נכתב עבור: שלשה ספרי דקדוק.

בספרים אלה הוויקיטקסט מסמן תוספות המתרגם ברקע אפור באמצעות התבניות {{סימון אפור|..}} / {{רקע אפור|..}}, ו"כפתורי ניווט"
{{קישור חיוג'}} / {{קישור רמבג}}. ‏ws_book.py אינו שומר רקע (clean_style מוחק background-color), ולכן כאן:
  * apply_template_map מוחלף ב-patched: אחרי ה---template-map הרגיל מוסיף rd["סימון אפור"] = rd["רקע אפור"] = span עם
    background-color: #E5E4E2; ו-rd["קישור חיוג'"] = rd["קישור רמבג"] = remove;
  * clean_style מוחלף כך שישמור גם background-color: #hex.
דוגמה לדפוס "הרחב את ws_book בלי לשנות אותו": import ws_book -> monkey-patch -> sys.exit(ws_book.main()).
הרצה:  python -X utf8 wrap.py --page "שלשה ספרי דקדוק/<דף>" --name "ספר ..." --out <תיקייה> [--exclude-page ...]
(ראה BLOCKED_BOOKS.md/README - שתי המהדורות × שלושה ספרים; שניים חלקיים.)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SC = os.path.dirname(os.path.dirname(HERE))  # scripts/ (שם יושב ws_book.py)
sys.path.insert(0, SC)
sys.path.insert(0, HERE)
import ws_book
_orig = ws_book.apply_template_map
GRAY = '<span style="background-color: #E5E4E2;">'
def patched(path, rep):
    _orig(path, rep)
    rd = ws_book.templates.replacement_dict
    pos = ws_book.tfuncs.positional
    gray = lambda t: GRAY + " ".join(pos(t)).strip() + '</span>'
    rd["סימון אפור"] = gray
    rd["רקע אפור"] = gray
    rd["קישור חיוג'"] = ws_book.tfuncs.remove
    rd["קישור רמבג"] = ws_book.tfuncs.remove
    rep.info.append("מיפוי מקומי: סימון אפור/רקע אפור -> span רקע אפור; קישור חיוג'/קישור רמבג -> הסרה (כפתורי ניווט)")
_orig_cs = ws_book.clean_style
def _cs(val):
    base = _orig_cs(val)
    import re as _re
    m = _re.search(r"background-color:\s*(#[0-9a-fA-F]{3,8})\s*(;|$)", val)
    if m:
        base = (base + " " if base else "") + f"background-color: {m.group(1).lower()};"
    return base
ws_book.clean_style = _cs
ws_book.apply_template_map = patched
sys.exit(ws_book.main())
