#!/usr/bin/env python3
"""QA for convert_pdf.py output. Prints only structure/counts (no Hebrew)."""
import sys, os, re, json, glob, collections, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import convert_pdf as C
from kskdec import decode_file

GEM = dict(zip('אבגדהוזחטיכלמנסעפצקרשת', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))
GEM.update({'ך': 20, 'ם': 40, 'ן': 50, 'ף': 80, 'ץ': 90})
VALIDATOR = os.environ.get('KSK_VALIDATOR', os.path.join(
    os.environ.get('KSK_REPO', os.path.dirname(os.path.dirname(HERE))),
    '.claude', 'skills', 'otzaria-book-format', 'scripts', 'validate_book.py'))


def gem(s):
    return sum(GEM.get(c, 0) for c in s)


def daf_seq(h2s):
    """h2 list -> list of numeric positions (daf*2 + amud) or (perek, mishna)."""
    out = []
    for h in h2s:
        w = re.sub('<.*?>', '', h).split(' ')
        if w[0] == C.PEREK_WORD:
            out.append(gem(w[1]) * 100 + gem(w[3])); continue
        t = re.sub('<.*?>', '', h).split(' ', 1)[1] if ' ' in h else h
        t = re.sub('<.*?>', '', t)
        if t.endswith('.') or t.endswith(':'):
            out.append(gem(t[:-1]) * 2 + (0 if t.endswith('.') else 1))
        else:
            p, m = t.split(' ')
            out.append(gem(p[1:]) * 100 + gem(m[1:]))
    return out


def gaps(seq, pm=False):
    g = []; dup = []
    for a, b in zip(seq, seq[1:]):
        if b == a:
            dup.append(a)
        elif pm:
            if not (b == a + 1 or (b // 100 == a // 100 + 1 and b % 100 == 1)):
                g.append((a, b))
        elif b != a + 1:
            g.append((a, b))
    return g, dup


def norm(s):
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'[֑-ׇ]', '', s)
    s = re.sub(r'[^א-ת0-9 ]', ' ', s)
    return s.split()


def shingles(words, n=5):
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def coverage(a_lines, b_set, b_short, n=5, thr=0.7):
    ok = 0; tot = 0
    for l in a_lines:
        w = norm(l)
        if not w:
            continue
        tot += 1
        if len(w) < n:
            ok += ' '.join(w) in b_short
            continue
        sh = shingles(w, n)
        ok += sum(1 for x in sh if x in b_set) / len(sh) >= thr
    return ok, tot


def body_of(lines):
    return [l for l in lines[1:] if l.strip() and not l.startswith('<h') and l != C.COPYRIGHT_LINE]


def qa(key):
    idxs, oldtr = C.BOOKS[key]
    new = open(os.path.join(C.OUT, key + '.txt'), encoding='utf-8').read()
    NL = new.rstrip('\n').split('\n')
    r = {}
    r['lines'] = len(NL)
    r['line1_h1'] = NL[0].startswith('<h1>') and NL[0].endswith('</h1>')
    r['line2_author'] = NL[1] == C.AUTHOR
    r['line3_copyright'] = NL[2] == C.COPYRIGHT_LINE
    r['empty_lines_after_2'] = sum(1 for l in NL[2:] if not l.strip())
    unbal = 0
    for l in NL:
        if l == C.COPYRIGHT_LINE:
            continue
        for t in ('b', 'h1', 'h2', 'h3'):
            if l.count('<' + t + '>') != l.count('</' + t + '>'):
                unbal += 1
        if re.search(r'<(?!/?(b|h1|h2|h3|tr|/td|/table)>|td[ >]|table border="1">)', l):
            unbal += 1
    r['unbalanced_or_stray_tags'] = unbal
    r['h2'] = sum(1 for l in NL if l.startswith('<h2>'))
    r['h3'] = sum(1 for l in NL if l.startswith('<h3>'))
    r['b_lines'] = sum(1 for l in NL if l.startswith('<b>') and l.endswith('</b>') and l.count('<b>') == 1)
    r['bold_tags'] = new.count('<b>')
    r['unknown_glyph_residue'] = len(re.findall(r'\{[A-Za-z0-9]+\}', new))
    r['max_line_len'] = max(len(l) for l in NL)
    # heading order: h3 directly after h1 without h2
    first_h = [l[:4] for l in NL if l.startswith('<h')][:3]
    r['first_headings'] = first_h
    h2s = [l for l in NL if l.startswith('<h2>')]
    pm = re.sub('<.*?>', '', h2s[0]).startswith(C.PEREK_WORD) or ' ' in re.sub('<.*?>', '', h2s[0]).split(' ', 1)[1]
    seq = daf_seq(h2s)
    g, dup = gaps(seq, pm)
    r['daf_first_last'] = (seq[0], seq[-1]); r['daf_gaps'] = g; r['daf_dups'] = dup
    # ---- old file
    old = [f for f in glob.glob(C.OLD_ROOT + '/*/*/*.txt') if C.tr(os.path.basename(f)).endswith(' el ' + oldtr + '.txt')]
    if old:
        OL = open(old[0], encoding='utf-8').read().rstrip('\n').split('\n')
        r['old_h1_equal'] = OL[0] == NL[0]
        oh2 = [l for l in OL if l.startswith('<h2>')]
        r['old_h2'] = len(oh2); r['h2_identical_to_old'] = oh2 == h2s
        if oh2 != h2s:
            so = set(oh2); sn = set(h2s)
            r['h2_only_old'] = [C.tr(x) for x in oh2 if x not in sn][:10]
            r['h2_only_new'] = [C.tr(x) for x in h2s if x not in so][:10]
        oh3 = collections.Counter(l for l in OL if l.startswith('<h3>'))
        nh3 = collections.Counter(l for l in NL if l.startswith('<h3>'))
        r['old_h3'] = sum(oh3.values())
        r['h3_multiset_overlap_pct'] = round(100 * sum((oh3 & nh3).values()) / max(1, sum(oh3.values())), 1)
        # h3 sequence alignment per amud: fraction of amudim whose h3 sequence is identical
        def per_amud(L):
            d = collections.OrderedDict(); cur = None
            for l in L:
                if l.startswith('<h2>'):
                    cur = l; d.setdefault(cur, [])
                elif l.startswith('<h3>') and cur:
                    d[cur].append(l)
            return d
        po, pn = per_amud(OL), per_amud(NL)
        same = sum(1 for k in po if k in pn and po[k] == pn[k])
        r['amudim_same_h3_sequence_pct'] = round(100 * same / max(1, len(po)), 1)
        ob = body_of(OL); nb = body_of(NL)
        nw = [norm(l) for l in nb]; ow = [norm(l) for l in ob]
        nset = set().union(*[shingles(w) for w in nw]); oset = set().union(*[shingles(w) for w in ow])
        nshort = {' '.join(w) for w in nw}; oshort = {' '.join(w) for w in ow}
        a, t = coverage(ob, nset, nshort)
        r['old_body_lines_matched_in_new_pct'] = round(100 * a / t, 2); r['old_body_lines'] = t
        a, t = coverage(nb, oset, oshort)
        r['new_body_lines_matched_in_old_pct'] = round(100 * a / t, 2); r['new_body_lines'] = t
        r['old_words'] = sum(len(w) for w in ow); r['new_words'] = sum(len(w) for w in nw)
        # exact paragraph identity (normalized, tags removed)
        so = {' '.join(w) for w in ow}
        r['new_body_lines_exact_in_old_pct'] = round(100 * sum(1 for w in nw if ' '.join(w) in so) / len(nw), 2)
        # geresh/gershayim style
        r['old_gershayim_ascii'] = sum(l.count('"') for l in ob); r['new_gershayim_ascii'] = sum(l.count('"') for l in nb)
        r['old_U05F4'] = sum(l.count('״') + l.count('׳') for l in ob)
        r['new_U05F4'] = sum(l.count('״') + l.count('׳') for l in nb)
    # ---- decoded words vs output words
    manifest = json.load(open(os.path.join(C.WORK, 'manifest.json')))
    dec = collections.Counter(); hdr = collections.Counter(); front = collections.Counter()
    header_strings = collections.Counter()
    for ix in idxs:
        pages = decode_file(manifest[str(ix)]['path'], os.path.join(C.WORK, 'work', 'dec', f'{ix}.jsonl.gz'))
        start = next(i for i, pg in enumerate(pages) if any(34 < l['size'] < 38 for l in pg))
        for pi, pg in enumerate(pages):
            for l in pg:
                t = ''.join(sp[1] for sp in l['spans'])
                w = norm(t)
                if pi < start:
                    front.update(w)
                elif l['y'] < 80:
                    hdr.update(w)
                    if l['size'] > 20:
                        header_strings[t.strip()] += 1
                else:
                    dec.update(w)
    out = collections.Counter()
    for l in NL[1:]:
        out.update(norm(l))
    r['decoded_body_words'] = sum(dec.values()); r['output_words'] = sum(out.values())
    r['front_matter_words_dropped'] = sum(front.values()); r['running_header_words_dropped'] = sum(hdr.values())
    miss = dec - out; extra = out - dec
    r['body_words_missing_in_output'] = sum(miss.values())
    r['output_words_not_in_decoded'] = sum(extra.values())
    r['top_missing_tokens_translit'] = [(C.tr(k), v) for k, v in miss.most_common(6)]
    # tokens of >= 3 letters: excludes daf-marker pieces (1-2 letters) moved into h2
    r['missing_tokens_len3plus'] = sum(v for k, v in miss.items() if len(k) >= 3)
    r['extra_tokens_len3plus'] = sum(v for k, v in extra.items() if len(k) >= 3)
    r['top_missing_len3plus_translit'] = [(C.tr(k), v) for k, v in miss.most_common() if len(k) >= 3][:6]
    r['top_extra_tokens_translit'] = [(C.tr(k), v) for k, v in extra.most_common(4)]
    # header residue: running-header strings (series/tractate title) as a whole line or glued to text
    hs = [h for h, c in header_strings.most_common(3)]
    r['header_strings_translit'] = [C.tr(h) for h in hs]
    body_txt = '\n'.join(NL[1:])
    r['header_string_occurrences_in_output'] = {C.tr(h): body_txt.count(h) for h in hs}
    dec_txt_counts = {}
    for ix in idxs:
        pages = decode_file(manifest[str(ix)]['path'], os.path.join(C.WORK, 'work', 'dec', f'{ix}.jsonl.gz'))
        start = next(i for i, pg in enumerate(pages) if any(34 < l['size'] < 38 for l in pg))
        for pg in pages[start:]:
            for l in pg:
                if l['y'] >= 80 and l['size'] < 14.5:
                    t = ''.join(sp[1] for sp in l['spans'])
                    for h in hs:
                        dec_txt_counts[C.tr(h)] = dec_txt_counts.get(C.tr(h), 0) + t.count(h)
    r['header_string_occurrences_in_decoded_body'] = dec_txt_counts
    # validator
    try:
        p = subprocess.run([sys.executable, VALIDATOR, os.path.join(C.OUT, key + '.txt')], capture_output=True, text=True, timeout=300)
        o = re.sub(r'[֐-׿]+', '*', (p.stdout + p.stderr))
        r['validator_rc'] = p.returncode; r['validator_tail'] = o.strip().split('\n')[-6:]
    except Exception as e:
        r['validator_rc'] = str(e)
    return r


if __name__ == '__main__':
    keys = sys.argv[1:] or list(C.BOOKS)
    allr = {}
    for k in keys:
        allr[k] = qa(k)
        print(k, json.dumps(allr[k], ensure_ascii=False))
    json.dump(allr, open(os.path.join(C.OUT, 'qa.json'), 'w'), indent=1)
