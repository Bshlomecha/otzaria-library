"""Restore what the Chavruta notes temp files lost, from the full source of each masechet.

The notes books (הערות על חברותא על X) were converted from 'HavTempNotes.txt'. That file is a
stale derivative of the masechet's 'HavAll.txt' and it is damaged: it dropped the bold of the
letters yod, gimel and peh (<b>רש''</b>י, שב<b>ע</b>י<b>ן</b> י<b>עקב</b>, <b>תוס</b>פ<b>ות</b>) and
wrote every quotation mark and gershayim as two apostrophes ('' ), which te_convert's gershayim
step then could not fold into a ", because the bold tag sat between the '' and the letter.
HavAll.txt, in the same folder, has the notes whole: <b>רש"י</b>, <b>עין</b> <b>יעקב</b>.

This script does not convert anything again: the current file is the baseline (hand fixes, line
numbers the links point at, headings). For each note it finds the same note in HavAll.txt by its
number, aligns the two texts character by character, and in the aligned stretches
  * bolds every character of a bold word of HavAll that the current file does not bold (never
    removes a bold; the bold HavAll puts on a yod/gimel/peh stuck to a quotation mark is not copied),
  * writes the " HavAll has where the current file has '' (a quote mark or gershayim).
Everything else stays as it is. A note that is not the same text in HavAll is left alone, and a book whose notes HavAll
mostly does not hold (most masechtot: it numbers them differently or lacks them) is skipped whole.
Run on its own output it changes nothing.

--gaps is the second step, for every Chavruta book, notes or text, including those HavAll cannot
vouch for: the same loss is in a few hundred other places (<b>מאיר</b>י, ק</b>י<b>נה, בית שמא</b>י). A
yod/gimel/peh left plain right after the bold letters of a word, or between two bold runs of one word,
is bolded. Checked against the Taanit notes (HavAll's answer): 1,674 of 1,674 such spots agree.
Not done: a plain yod at the start of a word before a bold run (י<b>עקב</b>) - 3 of 413 are
real prefixes, so it is left to the HavAll step, and an unbolded yod beside a quotation mark.

--check prints, per book, what would change, and fails when a change would touch the text in any
other way, or when a note of the book is missing from HavAll.txt.

Usage (from the repo root):
    python ToratEmetToOtzaria/סקריפטים/te_restore_notes.py --src "<Torat Emet dir>" --check
    python ToratEmetToOtzaria/סקריפטים/te_restore_notes.py --src "<Torat Emet dir>" --write [--only תענית]
    python ToratEmetToOtzaria/סקריפטים/te_restore_notes.py --gaps --check|--write
"""
import argparse
import collections
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, '..', 'ספרים', 'אוצריא')
NOTES_DIR = 'הערות על ביאור חברותא'
NOTE_RE = re.compile(r'\[~(\d+)\.~\] ')
END_RE = re.compile(r'\{(?:אאא|ססס)\}')
LINE_NUM_RE = re.compile(r'^<b>\((\d+)\)</b> ')
TAG_RE = re.compile(r'<[^<>]*>')
MAX_OTHER = 0.02  # a book whose notes HavAll holds whole has (almost) none that differ
LETTERS = set('אבדהוזחטכלמנסעצקרשתךםןףץ')   # the Hebrew letters but yod, gimel and peh
SIMILAR = 0.97   # the notes of a book that HavAll has whole match its text at 0.99+


def read_all(path):
    with open(path, 'rb') as f:
        return f.read().decode('cp1255').replace('\r', '')


def rules(html):
    """The rules of the notes' CosmeticsType (HavAll 2454) that make text: <QM> ?, <S> space, SB/SE ( )."""
    for token, text in (('<QM>', '?'), ('<S>', ' '), ('SB', '('), ('SE', ')')):
        html = html.replace(token, text)
    return html


def all_notes(text):
    """-> {note number: note html as HavAll writes it}"""
    notes = {}
    for m in NOTE_RE.finditer(text):
        end = END_RE.search(text, m.end())
        stop = end.start() if end else text.index('\n', m.end())
        notes[int(m.group(1))] = rules(text[m.end():stop].strip())
    return notes


def tokens(html):
    """-> [(token, bold, as written)]; '' is one token, compared as the " it stands for. Only <b> is tracked."""
    out, bold, pos = [], False, 0
    pieces = []
    for m in TAG_RE.finditer(html):
        pieces.append((html[pos:m.start()], bold))
        if m.group() == '<b>':
            bold = True
        elif m.group() == '</b>':
            bold = False
        pos = m.end()
    pieces.append((html[pos:], bold))
    for text, b in pieces:
        for t in re.findall(r"''|.", text, re.S):
            out.append(('"' if t == "''" else t, b, t))
    return out


def real_bold(ref):
    """The positions of ref whose bold is the author's. HavAll also bolds a yod/gimel/peh stuck to a
    quotation mark (<b>"ג</b>בורות<b>"</b>, ק<b>י"</b>ד), where the author bolds the mark alone; so only a
    bold run with a letter other than י, ג, פ is a bold word whose letters were lost."""
    keep, run = set(), []

    def close():
        if sum(1 for j in run if ref[j][0] in LETTERS) >= 1:
            keep.update(run)
        run.clear()
    for j, (_, bold, _) in enumerate(ref):
        if bold:
            run.append(j)
        else:
            close()
    close()
    return keep


def current_tokens(line):
    """-> (segments, idx): segments are ('tag', s) | ('tok', s, bold); idx the positions of 'tok's"""
    segs, bold, pos = [], False, 0

    def add(text):
        for t in re.findall(r"''|.", text, re.S):
            segs.append(['tok', t, bold])
    for m in TAG_RE.finditer(line):
        add(line[pos:m.start()])
        segs.append(['tag', m.group()])
        if m.group() == '<b>':
            bold = True
        elif m.group() == '</b>':
            bold = False
        pos = m.end()
    add(line[pos:])
    return segs, [i for i, s in enumerate(segs) if s[0] == 'tok']


def restore_line(line, note_html, stats):
    """-> the line with HavAll's bold and quote marks, or None when the texts do not match."""
    segs, idx = current_tokens(line)
    cur = [('"' if segs[i][1] == "''" else segs[i][1]) for i in idx]
    ref = tokens(note_html)
    # the leading '(N) ' belongs to the converter, HavAll has '[~N.~]' there
    start = len('(%s) ' % LINE_NUM_RE.match(line).group(1))
    sm = difflib.SequenceMatcher(None, cur[start:], [t[0] for t in ref], autojunk=False)
    # a note of another text (the numbers of some masechtot do not line up) must not lend its bold
    if sm.quick_ratio() < SIMILAR or sm.ratio() < SIMILAR:
        return None
    ops = sm.get_opcodes()
    real = real_bold(ref)
    bolded = quotes = 0
    for tag, i1, i2, j1, j2 in ops:
        if tag != 'equal':
            continue
        for k in range(i2 - i1):
            seg = segs[idx[start + i1 + k]]
            rtok, rbold, rraw = ref[j1 + k]
            if rbold and (j1 + k) in real and not seg[2] and not seg[1].isspace():
                seg[2] = 'add'
                stats['bold:' + rtok] += 1
                bolded += 1
            if seg[1] == "''" and rraw == '"':
                seg[1] = '"'
                stats['quote'] += 1
                quotes += 1
    unmatched = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag != 'equal')
    rebuilt = []
    for s in segs:
        if s[0] == 'tag':
            rebuilt.append(s[1])
        elif s[2] == 'add':
            rebuilt.append('<b>%s</b>' % s[1])
        else:
            rebuilt.append(s[1])
    new = ''.join(rebuilt)
    while '</b><b>' in new:
        new = new.replace('</b><b>', '')
    return new, bolded, quotes, unmatched


def books(src):
    names = json.load(open(os.path.join(HERE, 'te_books.json'), encoding='utf-8'))
    for rel, ent in names.items():
        if f'/{NOTES_DIR}/' in rel and ent['src'].endswith('HavTempNotes.txt'):
            yield rel, os.path.join(src, os.path.dirname(ent['src']), 'HavAll.txt')


GAP_MID_RE = re.compile(r'(?<=[א-ת])</b>([יגפ]+)<b>(?=[א-ת])')
GAP_END_RE = re.compile(r'(?<=[א-ת])</b>([יגפ]+)(?![א-ת"\'])')


def fill_gaps(line):
    """A yod/gimel/peh the bold of its own word left out: <b>מאיר</b>י -> <b>מאירי</b>"""
    return GAP_END_RE.sub(r'\1</b>', GAP_MID_RE.sub(r'\1', line))


def run_gaps(write, only):
    names = json.load(open(os.path.join(HERE, 'te_books.json'), encoding='utf-8'))
    total = 0
    for rel in names:
        if 'חברותא' not in rel or (only and only not in rel):
            continue
        path = os.path.join(LIB, rel)
        lines = open(path, encoding='utf-8').read().split('\n')
        new = [fill_gaps(l) for l in lines]
        n = sum(a != b for a, b in zip(lines, new))
        if n:
            print(f'{os.path.basename(path)}: {n} lines changed')
            total += n
            if write:
                with open(path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write('\n'.join(new))
    print(f'{total} lines changed')
    return 0


def plain(s):
    return ''.join(t[0] for t in tokens(s))


def run(src, write, only):
    bad = False
    for rel, allpath in books(src):
        if only and only not in rel:
            continue
        path = os.path.join(LIB, rel)
        lines = open(path, encoding='utf-8').read().split('\n')
        notes = all_notes(read_all(allpath))
        stats = collections.Counter()
        book_bad = False
        changed = missing = unaligned = other = count = 0
        for n, line in enumerate(lines):
            m = LINE_NUM_RE.match(line)
            if not m:
                continue
            num = int(m.group(1))
            count += 1
            if num not in notes:
                missing += 1
                continue
            res = restore_line(line, notes[num], stats)
            if res is None:
                other += 1
                continue
            new, bolded, quotes, un = res
            if plain(new) != plain(line):
                print(f'  FAIL {os.path.basename(path)} line {n + 1}: the text would change')
                bad = book_bad = True
                continue
            if un:
                unaligned += 1
            if new != line:
                changed += 1
                lines[n] = new
        if other > MAX_OTHER * count or missing:
            # HavAll does not hold this book's notes (or numbers them differently): nothing to restore from
            print(f'{os.path.basename(path)}: skipped, HavAll has other text for {other} of {count} notes')
            continue
        print(f'{os.path.basename(path)}: {changed} lines changed, bold {sum(v for k, v in stats.items() if k.startswith("bold:"))}'
              f' ({", ".join(f"{k[5:]}={v}" for k, v in stats.most_common() if k.startswith("bold:"))}), '
              f'quotes {stats["quote"]}, not in HavAll {missing}, other text in HavAll {other}, lines with unaligned text {unaligned}')
        if write and not book_bad:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(lines))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--src', help='the Torat Emet books directory (not needed with --gaps)')
    ap.add_argument('--gaps', action='store_true', help='bold the yod/gimel/peh a bold word left out, in every Chavruta book')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', action='store_true')
    g.add_argument('--write', action='store_true')
    ap.add_argument('--only', help='a part of the book name')
    a = ap.parse_args()
    if a.gaps:
        sys.exit(run_gaps(a.write, a.only))
    if not a.src:
        ap.error('--src is required without --gaps')
    sys.exit(run(os.path.join(a.src, ''), a.write, a.only))


if __name__ == '__main__':
    main()
