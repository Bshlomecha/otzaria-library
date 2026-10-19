#!/usr/bin/env python3
"""Split giant paragraphs in packaged books and remap every line reference to them.

A paragraph of more than 50,000 visible chars freezes the reader (Otzaria/otzaria#1941).
A non-heading line over --min-chars is cut into pieces of about --target visible chars,
only where no tag but a whole-line wrapper is open, preferring <br>, then ": ", then
". ", then a space. A whole-line wrapper is closed at the end of each piece and reopened
at the start of the next. In the same run every `_links.json` record (both sides),
`_alt_toc.json` node and `_headings.json` entry that points into a split book is
remapped, so no link breaks.

    python -X utf8 split_long_lines.py --repo <otzaria-library>              # dry run, numbers only
    python -X utf8 split_long_lines.py --repo <otzaria-library> --apply      # write books + sidecars
    python -X utf8 split_long_lines.py --repo <otzaria-library> --roots National-LibraryToOtzaria
    python -X utf8 split_long_lines.py --repo <otzaria-library> --check-changed <base-sha>

Deterministic: the same input always gives the same output, and a second run splits
nothing. The dry run and --apply print only numbers, never book text or titles.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

MIN_CHARS = 50_000
TARGET_CHARS = 20_000
MAX_CHARS = 30_000
MIN_TAIL_CHARS = 10_000

OTZ = 'אוצריא'
# Same order as BOOK_ROOTS in manual_links_packaging.py: a later root overrides an earlier one.
BOOK_SOURCES = [
    'Ben-YehudaToOtzaria', 'DictaToOtzaria/ערוך', 'OnYourWayToOtzaria', 'OraytaToOtzaria',
    'tashmaToOtzaria', 'sefariaToOtzaria/sefaria_export', 'sefariaToOtzaria/sefaria_api', 'MoreBooks', 'KSK',
    'wikiJewishBooksToOtzaria', 'wikisourceToOtzaria', 'ToratEmetToOtzaria', 'pninimToOtzaria',
    'National-LibraryToOtzaria', 'yam-HaHachmaToOtzaria', 'BeitAharonVeYisraelToOtzaria',
]
BOOK_ROOTS = [s + '/ספרים/' + OTZ for s in BOOK_SOURCES]
# Same test as HearotCompanionMerge.isMergeableCompanionTitle in SeforimLibrary.
COMPANION_PREFIX = 'הערות על '
HAVROUTA_PREFIX = 'הערות על חברותא'

VOID_TAGS = {'br', 'hr', 'img', 'wbr', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'source',
             'track', 'param'}
HEADING_TAG = re.compile(r'h[1-6]$')
BR, COLON, PERIOD, SPACE = range(4)  # lower kind wins inside the cut window
KIND_NAMES = ('br', 'colon', 'period', 'space')


@dataclass(frozen=True)
class Config:
    min_chars: int = MIN_CHARS
    target: int = TARGET_CHARS
    max_chars: int = MAX_CHARS
    min_tail: int = MIN_TAIL_CHARS


# ------------------------------------------------------------------ markup scanning

def is_heading(line: str, at: int = 0) -> bool:
    """Same test as the generator's detectHeaderLevel."""
    return len(line) >= at + 3 and line[at] == '<' and line[at + 1] in 'hH' and line[at + 2] in '123456'


def tag_name(tag: str) -> str:
    i = 2 if tag.startswith('</') else 1
    j = i
    while j < len(tag) and (tag[j].isalnum() or tag[j] in '-:'):
        j += 1
    return tag[i:j].lower()


def apply_tag(stack: list, tag: str, seq: int) -> None:
    if tag.startswith('<!') or tag.startswith('<?'):
        return
    name = tag_name(tag)
    if not name:
        return
    if tag.startswith('</'):
        for at in range(len(stack) - 1, -1, -1):
            if stack[at][0] == name:
                del stack[at:]
                break
        return
    if name in VOID_TAGS or tag.endswith('/>'):
        return
    stack.append((name, tag, seq))


def entity_end(line: str, i: int) -> int:
    """`&...;` within 10 chars is one visible char (the generator's countVisibleChars)."""
    end = min(len(line), i + 10)
    for j in range(i + 1, end):
        if line[j] == ';':
            return j
    return i


def common_prefix(a, b) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[n][2] == b[n][2]:
        n += 1
    return n


def visible_len(s: str) -> int:
    n, i, in_tag = 0, 0, False
    while i < len(s):
        c = s[i]
        if in_tag:
            if c == '>':
                in_tag = False
        elif c == '<':
            in_tag = True
        elif c == '&':
            n += 1
            i = entity_end(s, i)
        else:
            n += 1
        i += 1
    return n


def u16_len(s: str) -> int:
    """Kotlin String.length: the generator and link offsets count UTF-16 units."""
    return len(s) + sum(1 for ch in s if ord(ch) > 0xFFFF)


def u16_to_cp(s: str, off: int) -> int:
    if all(ord(ch) <= 0xFFFF for ch in s):
        return off
    n = 0
    for i, ch in enumerate(s):
        if n >= off:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(s)


def cp_to_u16(s: str, off: int) -> int:
    return off + sum(1 for ch in s[:off] if ord(ch) > 0xFFFF)


def word_anchor_ranges(line: str, spans) -> list:
    """Raw Python ranges protected by the generator's UTF-16 word offsets."""
    return [(u16_to_cp(line, int(start)), u16_to_cp(line, int(end))) for start, end in spans]


@dataclass
class Cut:
    end: int      # raw end of the previous piece
    next: int     # raw start of the next piece (a cut <br> or space lies between the two)
    visible: int
    kind: int


def scan(line: str):
    """(total visible, whole-line wrapper, cut candidates), or None for an unterminated tag."""
    wrapper = None
    stack: list = []
    i = 0
    while i < len(line):
        c = line[i]
        if c == '<':
            gt = line.find('>', i)
            if gt < 0:
                return None
            apply_tag(stack, line[i:gt + 1], i)
            i = gt + 1
            continue
        if c == '&':
            i = entity_end(line, i)
        wrapper = list(stack) if wrapper is None else wrapper[:common_prefix(wrapper, stack)]
        i += 1
    wrap = wrapper or []
    # Reopening a footnote or a heading would duplicate the note or create a TOC heading.
    if any('footnote' in t[1] or HEADING_TAG.match(t[0]) for t in wrap):
        return visible_len(line), wrap, []
    cuts: list[Cut] = []
    visible = 0
    stack = []
    i = 0
    while i < len(line):
        c = line[i]
        at_wrapper = len(stack) == len(wrap) and common_prefix(wrap, stack) == len(wrap)
        if c == '<':
            gt = line.find('>', i)
            tag = line[i:gt + 1]
            if tag_name(tag) == 'br' and not tag.startswith('</') and at_wrapper:
                cuts.append(Cut(i, gt + 1, visible, BR))
            apply_tag(stack, tag, i)
            i = gt + 1
            continue
        if c == '&':
            i = entity_end(line, i)
            visible += 1
        else:
            visible += 1
            if c == ' ' and at_wrapper:
                prev = line[i - 1] if i > 0 else ''
                kind = COLON if prev == ':' else PERIOD if prev == '.' else SPACE
                cuts.append(Cut(i, i + 1, visible, kind))  # the space becomes the line break
        i += 1
    return visible, wrap, cuts


@dataclass
class Piece:
    content: str
    src_start: int   # raw offset in the source line where this piece's own text starts
    src_end: int     # raw offset where it ends (exclusive)
    prefix_len: int  # length of the reopened wrapper tags in front


@dataclass
class SplitLine:
    pieces: list
    kinds: list
    openers: str
    closers: str


def needs_split(line: str, cfg: Config = Config()) -> bool:
    return u16_len(line) > cfg.min_chars and not is_heading(line)


def split_line(line: str, cfg: Config = Config(), forbidden=()):
    """(SplitLine, None) or (None, reason). [forbidden]: raw (start, end) ranges no cut may enter."""
    sc = scan(line)
    if sc is None:
        return None, 'unterminated-tag'
    total, wrap, cuts = sc
    if total <= cfg.min_chars:
        return None, 'visible-under-threshold'
    if not cuts:
        return None, 'no-cut-candidate'
    cuts = [c for c in cuts if not any(a < c.next and c.end < b for a, b in forbidden)]
    chosen: list[Cut] = []
    piece_start, frm = 0, 0
    while total - piece_start > cfg.max_chars:
        # Just over max_chars left: a plain target-sized window would be a few chars wide.
        lo = piece_start + min(cfg.target, (total - piece_start) // 2)
        hi = min(piece_start + cfg.max_chars, total - cfg.min_tail)
        best = -1
        i = frm
        while i < len(cuts) and cuts[i].visible <= hi:
            c = cuts[i]
            # A piece opening with <hN> would become a TOC heading.
            # Checked where the next piece really starts: spaces after the cut are dropped.
            start_of_next = c.next
            while start_of_next < len(line) and line[start_of_next] == ' ':
                start_of_next += 1
            opens_heading = not wrap and is_heading(line, start_of_next)
            if c.visible >= lo and not opens_heading and (best < 0 or c.kind < cuts[best].kind):
                best = i
            i += 1
        if best < 0:
            return None, 'no-cut-in-window'
        chosen.append(cuts[best])
        piece_start = cuts[best].visible
        frm = best + 1
    if not chosen:
        return None, 'no-cut-needed'
    openers = ''.join(t[1] for t in wrap)
    closers = ''.join('</%s>' % t[0] for t in reversed(wrap))
    pieces, start = [], 0
    for k, cut in enumerate(chosen):
        # Spaces around the cut would only be trailing/leading whitespace on the new lines.
        end, nxt = cut.end, cut.next
        while end > start and line[end - 1] == ' ':
            end -= 1
        while nxt < len(line) and line[nxt] == ' ':
            nxt += 1
        prefix = '' if k == 0 else openers
        pieces.append(Piece(prefix + line[start:end] + closers, start, end, len(prefix)))
        start = nxt
    pieces.append(Piece(openers + line[start:], start, len(line), len(openers)))
    return SplitLine(pieces, [c.kind for c in chosen], openers, closers), None


def rejoin(sp: SplitLine, line: str) -> str:
    """Undo a split: must give back [line] byte for byte."""
    out = []
    last = len(sp.pieces) - 1
    for k, p in enumerate(sp.pieces):
        body = p.content
        if k > 0:
            if not body.startswith(sp.openers):
                return ''
            body = body[len(sp.openers):]
        if k < last:
            if sp.closers:
                if not body.endswith(sp.closers):
                    return ''
                body = body[:-len(sp.closers)]
            out.append(body + line[p.src_end:sp.pieces[k + 1].src_start])
        else:
            out.append(body)
    return ''.join(out)


def piece_of(sp: SplitLine, raw: int) -> int:
    k = 0
    while k + 1 < len(sp.pieces) and sp.pieces[k + 1].src_start <= raw:
        k += 1
    return k


# ------------------------------------------------------------------ companion merge (HearotCompanionMerge.kt)

NOTE_SMALL_SUP = re.compile(r'^﻿?<small><sup>([^<]+)</sup>\s*')
NOTE_SUP = re.compile(r'^﻿?<sup(?:\s[^>]*)?>([^<]+)</sup>\s*')
NOTE_BARE = re.compile(r'^﻿?(\d+)\s+')


def is_mergeable_companion(title: str) -> bool:
    return title.startswith(COMPANION_PREFIX) and not title.startswith(HAVROUTA_PREFIX)


def note_marker(note: str):
    m = NOTE_SMALL_SUP.match(note)
    if m:
        return m.group(1) if note[m.end():].rstrip().endswith('</small>') else None
    m = NOTE_SUP.match(note) or NOTE_BARE.match(note)
    return m.group(1) if m else None


def find_anchor(line: str, token: str, consumed: list):
    esc = re.escape(token)
    best = None
    for pat in ('<sup>' + esc + '</sup>', r'<sup\s[^>]*>' + esc + '</sup>', r'<small\s[^>]*>\s*' + esc + r'\s*</small>'):
        for m in re.finditer(pat, line):
            a, b = m.start(), m.end() - 1
            if any(x <= b and a <= y for x, y in consumed):
                continue
            if best is None or a < best[0]:
                best = (a, b)
    return best


def merge_notes(line: str, notes: list) -> str:
    """Shape of the generator's merge, enough to prove where each note lands."""
    consumed, places, appendix = [], [], ''
    for note in notes:
        tok = note_marker(note)
        a = find_anchor(line, tok, consumed) if tok is not None else None
        if a is None:
            appendix += '<i class="footnote">' + note.lstrip('﻿') + '</i>'
        else:
            consumed.append(a)
            places.append((a, tok))
    for (a, b), tok in sorted(places, key=lambda x: -x[0][0]):
        line = line[:a] + '<sup class="footnote-marker">' + tok + '</sup><i class="footnote"></i>' + line[b + 1:]
    return line + appendix


def note_pieces(line: str, sp: SplitLine, notes: list) -> list:
    """Piece of each note (notes in line_index_2 order); unanchored notes stay at the line's end."""
    consumed, out = [], []
    for note in notes:
        tok = note_marker(note)
        a = find_anchor(line, tok, consumed) if tok is not None else None
        if a is None:
            out.append(len(sp.pieces) - 1)
        else:
            consumed.append(a)
            out.append(piece_of(sp, a[0]))
    return out


def merge_is_preserved(line: str, sp: SplitLine, notes: list, pieces_of_notes: list) -> bool:
    whole = merge_notes(line, notes)
    parts = []
    for k, p in enumerate(sp.pieces):
        merged = merge_notes(p.content, [n for n, j in zip(notes, pieces_of_notes) if j == k])
        gap = line[p.src_end:sp.pieces[k + 1].src_start] if k + 1 < len(sp.pieces) else ''
        parts.append(merged + gap)
    return ''.join(parts) == whole


# ------------------------------------------------------------------ books

@dataclass
class Book:
    path: str
    title: str
    bom: bool
    newline: str
    lines: list
    split: dict = field(default_factory=dict)   # 0-based source line -> SplitLine
    first: list = field(default_factory=list)   # 0-based source line -> first new line; len = lines + 1

    def finish(self) -> None:
        self.first, acc = [], 0
        for i in range(len(self.lines)):
            self.first.append(acc)
            acc += len(self.split[i].pieces) if i in self.split else 1
        self.first.append(acc)

    def last(self, idx: int) -> int:
        return self.first[idx + 1] - 1

    def new_lines(self) -> list:
        out = []
        for i, ln in enumerate(self.lines):
            if i in self.split:
                out.extend(p.content for p in self.split[i].pieces)
            else:
                out.append(ln)
        return out

    def encode(self) -> bytes:
        return (b'\xef\xbb\xbf' if self.bom else b'') + self.newline.join(self.new_lines()).encode('utf-8')


def title_of(path: str) -> str:
    base = path.replace('\\', '/').rsplit('/', 1)[-1]
    return base[:-4] if base.lower().endswith('.txt') else base


def parse_book(path: str, raw: bytes) -> Book:
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw[3:].decode('utf-8') if bom else raw.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    if newline == '\n' and '\r' in text:
        raise ValueError('bare CR in a book file')
    return Book(path, title_of(path), bom, newline, text.split(newline))


def read_bytes(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def write_bytes(path: str, data: bytes) -> None:
    with open(path, 'wb') as f:
        f.write(data)


def git(repo: str, *args: str) -> bytes:
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, check=True).stdout


def packaged_books(tracked: list) -> dict:
    """Packaged path under אוצריא/ -> repo path; a later root overrides an earlier one."""
    out = {}
    for root in BOOK_ROOTS:
        pre = root + '/'
        for f in tracked:
            if f.startswith(pre) and f.endswith('.txt'):
                out[f[len(pre):]] = f
    return out


# ------------------------------------------------------------------ JSON sidecars

STYLES = [(2, ': ', ','), (1, ': ', ','), (4, ': ', ','), (None, ':', ','), (None, ': ', ', ')]


def detect_style(text: str):
    data = json.loads(text)
    body = text.rstrip('\n')
    for indent, kv, item in STYLES:
        for ascii_only in (False, True):
            if json.dumps(data, ensure_ascii=ascii_only, indent=indent, separators=(item, kv)) == body:
                return indent, kv, item, ascii_only
    return None


def dump(data, style, trailing_newlines: int) -> str:
    indent, kv, item, ascii_only = style
    return json.dumps(data, ensure_ascii=ascii_only, indent=indent, separators=(item, kv)) + '\n' * trailing_newlines


def same_type(old, new: int):
    return float(new) if isinstance(old, float) else new


def with_key_after(rec: dict, after: str, key: str, value) -> dict:
    out = {}
    for k, v in rec.items():
        out[k] = v
        if k == after:
            out[key] = value
    return out


def remap_side(rec: dict, side: int, book: Book, stats, whole_line: str, note_piece=None, anchored=False) -> dict:
    """Remap one side of a link record into [book]'s new numbering. Returns the (maybe new) record."""
    key, end_key = 'line_index_%d' % side, 'line_index_%d_end' % side
    old = rec[key]
    idx = int(old) - 1
    if not 0 <= idx < len(book.lines):
        stats['warn_out_of_range_kept'] += 1
        return rec
    end = int(rec[end_key]) - 1 if end_key in rec else None
    if end is not None and not idx <= end < len(book.lines):
        stats['warn_bad_existing_end_kept'] += 1
        end = None
    new_idx = book.first[idx]
    new_end = book.last(end) if end is not None else None
    add_end = None
    if idx in book.split:
        sp = book.split[idx]
        if anchored:
            line = book.lines[idx]
            raw = u16_to_cp(line, int(rec['start']))
            k = piece_of(sp, raw)
            p = sp.pieces[k]
            new_idx += k
            rec['start'] = same_type(rec['start'], cp_to_u16(p.content, min(raw, p.src_end) - p.src_start + p.prefix_len))
            if 'end' in rec:
                raw_end = min(u16_to_cp(line, int(rec['end'])), p.src_end)
                rec['end'] = same_type(rec['end'], cp_to_u16(p.content, raw_end - p.src_start + p.prefix_len))
            stats['word_anchor_moved_to_piece'] += 1
        elif note_piece is not None:
            new_idx += note_piece
            stats['footnote_moved_to_marker_piece'] += 1
        elif end is None and whole_line == 'range':
            add_end = book.last(idx)
            stats['whole_line_link_to_range'] += 1
        elif end is None:
            stats['whole_line_link_to_first_piece'] += 1
    if new_idx != idx:
        rec[key] = same_type(old, new_idx + 1)
    if new_end is not None and new_end != end:
        rec[end_key] = same_type(rec[end_key], new_end + 1)
    if add_end is not None:
        rec = with_key_after(rec, key, end_key, same_type(old, add_end + 1))
    return rec


# ------------------------------------------------------------------ the run

def run(repo: str, cfg: Config, whole_line: str = 'range', roots=(), apply: bool = False):
    stats = collections.Counter()
    tracked = [x for x in git(repo, 'ls-files', '-z').decode('utf-8').split('\0') if x]
    packaged = packaged_books(tracked)
    title_count = collections.Counter(title_of(p) for p in packaged.values())
    present = sorted(p for p in packaged.values() if os.path.exists(os.path.join(repo, p)))
    if roots:
        present = [p for p in present if p.split('/')[0] in roots]
    stats['packaged_books_tracked'] = len(packaged)
    stats['packaged_books_scanned'] = len(present)

    docs = {}
    # A tracked links file missing on disk (sparse checkout) would leave its references unmapped.
    missing_links = 0
    for rel in tracked_links_files(repo, tracked):
        path = os.path.join(repo, rel)
        if not os.path.isfile(path):
            missing_links += 1
            continue
        raw = read_bytes(path)
        text = raw.decode('utf-8')
        docs[rel] = {'text': text, 'data': json.loads(text), 'title': title_of(rel)[:-len('_links.json')],
                     'trail': len(raw) - len(raw.rstrip(b'\n')), 'dirty': False}
    stats['links_files_read'] = len(docs)

    anchors = collections.defaultdict(list)
    merged_companions = set()
    for d in docs.values():
        for rec in d['data']:
            if 'start' in rec and 'end' in rec:
                anchors[(d['title'], int(rec['line_index_1']) - 1)].append((rec['start'], rec['end']))
            target = title_of(rec['path_2'])
            # The generator selects companion links by title, regardless of connection type.
            if is_mergeable_companion(target):
                merged_companions.add(target)

    books = {}
    for rel in present:
        book = parse_book(rel, read_bytes(os.path.join(repo, rel)))
        long_idx = [i for i, ln in enumerate(book.lines) if needs_split(ln, cfg)]
        if not long_idx:
            continue
        stats['books_with_long_lines'] += 1
        stats['long_lines'] += len(long_idx)
        if title_count[book.title] > 1:
            stats['skipped_lines:title-not-unique'] += len(long_idx)
            continue
        if book.title in merged_companions:
            # Pieces would be unlinked note lines, and the generator would refuse the whole merge.
            stats['skipped_lines:merged-companion'] += len(long_idx)
            continue
        for i in long_idx:
            line = book.lines[i]
            forbidden = word_anchor_ranges(line, anchors.get((book.title, i), []))
            sp, why = split_line(line, cfg, forbidden)
            if sp is None:
                stats['skipped_lines:' + why] += 1
                continue
            if rejoin(sp, line) != line:
                stats['ERROR_rejoin_mismatch'] += 1
            for p in sp.pieces:
                if is_heading(p.content) or '\n' in p.content or '\r' in p.content:
                    stats['ERROR_piece_is_heading_or_has_newline'] += 1
            book.split[i] = sp
            stats['split_lines'] += 1
            stats['pieces'] += len(sp.pieces)
            for k in sp.kinds:
                stats['cuts:' + KIND_NAMES[k]] += 1
        if book.split:
            book.finish()
            books[book.title] = book
            stats['books_split'] += 1
            stats['books_split:' + rel.split('/')[0]] += 1

    companions = {title_of(p): p for p in packaged.values()}
    for rel, d in docs.items():
        src = books.get(d['title'])
        note_piece = {}
        if src is not None:
            groups = collections.defaultdict(list)
            for n, rec in enumerate(d['data']):
                target = title_of(rec['path_2'])
                idx = int(rec['line_index_1']) - 1
                if is_mergeable_companion(target) and idx in src.split:
                    groups[(idx, target)].append(n)
            for (idx, target), members in groups.items():
                cpath = companions.get(target)
                if cpath is None or not os.path.exists(os.path.join(repo, cpath)):
                    stats['ERROR_companion_book_not_available'] += 1
                    continue
                notes_book = parse_book(cpath, read_bytes(os.path.join(repo, cpath)))
                members.sort(key=lambda n: int(d['data'][n]['line_index_2']))
                notes = []
                for n in members:
                    j = int(d['data'][n]['line_index_2']) - 1
                    notes.append(notes_book.lines[j] if 0 <= j < len(notes_book.lines) else '')
                placed = note_pieces(src.lines[idx], src.split[idx], notes)
                if merge_is_preserved(src.lines[idx], src.split[idx], notes, placed):
                    stats['footnote_merge_proofs_ok'] += 1
                else:
                    stats['ERROR_footnote_merge_proof_failed'] += 1
                note_piece.update(zip(members, placed))
        out = []
        for n, rec in enumerate(d['data']):
            before = json.dumps(rec, sort_keys=True)
            tgt = books.get(title_of(rec['path_2']))
            if src is not None:
                stats['records_side1_in_split_books'] += 1
                rec = remap_side(rec, 1, src, stats, whole_line, note_piece.get(n), anchored='start' in rec)
            if tgt is not None:
                stats['records_side2_in_split_books'] += 1
                if is_mergeable_companion(tgt.title):
                    stats['ERROR_merged_companion_was_split'] += 1
                rec = remap_side(rec, 2, tgt, stats, whole_line)
            if json.dumps(rec, sort_keys=True) != before:
                d['dirty'] = True
                stats['records_changed'] += 1
                stats['records_changed:' + str(rec.get('Conection Type'))] += 1
            out.append(rec)
        d['data'] = out
        if d['dirty']:
            stats['links_files_changed'] += 1
            if detect_style(d['text']) is None:
                stats['ERROR_links_file_style_not_reproducible'] += 1

    sidecars = {}
    for f in tracked:
        if f.endswith('_alt_toc.json') and '/alt_toc/' in f:
            kind, title = 'alt_toc', title_of(f)[:-len('_alt_toc.json')]
        elif f.endswith('_headings.json') and '/links/' in f:
            kind, title = 'headings', title_of(f)[:-len('_headings.json')]
        else:
            continue
        book = books.get(title)
        if book is None:
            continue
        if not os.path.exists(os.path.join(repo, f)):
            stats['ERROR_sidecar_not_checked_out'] += 1
            continue
        raw = read_bytes(os.path.join(repo, f))
        bom = raw.startswith(b'\xef\xbb\xbf')
        text = raw[3:].decode('utf-8') if bom else raw.decode('utf-8')
        data = json.loads(text)
        moved = 0

        def walk(nodes):
            nonlocal moved
            for node in nodes:
                idx = int(node['line']) - 1
                if 0 <= idx < len(book.lines) and book.first[idx] != idx:
                    node['line'] = same_type(node['line'], book.first[idx] + 1)
                    moved += 1
                walk(node.get('children', []))
        if kind == 'alt_toc':
            for structure in data:
                walk(structure.get('nodes', []))
        else:
            for k in list(data):
                idx = int(data[k]) - 1
                if 0 <= idx < len(book.lines) and book.first[idx] != idx:
                    data[k] = same_type(data[k], book.first[idx] + 1)
                    moved += 1
        stats[kind + '_entries_changed'] += moved
        if moved:
            style = detect_style(text)
            if style is None:
                stats['ERROR_sidecar_style_not_reproducible'] += 1
            sidecars[f] = (bom, data, style, len(raw) - len(raw.rstrip(b'\n')))

    for d in docs.values():
        for rec in d['data']:
            for side, title in ((1, d['title']), (2, title_of(rec['path_2']))):
                book = books.get(title)
                if book is None:
                    continue
                key, end_key = 'line_index_%d' % side, 'line_index_%d_end' % side
                for k in (key, end_key):
                    if k in rec and not 1 <= int(rec[k]) <= book.first[-1]:
                        stats['ERROR_remapped_out_of_range'] += 1
                if end_key in rec and int(rec[end_key]) < int(rec[key]):
                    stats['ERROR_reversed_range'] += 1

    if missing_links and books:
        stats['ERROR_tracked_links_files_not_checked_out'] = missing_links
    errors = sum(v for k, v in stats.items() if k.startswith('ERROR'))
    if apply and not errors:
        for book in books.values():
            write_bytes(os.path.join(repo, book.path), book.encode())
        for rel, d in docs.items():
            if d['dirty']:
                text = dump(d['data'], detect_style(d['text']), d['trail'])
                write_bytes(os.path.join(repo, rel), text.encode('utf-8'))
        for f, (bom, data, style, trail) in sidecars.items():
            write_bytes(os.path.join(repo, f), (b'\xef\xbb\xbf' if bom else b'') + dump(data, style, trail).encode('utf-8'))
    return stats, errors, books


def tracked_links_files(repo: str, tracked: list) -> list:
    sync = json.loads(read_bytes(os.path.join(repo, 'manual_links_sync.json')).decode('utf-8'))
    roots = [r['path'] + '/' for r in sync['links_roots']]
    return sorted(f for f in tracked if f.endswith('_links.json')
                  and any(f.startswith(r) and '/' not in f[len(r):] for r in roots))


def companion_is_merged(repo: str, title: str, links_by_title: dict) -> bool:
    """Same rule --apply uses, read from the base book's links file in HEAD."""
    rel = links_by_title.get(title[len(COMPANION_PREFIX):])
    if rel is None:
        return False
    for rec in json.loads(git(repo, 'show', 'HEAD:' + rel).decode('utf-8')):
        if title_of(rec['path_2']) == title:
            return True
    return False


def check_changed(repo: str, base: str, cfg: Config) -> int:
    """Fail when a packaged book changed since [base] has a line that --apply would split; warn on the rest."""
    names = git(repo, 'diff', '--name-only', '--no-renames', '--diff-filter=d', '-z', base, 'HEAD', '--')
    roots = tuple(r + '/' for r in BOOK_ROOTS)
    changed = [n for n in names.decode('utf-8').split('\0') if n.startswith(roots) and n.endswith('.txt')]
    tracked = [x for x in git(repo, 'ls-files', '-z').decode('utf-8').split('\0') if x]
    title_count = collections.Counter(title_of(p) for p in packaged_books(tracked).values())
    links_by_title = {title_of(f)[:-len('_links.json')]: f for f in tracked_links_files(repo, tracked)}
    failed = 0
    for path in changed:
        try:
            book = parse_book(path, git(repo, 'show', 'HEAD:' + path))
        except (ValueError, UnicodeDecodeError):
            continue  # encoding problems are other validators' business
        long_idx = [i for i, ln in enumerate(book.lines) if needs_split(ln, cfg)]
        if not long_idx:
            continue
        anchors = collections.defaultdict(list)
        links = links_by_title.get(book.title)
        if links is not None:
            # Read HEAD, just like the book: CI may have a sparse checkout.
            for rec in json.loads(git(repo, 'show', 'HEAD:' + links).decode('utf-8')):
                if 'start' in rec and 'end' in rec:
                    anchors[int(rec['line_index_1']) - 1].append((rec['start'], rec['end']))
        verdicts = {i + 1: split_line(book.lines[i], cfg,
                                     word_anchor_ranges(book.lines[i], anchors[i]))[1]
                    for i in long_idx}
        splittable = [n for n, why in verdicts.items() if why is None]
        unsplittable = {n: why for n, why in verdicts.items() if why not in (None, 'visible-under-threshold')}
        skip = None
        if title_count[book.title] > 1:
            skip = 'the title is not unique, so --apply skips this book'
        elif is_mergeable_companion(book.title) and companion_is_merged(repo, book.title, links_by_title):
            skip = 'companion notes merged into their base book; split the base line instead'
        if splittable and skip is None:
            failed += 1
            print('error: %s: lines %s are over %d visible chars (Otzaria/otzaria#1941). Run '
                  '.claude/skills/otzaria-book-format/scripts/split_long_lines.py --apply' % (path, splittable[:10], cfg.min_chars))
        elif splittable:
            print('warning: %s: lines %s are over %d visible chars, not split: %s' % (path, splittable[:10], cfg.min_chars, skip))
        for n, why in sorted(unsplittable.items())[:10]:
            print('warning: %s: line %d is over %d visible chars and cannot be cut safely (%s); split it by hand'
                  % (path, n, cfg.min_chars, why))
    print('checked %d changed book(s), %d with lines to split' % (len(changed), failed))
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default='.')
    ap.add_argument('--roots', nargs='*', default=[], help='only books of these source folders (first path part)')
    ap.add_argument('--whole-line-links', choices=('range', 'first'), default='range',
                    help='a link to a whole split line: a range over all its pieces, or its first piece')
    ap.add_argument('--apply', action='store_true', help='write books and sidecars (default: dry run)')
    ap.add_argument('--check-changed', metavar='BASE', help='CI gate: books changed since BASE must not need a split')
    ap.add_argument('--min-chars', type=int, default=MIN_CHARS)
    ap.add_argument('--target', type=int, default=TARGET_CHARS)
    ap.add_argument('--max-chars', type=int, default=MAX_CHARS)
    ap.add_argument('--min-tail', type=int, default=MIN_TAIL_CHARS)
    a = ap.parse_args(argv)
    cfg = Config(a.min_chars, a.target, a.max_chars, a.min_tail)
    if a.check_changed:
        return check_changed(a.repo, a.check_changed, cfg)
    stats, errors, _ = run(a.repo, cfg, a.whole_line_links, tuple(a.roots), a.apply)
    print('mode', 'apply' if a.apply and not errors else 'dry-run', '| whole-line links:', a.whole_line_links)
    for k in sorted(stats):
        print(' ', k if k.isascii() else 'non-ascii-key', stats[k])
    if errors:
        print('errors: %d, nothing written' % errors, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
