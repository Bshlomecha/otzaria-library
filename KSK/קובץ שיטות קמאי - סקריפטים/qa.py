#!/usr/bin/env python3
"""QA for convert_doc.py output. Prints only numbers / masked text.

Per file:
  daf sequence (monotonic/continuous), h2 sequence vs old KSK file
  coverage: word-3-shingle containment old body lines -> new doc, new body lines -> old doc
  h3 agreement: for body lines whose normalized text is identical in old and new,
                does the governing h3 match?
  validate_book.py (json) error/warning counts
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from convert_doc import DOC_IDX, old_file  # noqa: E402
from copyright_line import COPYRIGHT_LINE  # noqa: E402

VALIDATOR = os.environ.get('KSK_VALIDATOR', os.path.join(
    os.environ.get('KSK_REPO', os.path.dirname(os.path.dirname(HERE))),
    '.claude', 'skills', 'otzaria-book-format', 'scripts', 'validate_book.py'))
from convert_doc import WORK  # noqa: E402
OUT = os.path.join(WORK, 'out')


def mask(s):
    return re.sub(r'[֐-׿]+', '*', s)


def normtext(s):
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'[֑-ׇ]', '', s)
    s = s.replace('%', '-')
    s = re.sub(r'[^א-ת0-9 ]', ' ', s)
    return s.split()


def shingles(w, k=3):
    if len(w) < k:
        return {tuple(w)} if w else set()
    return {tuple(w[i:i + k]) for i in range(len(w) - k + 1)}


def parse(path):
    L = open(path, encoding='utf-8').read().split('\n')
    body = []   # (text, h2, h3)
    h2 = h3 = None
    h2s = []
    for l in L[1:]:
        if not l.strip() or l == COPYRIGHT_LINE:
            continue
        if l.startswith('<h2>'):
            h2 = l[4:-5]
            h2s.append(h2)
            continue
        if l.startswith('<h3>'):
            h3 = l[4:-5]
            continue
        body.append((l, h2, h3))
    return L, body, h2s


def seq_issues(seq):
    issues = Counter()
    ex = []
    prev = None
    for d, a in seq:
        v = d * 2 + (0 if a == 'א' else 1)
        if prev is not None:
            if v == prev:
                issues['duplicate'] += 1
                ex.append(('dup', d, a))
            elif v < prev:
                issues['out_of_order'] += 1
                ex.append(('back', d, a))
            elif v > prev + 1:
                issues['gap'] += 1
                ex.append(('gap_before', d, a, v - prev - 1))
        prev = v
    return issues, ex


def run_validator(p, name):
    import shutil
    tmpd = os.path.join(OUT, '_validate_tmp')
    os.makedirs(tmpd, exist_ok=True)
    q = os.path.join(tmpd, name + '.txt')   # validate under the real file name
    shutil.copyfile(p, q)
    r = subprocess.run([sys.executable, '-X', 'utf8', VALIDATOR, q, '--json'],
                       capture_output=True, text=True)
    os.remove(q)
    try:
        j = json.loads(r.stdout)
    except Exception:
        return dict(rc=r.returncode, parse_error=True, err=mask(r.stderr[-300:]), out=mask(r.stdout[:300]))
    return dict(rc=r.returncode, j=j)


def qa(idx):
    st = json.load(open(os.path.join(OUT, f'{idx}.stats.json'), encoding='utf-8'))
    newp = os.path.join(OUT, f'{idx}.txt')
    NL, nbody, nh2 = parse(newp)
    OL, obody, oh2 = parse(old_file(idx))
    res = dict(idx=idx)
    iss, ex = seq_issues([tuple(x) for x in st['daf_seq']])
    res['daf_issues'] = dict(iss)
    res['daf_issue_examples'] = ex[:10]
    res['daf_first_last'] = [st['daf_seq'][0], st['daf_seq'][-1]] if st['daf_seq'] else None
    res['h2_equal_old'] = nh2 == oh2
    if nh2 != oh2:
        so, sn = set(oh2), set(nh2)
        res['h2_only_old'] = len(so - sn)
        res['h2_only_new'] = len(sn - so)
        res['h2_first_diff_pos'] = next((i for i, (a, b) in enumerate(zip(oh2, nh2)) if a != b), min(len(oh2), len(nh2)))
    # coverage
    ndoc = set()
    for t, _, _ in nbody:
        ndoc |= shingles(normtext(t))
    odoc = set()
    for t, _, _ in obody:
        odoc |= shingles(normtext(t))

    def cover(lines, doc):
        good = tot = 0
        wtot = wgood = 0
        for t, _, _ in lines:
            w = normtext(t)
            s = shingles(w)
            if len(w) < 4:
                continue
            tot += 1
            wtot += len(w)
            c = len(s & doc) / len(s)
            if c >= 0.8:
                good += 1
                wgood += len(w)
        return round(100 * good / max(tot, 1), 2), round(100 * wgood / max(wtot, 1), 2), tot
    res['old_lines_covered_pct'], res['old_words_covered_pct'], res['old_lines'] = cover(obody, ndoc)
    res['new_lines_covered_pct'], res['new_words_covered_pct'], res['new_lines'] = cover(nbody, odoc)
    # h3 agreement on identical body lines
    def key(t):
        return ' '.join(normtext(t))
    om = {}
    for t, h2, h3 in obody:
        om.setdefault(key(t), (h2, h3))
    agree = dis = same_line = 0
    dis_kinds = Counter()
    for t, h2, h3 in nbody:
        k = key(t)
        if len(k) < 20 or k not in om:
            continue
        same_line += 1
        oh2_, oh3_ = om[k]
        if oh3_ == h3:
            agree += 1
        else:
            dis += 1
            n1 = ' '.join(normtext(oh3_ or ''))
            n2 = ' '.join(normtext(h3 or ''))
            dis_kinds['norm_equal' if n1 == n2 else ('old_none' if oh3_ is None else ('new_none' if h3 is None else 'different'))] += 1
    res['identical_body_lines'] = same_line
    res['h3_agree_pct'] = round(100 * agree / max(same_line, 1), 2)
    res['h3_disagree_kinds'] = dict(dis_kinds)
    v = run_validator(newp, st['name'])
    if 'j' in v:
        j = v['j']
        res['validator_rc'] = v['rc']
        j = j[0]
        res['validator_errors'] = len(j['errors'])
        res['validator_warnings'] = len(j['warnings'])
        k = lambda e: mask(re.sub(r'\d+', 'N', e['message']))[:70]
        res['validator_error_kinds'] = Counter(k(e) for e in j['errors']).most_common(5)
        res['validator_warning_kinds'] = Counter(k(e) for e in j['warnings']).most_common(5)
        res['validator_first_lines'] = [e['line'] for e in (j['errors'] + j['warnings'])[:5]]
    else:
        res['validator'] = v
    return res


if __name__ == '__main__':
    idxs = [int(a) for a in sys.argv[1:]] or DOC_IDX
    allr = {}
    for i in idxs:
        r = qa(i)
        allr[i] = r
        print(json.dumps(r, ensure_ascii=True))
    with open(os.path.join(OUT, 'qa.json'), 'w') as f:
        json.dump(allr, f, indent=1)
