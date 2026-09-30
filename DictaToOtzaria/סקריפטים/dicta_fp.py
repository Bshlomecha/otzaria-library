"""טביעות טקסט להשוואת ספרים — בלי תלות בקיטוע השורות, בסימון ובניקוד.

כל מילה מצטמצמת לאותיות העבריות שבה בלבד (סופיות → רגילות), ואז:

* `keys(text)`        — רצף המפתחות (למשל ליישור ברמת מילים ב־dicta_replay).
* `fingerprint(text)` — קבוצת 8-grams מדוגמים (crc32 % MOD == 0) של המפתחות.
* `coverage(a, b)`    — איזה חלק מהטביעה של a נמצא ב־b.

זו אותה שיטה שבה נמדדה בבדיקה הראשונית (ר' README) החפיפה בין ספרי דיקטה לספריה.
"""
from __future__ import annotations

import hashlib
import re
import zlib

TAG_RE = re.compile(r"<[^>]+>")
HEB_RE = re.compile(r"[א-ת]+")
FINALS = str.maketrans("ךםןףץ", "כמנפצ")
N = 8
MOD = 32


def keys(text: str) -> list[str]:
    """מפתחות־אותיות לכל מילה שיש בה לפחות אות עברית אחת."""
    t = TAG_RE.sub(" ", text.replace("&nbsp;", " ").replace("&amp;", "&"))
    out = []
    for w in t.split():
        k = "".join(HEB_RE.findall(w))
        if k:
            out.append(k.translate(FINALS))
    return out


def html_keys(html: str) -> list[str]:
    """מפתחות של דף HTML של דיקטה כפי שהאתר מציג אותו: טקסט ה־span־ים מחובר בלי רווח
    (`<span> בין</span><span>מטה</span>` = "ביןמטה"), רווח רק היכן שיש רווח בטקסט עצמו."""
    return keys(TAG_RE.sub("", html.replace("&nbsp;", " ")))


def text_keys(text: str) -> list[str]:
    """מפתחות של טקסט אוצריא כפי שהוא מוצג: תגים בתוך השורה (<b>, <big>, <small>, <i>, <sup>…) אינם
    מפרידים מילים (`<b>י</b>סודי` = "יסודי"); שורה חדשה ו־<br> כן."""
    return keys(TAG_RE.sub("", re.sub(r"<br\s*/?>", " ", text.replace("&nbsp;", " "))))


def fingerprint(text_or_keys, n: int = N, mod: int = MOD) -> set[int]:
    ws = keys(text_or_keys) if isinstance(text_or_keys, str) else list(text_or_keys)
    out = set()
    for i in range(len(ws) - n + 1):
        c = zlib.crc32(" ".join(ws[i:i + n]).encode("utf-8"))
        if c % mod == 0:
            out.add(c)
    return out


def coverage(a: set[int], b: set[int]) -> float:
    """החלק של a שנמצא ב־b (0 כש־a ריק)."""
    return len(a & b) / len(a) if a else 0.0


def letters_hash(text: str, length: int = 10) -> str:
    """hash של רצף האותיות בלבד — זהה גם כשדיקטה משנה סימון או צירוף מילים."""
    return hashlib.sha1("".join(keys(text)).encode("utf-8")).hexdigest()[:length]


# ---------------------------------------------------------------------------
# אינדקס טביעות לכל הספרייה — לזיהוי כפילות תוכן של ספר חדש (גם בשם אחר)
# ---------------------------------------------------------------------------
#
# קובץ: שורת כותרת JSON, '\n', ואז שני מערכים בינאריים (little-endian) באותו אורך:
# hashes (uint32, ממוינים) ו־ids (uint16). כל זוג = "8-gram מדוגם X נמצא בספר id".
# הסיומת ‎.dat — לא ב־.gitattributes של LFS (‎.bin/.gz/.zip כן).
# דגימה גסה יותר (INDEX_MOD) מזו של הבדיקה הישירה (MOD), כדי שהקובץ יישאר קטן; שלב 2 של
# הבדיקה (dicta_sync) מחשב מחדש ב־MOD מול הטקסט המלא של המועמדים שיש להם טקסט במאגר.

import array as _array
import collections as _collections
import json as _json
import sys as _sys

INDEX_MOD = 256


class FingerprintIndex:
    def __init__(self, mod: int = INDEX_MOD, books=None, pairs=None):
        self.mod = mod
        self.books = books or []          # [{"key", "grams", ...meta}]
        self._map = None
        self._pairs = pairs or []         # [(hash, id)]

    @classmethod
    def build(cls, items, mod: int = INDEX_MOD):
        """items: [(key, text_or_keys, meta_dict)]."""
        idx = cls(mod)
        for key, text, meta in items:
            idx.add(key, fingerprint(text, mod=mod), meta)
        return idx

    def add(self, key, grams: set, meta=None):
        i = len(self.books)
        if i >= 65535:
            raise ValueError("too many books for uint16 ids")
        self.books.append({"key": key, "grams": len(grams), **(meta or {})})
        self._pairs.extend((h, i) for h in grams)
        self._map = None

    def save(self, path: str, extra: dict | None = None):
        pairs = sorted(set(self._pairs))
        hs = _array.array("I", (h for h, _ in pairs))
        ids = _array.array("H", (i for _, i in pairs))
        if _sys.byteorder != "little":
            hs.byteswap()
            ids.byteswap()
        head = {"format": "dicta-fp-index-1", "n": N, "mod": self.mod, "pairs": len(pairs),
                "books": self.books, **(extra or {})}
        with open(path, "wb") as f:
            f.write(_json.dumps(head, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
            f.write(hs.tobytes())
            f.write(ids.tobytes())

    @classmethod
    def load(cls, path: str):
        with open(path, "rb") as f:
            head = _json.loads(f.readline().decode("utf-8"))
            if head.get("format") != "dicta-fp-index-1" or head.get("n") != N:
                raise ValueError(f"{path}: unknown fingerprint index format")
            hs = _array.array("I")
            ids = _array.array("H")
            hs.frombytes(f.read(4 * head["pairs"]))
            ids.frombytes(f.read(2 * head["pairs"]))
        if _sys.byteorder != "little":
            hs.byteswap()
            ids.byteswap()
        idx = cls(head["mod"], head["books"], list(zip(hs, ids)))
        idx.header = head
        return idx

    def _index(self):
        if self._map is None:
            m = _collections.defaultdict(list)
            for h, i in self._pairs:
                m[h].append(i)
            self._map = m
        return self._map

    def query(self, text_or_keys, min_shared: int = 2) -> list[dict]:
        """לכל ספר באינדקס שחולק עם הטקסט ≥min_shared grams: book_cov (חלק מהטקסט שנמצא בספר)
        ו־file_cov (חלק מהספר שנמצא בטקסט) — אותן הגדרות כמו ב־bootstrap."""
        g = fingerprint(text_or_keys, mod=self.mod)
        m = self._index()
        c = _collections.Counter(i for h in g for i in m.get(h, ()))
        out = []
        for i, k in c.most_common():
            if k < min_shared:
                break
            b = self.books[i]
            out.append({**b, "shared": k, "text_grams": len(g),
                        "book_cov": k / max(1, len(g)), "file_cov": k / max(1, b["grams"])})
        return out
