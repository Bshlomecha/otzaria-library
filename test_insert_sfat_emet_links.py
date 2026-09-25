"""Connection-type handling of _insert_sfat_emet_links.py (no real seforim.db needed)."""
import contextlib
import importlib.util
import io
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("insert_sfat_emet_links", ROOT / "_insert_sfat_emet_links.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

LINK_KT = (
    ROOT.parent / "SeforimLibrary" / "core" / "src" / "commonMain" / "kotlin" / "io" / "github"
    / "kdroidfilter" / "seforimlibrary" / "core" / "models" / "Link.kt"
)
# ConnectionType enum order == connection_type ids in a fresh SeforimLibrary build.
ENUM = [
    "COMMENTARY", "SUPER_COMMENTARY", "TARGUM", "REFERENCE", "SOURCE", "MIDRASH", "QUOTATION",
    "MESORAT_HASHAS", "EIN_MISHPAT", "DIBUR_HAMATCHIL", "PARSHANUT", "MISHNAH_IN_TALMUD",
    "RELATED", "OTHER", "LINKER", "SIFREI_MITZVOT", "ESSAY", "ALLUSION", "LITURGY",
    "ELUCIDATION", "EXPLICATION", "LAW", "SUMMARY", "FOOTNOTES",
]
ON = " על "           # the " al " separator Generator.titleDeclaresDependencyOn reads
BASE = "Base"
CITING = "Citing" + ON + BASE   # declares its base, like the real PAIRS titles
PLAIN = "Citing"                # does not
FLAGS = ("hasTargumConnection", "hasReferenceConnection", "hasSourceConnection",
         "hasCommentaryConnection", "hasOtherConnection")


def make_db(type_names, citing_title=CITING):
    """Current seforim.db schema (baseProvenance, not the pre-July-2026 isDeclaredBase)."""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE connection_type(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE source(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE book(id INTEGER PRIMARY KEY, sourceId INT NOT NULL DEFAULT 1, title TEXT,
            totalLines INT, orderIndex INT, isBaseBook INT NOT NULL DEFAULT 0,
            hasTargumConnection INT NOT NULL DEFAULT 0, hasReferenceConnection INT NOT NULL DEFAULT 0,
            hasSourceConnection INT NOT NULL DEFAULT 0, hasCommentaryConnection INT NOT NULL DEFAULT 0,
            hasOtherConnection INT NOT NULL DEFAULT 0);
        CREATE TABLE line(id INTEGER PRIMARY KEY, bookId INT, lineIndex INT, content TEXT NOT NULL);
        CREATE TABLE link(id INTEGER PRIMARY KEY, sourceBookId INT NOT NULL, targetBookId INT NOT NULL,
            sourceLineId INT NOT NULL, targetLineId INT NOT NULL, targetLineIndex INT NOT NULL,
            targetBookOrderIndex INT NOT NULL, connectionTypeId INT NOT NULL,
            baseProvenance INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE book_has_links(bookId INTEGER PRIMARY KEY, hasSourceLinks INT NOT NULL DEFAULT 0,
            hasTargetLinks INT NOT NULL DEFAULT 0);
        INSERT INTO source VALUES (1, 'DictaToOtzaria');
        """
    )
    cur.execute("INSERT INTO book (id, title, totalLines, orderIndex, isBaseBook) VALUES (1, ?, 3, 1, 1)", (BASE,))
    cur.execute("INSERT INTO book (id, title, totalLines, orderIndex, isBaseBook) VALUES (2, ?, 3, 2, 0)",
                (citing_title,))
    cur.executemany("INSERT INTO connection_type VALUES (?, ?)", list(enumerate(type_names, start=1)))
    cur.executemany(
        "INSERT INTO line(bookId, lineIndex, content) VALUES (?, ?, ?)",
        [(book, idx, "<h2>h</h2>" if idx == 2 else "text") for book in (1, 2) for idx in range(3)],
    )
    return conn, cur


def entry(line, ctype):
    return {"line_index_1": line, "line_index_2": line, "heRef_2": "x", "path_2": BASE + ".txt",
            "Conection Type": ctype}


def run_pair(cur, citing_title, entries):
    ids = m.load_connection_type_ids(cur)
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, f"{citing_title}_links.json").write_text(json.dumps(entries), encoding="utf-8")
        old_dir = m.LINKS_DIR
        m.LINKS_DIR = Path(tmp)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                next_id = (cur.execute("SELECT MAX(id) FROM link").fetchone()[0] or 0) + 1
                return m.insert_pair(cur, citing_title, BASE, next_id, ids), ids
        finally:
            m.LINKS_DIR = old_dir


class ConnectionTypeParsingTests(unittest.TestCase):
    def test_normalization_matches_seforimlibrary(self):
        self.assertEqual(m.canonical_connection_type(" Footnotes "), "FOOTNOTES")
        self.assertEqual(m.canonical_connection_type("footnote"), "FOOTNOTES")
        self.assertEqual(m.canonical_connection_type("mesorat hashas"), "MESORAT_HASHAS")
        self.assertEqual(m.canonical_connection_type("ein mishpat / ner mitsvah"), "EIN_MISHPAT")
        self.assertEqual(m.canonical_connection_type("super commentary"), "SUPER_COMMENTARY")
        self.assertIsNone(m.canonical_connection_type("note"))
        self.assertIsNone(m.canonical_connection_type(None))

    def test_only_types_the_generator_can_flip_are_supported(self):
        self.assertEqual(m.stored_type_for("source"), "COMMENTARY")
        self.assertEqual(m.stored_type_for("footnotes"), "FOOTNOTES")
        self.assertEqual(m.stored_type_for("dibur_hamatchil"), "DIBUR_HAMATCHIL")
        # Stored unflipped by Generator.kt -> this always-flipping script must refuse them.
        for lateral in ("mesorat hashas", "reference", "explication", "other", "linker"):
            self.assertIsNone(m.stored_type_for(lateral), lateral)

    @unittest.skipUnless(LINK_KT.exists(), "SeforimLibrary checkout not next to this repo")
    def test_known_types_cover_the_kotlin_enum(self):
        text = LINK_KT.read_text(encoding="utf-8")
        body = text[text.index("enum class ConnectionType"):text.index("companion object")]
        names = set(re.findall(r"^\s*([A-Z][A-Z_]+),\s*$", body, re.M))
        self.assertEqual(names, set(ENUM))
        self.assertEqual(set(m.icl.KNOWN_CONNECTION_TYPES), names)
        self.assertLessEqual(set(m.STORED_TYPE_FOR), names)


class PreflightAndInsertTests(unittest.TestCase):
    def test_unsupported_type_is_refused_not_skipped(self):
        _conn, cur = make_db(ENUM)
        problems = m.preflight_connection_types(
            {"f_links.json": [entry(1, "source"), entry(2, "mesorat hashas")]},
            m.load_connection_type_ids(cur),
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("'mesorat hashas'", problems[0])

    def test_db_without_footnotes_row_is_refused(self):
        _conn, cur = make_db(ENUM[:-1])
        problems = m.preflight_connection_types(
            {"f_links.json": [entry(1, "footnotes")]}, m.load_connection_type_ids(cur)
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("'FOOTNOTES' is missing", problems[0])

    def test_footnotes_and_source_are_both_inserted_flipped(self):
        _conn, cur = make_db(ENUM)
        (_next, inserted, skipped), ids = run_pair(
            cur, CITING, [entry(1, "source"), entry(2, "footnotes"), entry(3, "source")]
        )
        self.assertEqual((inserted, skipped), (2, 1))  # line 3 is a heading -> skipped
        rows = cur.execute(
            "SELECT sourceBookId, targetBookId, connectionTypeId, baseProvenance FROM link ORDER BY id"
        ).fetchall()
        self.assertEqual(rows, [(1, 2, ids["COMMENTARY"], 0), (1, 2, ids["FOOTNOTES"], 0)])

    def test_footnotes_under_a_title_not_naming_the_base_is_refused(self):
        # Generator.kt would store it as OTHER, unflipped -- not what this script writes.
        _conn, cur = make_db(ENUM, citing_title=PLAIN)
        with self.assertRaises(ValueError):
            run_pair(cur, PLAIN, [entry(1, "footnotes")])

    def test_flags_are_the_generators(self):
        _conn, cur = make_db(ENUM)
        run_pair(cur, CITING, [entry(2, "footnotes")])
        flags = cur.execute(f"SELECT {', '.join(FLAGS)} FROM book ORDER BY id").fetchall()
        self.assertEqual(flags, [(0,) * 5, (0,) * 5])  # FOOTNOTES sets no has*Connection
        self.assertEqual(cur.execute("SELECT * FROM book_has_links ORDER BY bookId").fetchall(),
                         [(1, 1, 0), (2, 0, 1)])
        run_pair(cur, CITING, [entry(1, "source")])
        base, citing = cur.execute(f"SELECT {', '.join(FLAGS)} FROM book ORDER BY id").fetchall()
        self.assertEqual(dict(zip(FLAGS, base))["hasCommentaryConnection"], 1)
        self.assertEqual(dict(zip(FLAGS, citing))["hasSourceConnection"], 1)
        self.assertEqual(dict(zip(FLAGS, base))["hasSourceConnection"], 0)


if __name__ == "__main__":
    unittest.main()
