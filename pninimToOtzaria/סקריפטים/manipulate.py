import os
import re
import sys

PATH_HEADING_RE = re.compile(r'^<h([1-6])>[^<]*</h\1>$')
DAR_HEADING_RE = re.compile(r'^(%+)\s*(.*)$')
# קטעים שאסור להחיל עליהם את סימון ה-dar: תגים, כתובות ונתוני תמונה
PROTECTED_RE = re.compile(r'<[^>]*>|(?:https?://|www\.)[^\s<>]+|data:[^\s"<>]+')
INLINE_RULES = [
    (re.compile(r'(?<!/)/(?![\s/])([^/\n]+?)/(?!/)'), r'<i>\1</i>'),
    (re.compile(r'\*([^*\n]+?)\*'), r'<b>\1</b>'),
    (re.compile(r'_([^_\n]+?)_'), r'<u>\1</u>'),
    (re.compile(r'\[\^(.*?)\]'), r'<sup>\1</sup>'),
]


# סימון התיקון של פנינים ~למחוק~{להוסיף} מוצג "(למחוק) [להוסיף]", כפי שהקהילה תיקנה ידנית בספרים שפורסמו;
# בתוך מילה הסוגריים נצמדים לאותיות, כמו בתיקונים הידניים: "פסול(ו)", "מ[ה]"
CORRECTION_RE = re.compile(r'~([^~\n]*)~(?:[ \t]*\{([^{}\n]*)\})?|\{([^{}\n]*)\}')
WORD_CHARS = re.compile(r'[\w\'"\u05f3\u05f4\u2019]')


def render_correction(deleted, inserted, before: str, after: str) -> str:
    """deleted/inserted: הטקסט שסומן (או None); before/after: התו שלפני ואחרי הסימון"""
    in_word = bool(WORD_CHARS.match(before or ' ') or WORD_CHARS.match(after or ' '))
    has_letters = lambda t: t is not None and re.search(r'\w', t)
    parts = []
    if has_letters(deleted):
        parts.append(f'({deleted})')
    if inserted is not None:
        parts.append(f'[{inserted}]' if has_letters(inserted) else inserted)
    return ('' if in_word else ' ').join(parts)


def apply_corrections(text: str) -> str:
    def sub(m: re.Match) -> str:
        before = text[m.start() - 1] if m.start() else ''
        after = text[m.end()] if m.end() < len(text) else ''
        if m.group(3) is not None:
            return render_correction(None, m.group(3), before, after)
        return render_correction(m.group(1), m.group(2), before, after)
    return CORRECTION_RE.sub(sub, text)


def apply_inline(text: str) -> str:
    """מחיל את סימון ה-dar רק מחוץ לתגים, לכתובות ולנתוני base64."""
    parts = []
    last = 0
    for m in PROTECTED_RE.finditer(text):
        parts.append((text[last:m.start()], True))
        parts.append((m.group(0), False))
        last = m.end()
    parts.append((text[last:], True))
    # מחליפים כל קטע מוגן במציין זמני כדי שזוגות סימון יוכלו לעטוף אותו
    keep = []
    flat = ''
    for chunk, editable in parts:
        if editable:
            flat += chunk
        else:
            flat += f'\x00{len(keep)}\x00'
            keep.append(chunk)
    flat = apply_corrections(flat)
    for pattern, replacement in INLINE_RULES:
        flat = pattern.sub(replacement, flat)
    return re.sub(r'\x00(\d+)\x00', lambda m: keep[int(m.group(1))], flat)


def manipulate(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')
    out = []
    base_level = 1
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if i == 0:
            out.append(f'<h1>{line.strip()}</h1>')
            continue
        path_heading = PATH_HEADING_RE.match(line)
        if path_heading:
            # כותרת שנוצרה מנתיב הקובץ (merge_books); כותרות % שבתוך הקובץ יורדות ממנה
            base_level = int(path_heading.group(1))
            out.append(line)
            continue
        heading = DAR_HEADING_RE.match(line)
        if heading:
            level = min(base_level + len(heading.group(1)), 6)
            line = f'<h{level}>{apply_inline(heading.group(2).strip())}</h{level}>'
        else:
            line = apply_inline(line)
            if line.startswith('<sup>'):
                line = f'<small>{line.strip()}</small>'
        out.append(line)

    # כותרת שחוזרת מיד אחרי עצמה (כותרת נתיב ואחריה אותה כותרת בתוך הקובץ) - נשארת הראשונה
    result = []
    for line in out:
        if result and re.sub('<[^<]+?>', '', line.replace(' ', '')) == re.sub('<[^<]+?>', '', result[-1].replace(' ', '')):
            continue
        result.append(line)

    with open(path.replace('merged.txt', '.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(result) + '\n')


def process_dir(path):
    """
    Runs manipulate() on every <name>merged.txt under path.
    """
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('merged.txt'):
                manipulate(os.path.join(root, file))


if __name__ == '__main__':
    process_dir(sys.argv[1] if len(sys.argv) > 1 else os.path.join('pninimToOtzaria', 'pninim books'))
