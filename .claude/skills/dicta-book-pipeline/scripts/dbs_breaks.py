#!/usr/bin/env python3
"""dbs_breaks.py - אבחון ותיקון שורות שבורות וכותרות קטועות בספרי DBS שנוספו ל-ערוך.

רקע: קבצי DBS שהועתקו כמו שהם ל-DictaToOtzaria/ערוך (קומיט "הוספת ספרים מדיקטה")
שומרים שבירת שורות של הדפוס: משפט נקטע באמצע ונמשך בשורה הבאה, וכותרות (h) נחתכות
באורך קבוע (~47 תווים) או שהמשכן נשאר בשורה נפרדת. הגרסה הגולמית של אותו ספר
(extraBooks/דיקטה או DictaToOtzaria/לא ערוך) משמשת כ"עד": אם בגולמי שני קצוות
שורה DBS עומדים באותה שורה - השבירה מלאכותית.

שימוש:
  dbs_breaks.py scan  [--commit b9ce756e] [--out report.json]
  dbs_breaks.py fix   [--commit b9ce756e] [--out report.json]    (כותב לקבצים!)

תיקונים אוטומטיים (בטוחים בלבד):
  1. איחוד שורות: שורה A שלא מסתיימת בפיסוק סוף + שורה B, כשבגולמי רצף המילים
     (3 אחרונות של A + 3 ראשונות של B) נמצא בתוך שורה אחת, וכל ההתאמות בגולמי מסכימות.
  2. כותרת ש"נחתכה": כשהגולמי מראה שהכותרת (עד מילה חלקית) היא תחילת רצף שורות
     הגולמי, וגוף ה-DBS שאחריה מתחיל בדיוק בתחילת שורה בגולמי - משלימים מהגולמי.
  3. סוגריים הפוכים בכותרת (`]אות א[`, `)נוסח(`): מחליפים כשההיפוך מאזן את הכותרת.
  איחוד שורות מזיז מספרי שורות, ולכן ספר שיש לו קובץ links (בשורשי ה-links שארוזים)
  לא מאוחד - הסקריפט מדווח עליו בלבד.

מה לא מתוקן (רק מדווח): כותרות שהמשכן בגוף בלי עד בגולמי, כותרת שנוצרה מחתיכת שורת גוף,
שורות לא-מסתיימות שאין להן עד בגולמי, אובדן מילה ראשונה בכותרות, `&amp;`.
"""
import argparse, collections, html, json, os, re, subprocess, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
DEFAULT_EXCLUDE = ['אורח משפט', 'עט סופר', 'משמרת אלעזר', 'אלפי מנשה', 'כתר המלך',
                   'נתיב מאיר', 'תבואות השדה', 'העיטור']
RAW_DIRS = ['extraBooks/דיקטה', 'DictaToOtzaria/לא ערוך']
EDITED_PREFIX = 'DictaToOtzaria/ערוך/ספרים/'

TAG = re.compile(r'<[^>]+>')
HRE = re.compile(r'^<h([1-6])>(.*)</h\1>$')
TOKCH = re.compile(r'[^א-ת0-9A-Za-z]')
TERM = re.compile(r'[.:?!;׃]["\'”’»)\]׳״]*$')


def plain(s):
    return html.unescape(TAG.sub('', s))


def toks(s):
    out = []
    for w in plain(s).split():
        w = TOKCH.sub('', w)
        if w:
            out.append(w)
    return out


def terminated(line):
    return bool(TERM.search(plain(line).rstrip()))


def is_body(line):
    return bool(line.strip()) and not line.startswith('<h')


# ---------------------------------------------------------------- raw index
class RawIndex:
    def __init__(self, path):
        self.path = path
        self.lines = open(path, encoding='utf-8').read().split('\n')
        self.T, self.start, self.lineno = [], [], []
        for n, l in enumerate(self.lines):
            for k, w in enumerate(toks(l)):
                self.T.append(w)
                self.start.append(k == 0)
                self.lineno.append(n)
        self.bi = collections.defaultdict(list)
        for i in range(len(self.T) - 1):
            self.bi[(self.T[i], self.T[i + 1])].append(i)

    def joined(self, A, B):
        """A, B: token lists של שתי שורות גוף רצופות ב-DBS -> join / break / unknown / ambig"""
        if not A or not B:
            return 'unknown'
        t, h = A[-3:], B[:3]
        W = t + h
        if len(W) < 4:
            return 'unknown'
        res = set()
        for q in self.bi.get((t[-1], h[0]), []):
            i = q - (len(t) - 1)
            if i < 0 or self.T[i:i + len(W)] != W:
                continue
            res.add('break' if self.start[q + 1] else 'join')
        if len(res) == 1:
            return res.pop()
        if res:
            return 'ambig'
        # רמה שנייה: DBS לפעמים קוצץ/משבש מילה בקצה השורה, אז מסתפקים ב-2+2 מילים,
        # אבל רק אם ההתאמה יחידה בכל הגולמי (אין מקום לבלבול בין מופעים)
        if len(A) >= 2 and len(B) >= 2:
            t, h = A[-2:], B[:2]
            W = t + h
            hits = [q for q in self.bi.get((t[-1], h[0]), [])
                    if q - 1 >= 0 and self.T[q - 1:q - 1 + 4] == W]
            if len(hits) == 1 and not self.start[hits[0] + 1]:
                return 'join'
        return 'unknown'

    def heading_status(self, h, b):
        """h: טוקני כותרת (DBS), b: טוקני שורת הגוף שאחריה.
        -> ('ok'|'trunc'|'notfound'|'ambig'|'skip', info)"""
        n = len(h)
        if n < 2 or len(b) < 3:
            return 'skip', None
        b4 = b[:4]
        T = self.T
        found = [q for q in self.bi.get((h[0], h[1]), [])
                 if T[q:q + n - 1] == h[:-1] and q + n - 1 < len(T) and T[q + n - 1].startswith(h[-1])]
        if not found:
            return 'notfound', None
        outs, info = set(), None
        for q in found:
            end = q + n
            rem = T[q + n - 1][len(h[-1]):]
            if rem == '' and T[end:end + len(b4)] == b4:
                outs.add('ok')
                continue
            for j in range(40):
                k = end + j
                if k + len(b4) > len(T):
                    break
                if T[k:k + len(b4)] == b4 and self.start[k] and (j > 0 or rem != ''):
                    outs.add('trunc')
                    info = (q, k)
                    break
            else:
                outs.add('other')
        if outs == {'trunc'}:
            return 'trunc', info
        if outs == {'ok'}:
            return 'ok', None
        return 'ambig', sorted(outs)

    def heading_midline(self, h):
        """הכותרת מופיעה בגולמי באמצע שורה (לא בתחילתה) - סימן לכותרת שנוצרה מחתיכת גוף."""
        n = len(h)
        if n < 4:
            return False
        T = self.T
        occ = [q for q in self.bi.get((h[0], h[1]), [])
               if T[q:q + n - 1] == h[:-1] and q + n - 1 < len(T) and T[q + n - 1].startswith(h[-1])]
        return len(occ) == 1 and not self.start[occ[0]]


# ------------------------------------------------------------------ helpers
def git(*a):
    return subprocess.run(['git', '-c', 'core.quotepath=off', *a], cwd=REPO,
                          capture_output=True, text=True, check=True).stdout


def books_of_commit(commit, exclude):
    out = git('show', '--name-only', '--diff-filter=A', '--format=', commit).split('\n')
    res = []
    for p in out:
        if p.startswith(EDITED_PREFIX) and p.endswith('.txt') and os.path.exists(os.path.join(REPO, p)):
            if not any(e in p for e in exclude):
                res.append(p)
    return res


def raw_files():
    d = collections.defaultdict(list)
    for root in RAW_DIRS:
        for r, _, fs in os.walk(os.path.join(REPO, root)):
            for f in fs:
                if f.endswith('.txt'):
                    d[f].append(os.path.join(r, f))
    return d


def find_raw_by_content(path, allraw, cache):
    """גיבוי כשאין שם קובץ זהה: חיפוש 4 ביטויים אקראיים מהגוף בכל הגולמיים."""
    import random
    rnd = random.Random(7)
    L = [l for l in open(os.path.join(REPO, path), encoding='utf-8').read().split('\n')
         if is_body(l) and len(l) > 120]
    phr = []
    for l in rnd.sample(L, min(4, len(L))):
        w = plain(l).split()
        k = len(w) // 2
        phr.append(' '.join(w[k:k + 4]))
    best, bn = None, 0
    for f in allraw:
        if f not in cache:
            cache[f] = open(f, encoding='utf-8').read()
        n = sum(1 for s in phr if s in cache[f])
        if n > bn:
            best, bn = f, n
    return best if bn >= 3 else None


def links_index():
    """שם ספר -> קבצי links (שורשים שארוזים) שבהם הוא מצטט או מצוטט."""
    conf = json.load(open(os.path.join(REPO, 'manual_links_sync.json')))
    idx = collections.defaultdict(list)
    for r in conf['links_roots']:
        if r['expected_state'] != 'present':
            continue
        d = os.path.join(REPO, r['path'])
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith('_links.json'):
                continue
            fp = os.path.join(r['path'], f)
            idx[f[:-len('_links.json')]].append(fp)
            try:
                data = json.load(open(os.path.join(REPO, fp), encoding='utf-8'))
            except Exception:
                continue
            for t in {os.path.splitext(os.path.basename(x.get('path_2', '')))[0] for x in data}:
                idx[t].append(fp)
    return idx


def fix_brackets(t):
    """מחליף סוגריים הפוכים אם ההיפוך מאזן את הכותרת (או מבטל עומק שלילי)."""
    def depth_ok(s):
        d = 0
        for ch in s:
            if ch in '([':
                d += 1
            elif ch in ')]':
                d -= 1
                if d < 0:
                    return False
        return True
    if not re.search(r'[\)\]]', t):
        return t
    if depth_ok(t):
        return t
    sw = t.translate(str.maketrans('()[]', ')(]['))
    # החלפה מלאה הופכת גם סוגריים תקינים; מבצעים רק אם התוצאה מאוזנת
    if depth_ok(sw) and sw.count('(') == sw.count(')') and sw.count('[') == sw.count(']'):
        return sw
    return t


# --------------------------------------------------------------- main logic
def process(path, ri, apply, block_merge):
    full = os.path.join(REPO, path)
    src = open(full, encoding='utf-8', newline='').read()
    L = src.split('\n')
    st = collections.Counter()
    ex = collections.defaultdict(list)

    def note(kind, i, text):
        st[kind] += 1
        if len(ex[kind]) < 4:
            ex[kind].append([i + 1, text[:70]])

    h1 = None
    fixes_h = 0

    def lost_first(h1, t):
        hw, tw = h1.split(), t.split()
        return (len(hw) > 1 and bool(tw) and tw[0] == hw[1] and tw[0] != hw[0]
                and hw[0] != 'ספר' and not hw[0].startswith('('))
    # כותרות שאיבדו את המילה הראשונה של שם הספר: מתקנים רק כשהדפוס שיטתי (>=90% מכותרות הקובץ)
    pre_h1, n_sub, n_lost = None, 0, 0
    for l in L:
        m = HRE.match(l)
        if not m:
            continue
        if m.group(1) == '1':
            pre_h1 = m.group(2).strip()
        else:
            n_sub += 1
            if pre_h1 and lost_first(pre_h1, m.group(2).strip()):
                n_lost += 1
    lost_systematic = n_sub >= 5 and n_lost >= 0.9 * n_sub
    # ---- כותרות
    for i, l in enumerate(L):
        if not l.startswith('<h'):
            continue
        m = HRE.match(l)
        if not m:
            note('h_unclosed', i, l)
            continue
        lv, t = m.group(1), m.group(2).strip()
        if lv == '1':
            h1 = t
            continue
        if re.search(r'[-–,(\[]$', t):
            note('h_trailing_joiner', i, t)
        if t != fix_brackets(t):
            note('h_reversed_brackets', i, t)
            if apply:
                L[i] = '<h%s>%s</h%s>' % (lv, fix_brackets(t), lv)
                fixes_h += 1
                t = fix_brackets(t)
        elif t.count('(') != t.count(')') or t.count('[') != t.count(']'):
            note('h_unbalanced', i, t)
        if len(t) in (47, 48) or len(t) >= 44 and not re.search(r'[.:?!)\]]$', t):
            note('h_len_suspect', i, t)
        lost_here = bool(h1) and lost_first(h1, t)
        if lost_here:
            note('h_lost_first_word_fixable' if lost_systematic else 'h_lost_first_word', i, t)
        if ri and i + 1 < len(L) and is_body(L[i + 1]):
            s, info = ri.heading_status(toks(t), toks(L[i + 1]))
            if s == 'trunc':
                q, k = info
                span = range(ri.lineno[q], ri.lineno[k - 1] + 1)
                allbold = all(re.sub(r'<[^>]+>', '', re.sub(r'<(b|big)>.*?</\1>', '', ri.lines[n])).strip(' \t.,:;') == ''
                              for n in span)
                if len(t) >= 40 and ri.start[q] and len(span) <= 3 and k - q <= 25 and allbold:
                    new = ' '.join(plain(ri.lines[n]).strip() for n in range(ri.lineno[q], ri.lineno[k - 1] + 1))
                    new = re.sub(r'\s+', ' ', new).strip().rstrip(':').strip()
                    note('h_truncated_fixable', i, '%s => %s' % (t, new))
                    if apply:
                        L[i] = '<h%s>%s</h%s>' % (lv, new, lv)
                        fixes_h += 1
                else:
                    note('h_truncated_manual', i, t)
            elif ri.heading_midline(toks(t)) and len(t) >= 40:
                note('h_from_body_fragment', i, t)
    if apply and lost_systematic:
        h1 = None
        for i, l in enumerate(L):
            m = HRE.match(l)
            if not m:
                continue
            if m.group(1) == '1':
                h1 = m.group(2).strip()
            elif h1 and lost_first(h1, m.group(2).strip()):
                L[i] = '<h%s>%s %s</h%s>' % (m.group(1), h1.split()[0], m.group(2).strip(), m.group(1))
                fixes_h += 1
    # ---- שורות גוף
    merged = 0
    n_body_pairs = 0
    out = []
    i = 0
    while i < len(L):
        cur = L[i]
        i += 1
        while is_body(cur) and i < len(L) and is_body(L[i]):
            nxt = L[i]
            n_body_pairs += 1
            if terminated(cur):
                break
            j = ri.joined(toks(cur), toks(nxt)) if ri else 'noraw'
            if j == 'join' and not re.search(r'\S[-־]$', cur.rstrip()) and not block_merge:
                note('b_broken_fixable', i - 1, plain(cur)[-25:] + ' || ' + plain(nxt)[:25])
                cur = cur.rstrip() + ' ' + nxt.lstrip()
                i += 1
                merged += 1
                continue
            if j == 'join':
                note('b_broken_blocked_links' if block_merge else 'b_broken_ends_hyphen',
                     i - 1, plain(cur)[-25:] + ' || ' + plain(nxt)[:25])
            elif j == 'break':
                st['b_unterminated_raw_also_breaks'] += 1
            else:
                note('b_unterminated_no_evidence', i - 1, plain(cur)[-25:] + ' || ' + plain(nxt)[:25])
            break
        out.append(cur)
    body = [l for l in L if is_body(l)]
    st['amp_leftover'] = sum(l.count('&amp;') for l in L)
    res = {'lines': len(L), 'body_lines': len(body), 'body_pairs': n_body_pairs,
           'merged': merged, 'heading_fixes': fixes_h,
           'stats': dict(st), 'examples': {k: v for k, v in ex.items()}}
    if apply and (merged or fixes_h):
        open(full, 'w', encoding='utf-8', newline='').write('\n'.join(out))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['scan', 'fix'])
    ap.add_argument('--commit', default='b9ce756e')
    ap.add_argument('--out', default='dbs_breaks_report.json')
    ap.add_argument('--exclude', nargs='*', default=DEFAULT_EXCLUDE)
    a = ap.parse_args()
    apply = a.mode == 'fix'
    books = books_of_commit(a.commit, a.exclude)
    raws = raw_files()
    allraw = [f for v in raws.values() for f in v]
    cache = {}
    lidx = links_index()
    report = {}
    for p in books:
        b = os.path.basename(p)
        title = b[:-4]
        cands = raws.get(b) or []
        rp = cands[0] if cands else find_raw_by_content(p, allraw, cache)
        ri = RawIndex(rp) if rp else None
        blocked = bool(lidx.get(title))
        r = process(p, ri, apply, blocked)
        r['raw'] = os.path.relpath(rp, REPO) if rp else None
        r['links_files'] = lidx.get(title, [])
        report[p] = r
    json.dump(report, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tot = collections.Counter()
    for r in report.values():
        for k, v in r['stats'].items():
            tot[k] += v
        tot['merged'] += r['merged']
        tot['heading_fixes'] += r['heading_fixes']
    print('books scanned: %d, without raw: %d' % (len(report), sum(1 for r in report.values() if not r['raw'])))
    for k, v in sorted(tot.items()):
        print('%-36s %d' % (k, v))


if __name__ == '__main__':
    main()
