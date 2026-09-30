#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ניקוי_דטרמיניסטי.py — שם הפקודה הוותיק של הניקוי הדטרמיניסטי לספרי דיקטה.

הקוד עבר ל־dicta_clean.py (מודול שאפשר לייבא; ר' שם את רשימת הכללים ו־README.md).
שינויים מהגרסה הקודמת:
  * H (הסרת <b> מ"מספר עמוד מדומה") — כבוי כברירת מחדל ומוגבל למספר גימטריה עם
    גרש/גרשיים; קודם הסיר הדגשה מדיבורים אמיתיים (<b>שם</b>, <b>ר'</b>, <b>כסף</b>).
  * B (מיזוג שורה מודגשת לקודמת) — כבוי כברירת מחדל (`--enable B` לקבצים מהממיר
    הישן), ולא ממזג יותר כותרת לא מסומנת (<b>הלכות תשובה</b>) או שורת תווית.
  * M (חדש, אחרון) — איחוד רצפי <b> סמוכים (`--only M` להפעלה לבד).
  * P, S, R, T (חדשים, לפני M) — תיקוני OCR: ו' במקום "(" לפני הפניה, אות סופית
    באמצע מילה (לפי מילון שכיחות), רמב"מ → רמב"ם, תוס → תוס'. `--only S` / `--only OCR`.

שימוש: כמו קודם —
  python3 ניקוי_דטרמיניסטי.py FILE [FILE ...] [--dry-run] [--json]
  python3 ניקוי_דטרמיניסטי.py --dir PATH [--glob "*.txt"] [--skip E] [--enable B] [--only M]
  python3 ניקוי_דטרמיניסטי.py FILE --only S        # כלל OCR בודד (P/S/R/T או OCR לכולם)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dicta_clean import (  # noqa: E402,F401  (תאימות לייבוא ישן)
    OCR_RULES, PIPELINE, FileReport, apply_ocr_rules, clean_text, main,
    merge_bold_runs, process_file,
)

if __name__ == "__main__":
    sys.exit(main())
