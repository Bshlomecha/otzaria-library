import os
import re
import sys
import unicodedata

# שורת הכללה של dar: +<נתיב> או +[כיתוב]<נתיב>. שורות שמתחילות ב-+ בתוך קבצי התוכן (גבולות טבלה) אינן הכללות.
INCLUDE_RE = re.compile(r'^\+(?:\[[^\]]*\])?<?([^<>]+)>\s*$')
NAME_NOISE_RE = re.compile(r'["\'׳״‎‏‪-‮]')


def normalize_name(name: str) -> str:
    name = unicodedata.normalize('NFC', name)
    name = NAME_NOISE_RE.sub('', name)
    return re.sub(r'[\s_]+', '_', name).strip('_')


def resolve_include(book_dir: str, rel: str) -> str:
    """
    מחזיר את הנתיב של קובץ שמוכלל באינדקס.
    שם שאינו זהה מותאם אחרי נרמול (גרשיים, סימני כיווניות, רווחים מיותרים); אם אין התאמה יחידה - שגיאה.
    """
    path = os.path.join(book_dir, *rel.split('/'))
    if os.path.isfile(path):
        return path
    current = book_dir
    for part in rel.split('/'):
        exact = os.path.join(current, part)
        if os.path.exists(exact):
            current = exact
            continue
        wanted = normalize_name(part)
        candidates = [n for n in os.listdir(current) if normalize_name(n) == wanted] if os.path.isdir(current) else []
        if len(candidates) != 1:
            raise FileNotFoundError(f'{book_dir}: include "{rel}" not found (candidates: {candidates})')
        current = os.path.join(current, candidates[0])
    if not os.path.isfile(current):
        raise FileNotFoundError(f'{book_dir}: include "{rel}" is not a file')
    return current


def merge_book(book_name: str):
    """
    Reads a pninim index file, replaces every include line with a path heading and the included file,
    and writes <dir>/<dir name>merged.txt. A missing include raises instead of being skipped.
    :param book_name: The path of the index file.
    """
    book_dir = os.path.dirname(book_name)
    last_toc = []
    with open(book_name, 'r', encoding='utf-8') as index_file:
        index_lines = index_file.readlines()
    text = []
    for line in index_lines:
        if line.startswith('#'):
            continue  # הערה של dar
        match = INCLUDE_RE.match(line)
        if not match:
            text.append(line)
            continue
        rel = match.group(1).strip()
        if set(rel) <= {'%'}:
            continue  # הוראת תוכן עניינים של dar
        toc = rel.split('/')
        for i, part in enumerate(toc):
            if i >= len(last_toc) or last_toc[i] != part:
                # שינוי ברמה גבוהה מחייב כותרת גם לרמות שמתחתיה, גם כשהשם שלהן זהה לקודם
                last_toc = last_toc[:i] + toc[i:]
                for j in range(i, len(toc)):
                    text.append(f'<h{j + 2}>{toc[j].replace("_", " ")}</h{j + 2}>\n')
                break
        last_toc = toc
        with open(resolve_include(book_dir, rel), 'r', encoding='utf-8') as f:
            content = f.readlines()
        if content and not content[-1].endswith('\n'):
            content[-1] += '\n'
        text += content
    target = os.path.join(book_dir, os.path.basename(book_dir) + 'merged.txt')
    with open(target, 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(text)
    return target


def process_dir(path):
    """
    Runs merge_book() on every index file under path.
    """
    for root, dirs, files in os.walk(path):
        for file in files:
            if file == 'index':
                merge_book(os.path.join(root, file))


if __name__ == '__main__':
    process_dir(sys.argv[1] if len(sys.argv) > 1 else os.path.join('pninimToOtzaria', 'pninim books'))
