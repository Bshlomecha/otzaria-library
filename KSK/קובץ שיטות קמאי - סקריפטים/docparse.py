"""Minimal Word 97-2003 (.doc) parser: text via piece table, paragraph styles via PAPX,
character formatting via CHPX, stylesheet names + inherited style formatting.
Outputs per-paragraph JSONL records and a simple HTML."""
import olefile, struct, bisect, json, sys, html as H

SPRM_SIZE = {0: 1, 1: 1, 2: 2, 3: 4, 4: 2, 5: 2, 7: 3}


def iter_sprms(g):
    i = 0
    n = len(g)
    while i + 2 <= n:
        op = struct.unpack_from('<H', g, i)[0]
        i += 2
        spra = op >> 13
        if spra == 6:
            if op == 0xD608:  # sprmTDefTable
                if i + 2 > n: break
                sz = struct.unpack_from('<H', g, i)[0] - 1
                i += 2
            elif op == 0xC615:  # sprmPChgTabs
                sz = g[i]
                i += 1
                if sz == 255:
                    break
            else:
                if i >= n: break
                sz = g[i]
                i += 1
        else:
            sz = SPRM_SIZE[spra]
        val = g[i:i + sz]
        i += sz
        yield op, val


def toggle(cur, v):
    if v == 0: return False
    if v == 1: return True
    if v == 0x81: return not cur
    return cur


def apply_chp(props, grpprl, base=None):
    for op, v in iter_sprms(grpprl):
        if op in (0x0835, 0x085C) and v:  # bold / bold bi
            key = 'b' if op == 0x0835 else 'bb'
            props[key] = toggle(props.get(key, False), v[0])
        elif op in (0x0836, 0x085D) and v:
            key = 'i' if op == 0x0836 else 'ib'
            props[key] = toggle(props.get(key, False), v[0])
        elif op == 0x4A43 and len(v) == 2:
            props['sz'] = struct.unpack('<H', v)[0]
        elif op == 0x4A61 and len(v) == 2:
            props['szb'] = struct.unpack('<H', v)[0]
        elif op == 0x2A42 and v:
            props['ico'] = v[0]
        elif op == 0x6870 and len(v) == 4:
            props['cv'] = v[:3].hex()
        elif op == 0x4A5E and len(v) == 2:
            props['ftcb'] = struct.unpack('<H', v)[0]
        elif op == 0x4A4F and len(v) == 2:
            props['ftc'] = struct.unpack('<H', v)[0]
        elif op == 0x4A30 and len(v) == 2:
            props['cistd'] = struct.unpack('<H', v)[0]
        elif op == 0x2A48 and v:
            props['iss'] = v[0]
        elif op == 0x2A3E and v:
            props['u'] = v[0]
        elif op == 0x0800 and v:
            props['rmdel'] = v[0]
        elif op == 0x0839 and v:  # fVanish? 0x083C is vanish
            pass
        elif op == 0x083C and v:
            props['vanish'] = toggle(props.get('vanish', False), v[0])
    return props


def para_sprms(grpprl):
    out = {}
    for op, v in iter_sprms(grpprl):
        if op == 0x2403 and v:  # jc
            out['jc'] = v[0]
        elif op == 0x2461 and v:
            out['jc'] = v[0]
        elif op == 0x2640 and v:  # outline level
            out['olvl'] = v[0]
        elif op == 0x2416 and v:
            out['intable'] = v[0]
    return out


class Doc:
    def __init__(self, path):
        o = olefile.OleFileIO(path)
        self.wd = o.openstream('WordDocument').read()
        wd = self.wd
        flags = struct.unpack_from('<H', wd, 0xA)[0]
        tbl = '1Table' if (flags >> 9) & 1 else '0Table'
        self.tb = o.openstream(tbl).read()
        self.lw = struct.unpack_from('<22i', wd, 0x40)
        self.ccpText = self.lw[3]
        cb = struct.unpack_from('<H', wd, 0x98)[0]
        self.fclcb = [struct.unpack_from('<II', wd, 0x9A + 8 * i) for i in range(cb)]
        self.read_styles()
        self.read_pieces()
        self.papx = self.read_bte(13, 'p')
        self.chpx = self.read_bte(12, 'c')

    def read_styles(self):
        fc, lcb = self.fclcb[1]
        t = self.tb[fc:fc + lcb]
        cbStshi = struct.unpack_from('<H', t, 0)[0]
        cstd, cbBase = struct.unpack_from('<HH', t, 2)
        pos = 2 + cbStshi
        self.styles = []
        for istd in range(cstd):
            cbStd = struct.unpack_from('<H', t, pos)[0]
            pos += 2
            std = t[pos:pos + cbStd]
            pos += cbStd
            if cbStd == 0:
                self.styles.append(None)
                continue
            w0, w1, w2 = struct.unpack_from('<HHH', std, 0)
            sti = w0 & 0xFFF
            stk = w1 & 0xF
            base = w1 >> 4
            cupx = w2 & 0xF
            p = cbBase
            cch = struct.unpack_from('<H', std, p)[0]
            name = std[p + 2:p + 2 + 2 * cch].decode('utf-16le', 'replace')
            p += 2 + 2 * cch + 2
            upx = []
            for _ in range(cupx):
                if p + 2 > len(std): break
                cbu = struct.unpack_from('<H', std, p)[0]
                upx.append(std[p + 2:p + 2 + cbu])
                p += 2 + cbu
                if cbu % 2: p += 1
            papx = chpx = b''
            if stk == 1:
                if upx: papx = upx[0][2:]
                if len(upx) > 1: chpx = upx[1]
            elif stk == 2:
                if upx: chpx = upx[0]
            self.styles.append(dict(sti=sti, stk=stk, base=base, name=name, papx=papx, chpx=chpx))
        cache = {}

        def resolve(i, depth=0):
            if i in cache: return cache[i]
            s = self.styles[i] if i < len(self.styles) else None
            if s is None or depth > 20:
                return {}, {}
            if s['base'] != 0xFFF and s['base'] < len(self.styles):
                c, pp = resolve(s['base'], depth + 1)
                c = dict(c); pp = dict(pp)
            else:
                c, pp = {}, {}
            apply_chp(c, s['chpx'])
            pp.update(para_sprms(s['papx']))
            cache[i] = (c, pp)
            return cache[i]
        self.style_chp = {}
        self.style_pap = {}
        for i in range(len(self.styles)):
            c, pp = resolve(i)
            self.style_chp[i] = c
            self.style_pap[i] = pp

    def read_pieces(self):
        fc, lcb = self.fclcb[33]
        t = self.tb[fc:fc + lcb]
        i = 0
        while t[i] == 1:
            cb = struct.unpack_from('<H', t, i + 1)[0]
            i += 3 + cb
        assert t[i] == 2
        lcbp = struct.unpack_from('<I', t, i + 1)[0]
        plc = t[i + 5:i + 5 + lcbp]
        n = (lcbp - 4) // 12
        cps = struct.unpack_from('<%dI' % (n + 1), plc, 0)
        self.pieces = []
        for k in range(n):
            pcd = plc[4 * (n + 1) + 8 * k:4 * (n + 1) + 8 * k + 8]
            fcv = struct.unpack_from('<I', pcd, 2)[0]
            comp = bool(fcv & 0x40000000)
            fcv &= 0x3FFFFFFF
            if comp: fcv //= 2
            self.pieces.append((cps[k], cps[k + 1], fcv, comp))
        parts = []
        for a, b, f, comp in self.pieces:
            if comp:
                parts.append(self.wd[f:f + (b - a)].decode('cp1255', 'replace'))
            else:
                parts.append(self.wd[f:f + 2 * (b - a)].decode('utf-16le', 'replace'))
        self.text = ''.join(parts)

    def read_bte(self, idx, kind):
        fc, lcb = self.fclcb[idx]
        t = self.tb[fc:fc + lcb]
        n = (lcb - 4) // 8
        pns = struct.unpack_from('<%dI' % n, t, 4 * (n + 1))
        runs = []  # (fcStart, fcEnd, payload)
        for pn in pns:
            page = self.wd[pn * 512:(pn + 1) * 512]
            crun = page[511]
            rgfc = struct.unpack_from('<%dI' % (crun + 1), page, 0)
            for r in range(crun):
                if kind == 'p':
                    bo = page[4 * (crun + 1) + 13 * r] * 2
                    if bo == 0:
                        runs.append((rgfc[r], rgfc[r + 1], (0, b'')))
                        continue
                    cbb = page[bo]
                    if cbb == 0:
                        cbb = page[bo + 1]
                        g = page[bo + 2:bo + 2 + 2 * cbb]
                    else:
                        g = page[bo + 1:bo + 1 + 2 * cbb - 1]
                    istd = struct.unpack_from('<H', g, 0)[0] if len(g) >= 2 else 0
                    runs.append((rgfc[r], rgfc[r + 1], (istd, g[2:])))
                else:
                    bo = page[4 * (crun + 1) + r] * 2
                    if bo == 0:
                        runs.append((rgfc[r], rgfc[r + 1], b''))
                        continue
                    cbb = page[bo]
                    runs.append((rgfc[r], rgfc[r + 1], page[bo + 1:bo + 1 + cbb]))
        runs.sort(key=lambda x: x[0])
        return runs

    def piece_of(self, cp):
        if not hasattr(self, '_pst'):
            self._pst = [p[0] for p in self.pieces]
        return self.pieces[bisect.bisect_right(self._pst, cp) - 1]

    def cp2fc(self, cp):
        a, b, f, comp = self.piece_of(cp)
        return f + (cp - a) * (1 if comp else 2)

    def paragraphs(self):
        """Yield dict per paragraph of main text: text, istd, style, pap, runs [(text, props)]"""
        text = self.text[:self.ccpText]
        pstarts = [r[0] for r in self.papx]
        cstarts = [r[0] for r in self.chpx]
        # char runs in cp space
        cp = 0
        N = len(text)
        while cp < N:
            end = text.find('\r', cp)
            if end == -1: end = N - 1
            fc_end = self.cp2fc(end)
            k = bisect.bisect_right(pstarts, fc_end) - 1
            istd, pg = self.papx[k][2] if k >= 0 else (0, b'')
            pap = dict(self.style_pap.get(istd, {}))
            pap.update(para_sprms(pg))
            # char runs
            runs = []
            c = cp
            while c < end:
                f = self.cp2fc(c)
                j = bisect.bisect_right(cstarts, f) - 1
                if j >= 0 and self.chpx[j][0] <= f < self.chpx[j][1]:
                    fce = self.chpx[j][1]
                    g = self.chpx[j][2]
                else:
                    fce = f + 2
                    g = b''
                # piece-bounded
                a, b, pf, comp = self.piece_of(c)
                step = 1 if comp else 2
                ce = min(b, c + max(1, (fce - f) // step), end)
                props = dict(self.style_chp.get(istd, {}))
                tmp = apply_chp({}, g)
                if 'cistd' in tmp:
                    props.update(self.style_chp.get(tmp['cistd'], {}))
                # re-apply with toggles relative to style
                apply_chp(props, g)
                if runs and runs[-1][1] == props:
                    runs[-1] = (runs[-1][0] + text[c:ce], props)
                else:
                    runs.append((text[c:ce], props))
                c = ce
            yield dict(text=text[cp:end], istd=istd, style=(self.styles[istd] or {}).get('name') if istd < len(self.styles) else None,
                       pap=pap, runs=runs)
            cp = end + 1
