"""Connection types written by to_otzaria.py and accepted by validate_sidecars.py.

Run: python3 -m unittest -v test_connection_types   (from this directory)
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


to_otzaria = _load("to_otzaria")
validate_sidecars = _load("validate_sidecars")
ICL = HERE.parents[1] / "otzaria-db-linker" / "scripts" / "insert_commentary_link.py"


class SplitFootnotesTests(unittest.TestCase):
    LINES = ['<h1>T</h1>',
             'a<sup class="footnote-marker">1</sup><i class="footnote">n1</i> b'
             '<sup class="footnote-marker">2</sup><i class="footnote">n2</i>']

    def test_links_are_base_named_footnotes(self):
        out, notes, links = to_otzaria.split_footnotes(self.LINES)
        self.assertEqual(notes, ["n1", "n2"])
        self.assertEqual([(e["line_index_1"], e["line_index_2"], e["Conection Type"]) for e in links],
                         [(2, 1, "footnotes"), (2, 2, "footnotes")])
        self.assertNotIn("footnote-marker", out[1])

    @unittest.skipUnless(ICL.exists(), "otzaria-db-linker engine not present")
    def test_generator_stores_them_base_to_notes_as_footnotes(self):
        spec = importlib.util.spec_from_file_location("icl", ICL)
        icl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(icl)
        base = "Base"
        notes = "הערות על " + base
        for base_is_base in (True, False):  # either way: as written, FOOTNOTES
            self.assertEqual(icl.plan_storage("FOOTNOTES", base, base_is_base, notes, False),
                             (False, "FOOTNOTES"))


class ValidateSidecarsTypeTests(unittest.TestCase):
    def check(self, ctype):
        validate_sidecars.errors.clear()
        validate_sidecars.warnings.clear()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, "X_links.json")
            p.write_text(json.dumps([{"line_index_1": 1, "line_index_2": 1, "heRef_2": "x",
                                      "path_2": "הערות על X.txt", "Conection Type": ctype}]),
                         encoding="utf-8")
            validate_sidecars.check_links(p, None, None, None)
        return list(validate_sidecars.errors), list(validate_sidecars.warnings)

    def test_space_and_underscore_spellings_are_the_same_type(self):
        for ctype in ("mesorat hashas", "mesorat_hashas", "ein mishpat / ner mitsvah", "ein_mishpat",
                      "related passage", "related_passage", "footnote", "super commentary",
                      "sifrei mitzvot", "sifrei_mitzvot", "quotation_auto_tanakh", "none", ""):
            self.assertEqual(self.check(ctype), ([], []), ctype)

    def test_trap_spellings_are_errors_and_unknown_warns(self):
        for ctype in ("sifrei mitsvot", "sifrei_mitsvot", "note", "notes"):
            errors, _warnings = self.check(ctype)
            self.assertEqual(len(errors), 1, ctype)
        errors, warnings = self.check("no_such_type")
        self.assertEqual((len(errors), len(warnings)), (0, 1))


class CompanionMergeContractTests(unittest.TestCase):
    """issue otzaria-library#200: a broken contract left the notes standalone, silently."""

    def run_check(self, notes_name, notes_lines, base_line="a<sup>1</sup> b",
                  ctype="footnotes", link_overrides=None, extra_links=()):
        validate_sidecars.errors.clear()
        validate_sidecars.warnings.clear()
        with tempfile.TemporaryDirectory() as tmp:
            book = Path(tmp, "X.txt")
            book.write_text("<h1>X</h1>\n" + base_line, encoding="utf-8")
            target = Path(tmp, notes_name + ".txt")
            target.write_text("\n".join(notes_lines), encoding="utf-8")
            links = Path(tmp, "X_links.json")
            entry = {"line_index_1": 2, "line_index_2": 2, "heRef_2": "x",
                     "path_2": target.name, "Conection Type": ctype}
            entry.update(link_overrides or {})
            links.write_text(json.dumps([entry, *extra_links]), encoding="utf-8")
            validate_sidecars.check_links(links, book, target, None)
        return list(validate_sidecars.errors), list(validate_sidecars.warnings)

    def test_valid_pair_passes(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>הערות על X</h1>", "<sup>1</sup> n"]), ([], []))

    def test_other_name_warns(self):
        _, warnings = self.run_check("הערות במספרים על X", ["<h1>T</h1>", "<sup>1</sup> n"])
        self.assertEqual(len(warnings), 1)

    def test_unlinked_credit_line_fails(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "<sup>1</sup> n", "© credit"])
        self.assertEqual(len(errors), 1)

    def test_italic_note_fails(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "<sup>1</sup> <i>n</i>"])
        self.assertEqual(len(errors), 1)

    def test_base_with_inline_footnotes_fails(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "<sup>1</sup> n"],
                                   base_line='a<sup class="footnote-marker">1</sup><i class="footnote">n</i>')
        self.assertEqual(len(errors), 1)

    def test_merge_selection_uses_title_regardless_of_connection_type(self):
        for ctype in ("commentary", "reference", "source", "other", ""):
            with self.subTest(ctype=ctype):
                errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n", "credit"], ctype=ctype)
                self.assertTrue(any("שורות בלי קישור" in e for e in errors))

    def test_standalone_notes_do_not_have_to_satisfy_merge_contract(self):
        errors, warnings = self.run_check("הגהות X", ["<h1>T</h1>", "<i>n</i>", "credit"],
                                         base_line='<i class="footnote">existing</i>',
                                         link_overrides={"line_index_2_end": 2})
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)

    def test_havruta_is_explicitly_excluded_from_merge(self):
        errors, warnings = self.run_check("הערות על חברותא ברכות", ["<h1>T</h1>", "<i>n</i>", "credit"])
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("חברותא", warnings[0])

    def test_even_single_line_ranges_block_merge(self):
        for field in ("line_index_1_end", "line_index_2_end"):
            with self.subTest(field=field):
                errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                           link_overrides={field: 2})
                self.assertTrue(any("טווח" in e for e in errors))

    def test_null_range_does_not_block_merge(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                        link_overrides={"line_index_2_end": None}), ([], []))

    def test_null_word_anchor_does_not_block_merge(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                        link_overrides={"start": None}), ([], []))

    def test_duplicate_pair_uses_first_row_like_the_planner(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>T</h1>", "n"], extra_links=[{
            "line_index_1": 2, "line_index_2": 2, "heRef_2": "x",
            "path_2": "הערות על X.txt", "Conection Type": "footnotes", "line_index_2_end": 2,
        }]), ([], []))

    def test_word_anchor_on_duplicate_row_still_blocks_merge(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n"], extra_links=[{
            "line_index_1": 2, "line_index_2": 2, "heRef_2": "X אות א",
            "path_2": "הערות על X.txt", "Conection Type": "footnotes", "start": 0,
        }])
        self.assertEqual(len(errors), 1)
        self.assertIn("עוגן מילה", errors[0])

    def test_word_anchor_on_companion_link_blocks_merge(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                   link_overrides={"start": 0, "heRef_2": "X אות א"})
        self.assertTrue(any("עוגן מילה" in e for e in errors))

    def test_word_anchor_to_another_book_on_same_source_line_blocks_merge(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n"], extra_links=[{
            "line_index_1": 2, "line_index_2": 100, "heRef_2": "Y אות א",
            "path_2": "Y.txt", "Conection Type": "reference", "start": 0,
        }])
        self.assertEqual(len(errors), 1)
        self.assertIn("עוגן מילה", errors[0])

    def test_word_anchor_on_another_source_line_does_not_block_merge(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                        base_line="a<sup>1</sup> b\nother line", extra_links=[{
            "line_index_1": 3, "line_index_2": 100, "heRef_2": "Y אות א",
            "path_2": "Y.txt", "Conection Type": "reference", "start": 0,
        }]), ([], []))

    def test_other_target_rows_do_not_satisfy_note_coverage(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n", "unlinked"], extra_links=[{
            "line_index_1": 2, "line_index_2": 3, "heRef_2": "Y",
            "path_2": "Y.txt", "Conection Type": "reference",
        }])
        self.assertEqual(len(errors), 1)
        self.assertIn("שורות בלי קישור", errors[0])

    def test_legacy_extensionless_target_with_windows_path_is_accepted(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                        link_overrides={"path_2": "folder\\הערות על X"}), ([], []))

    def test_target_title_normalization_matches_generator(self):
        self.assertEqual(self.run_check('הערות על שו״ת X', ["<h1>T</h1>", "n"],
                                        link_overrides={"path_2": 'folder/הערות  על שו"ת X.txt'}), ([], []))

    def test_title_normalization_does_not_hide_unlinked_notes(self):
        errors, _ = self.run_check('הערות על שו״ת X', ["<h1>T</h1>", "n", "credit"], ctype="reference",
                                   link_overrides={"path_2": 'folder/הערות  על שו"ת X.txt'})
        self.assertEqual(len(errors), 1)
        self.assertIn("שורות בלי קישור", errors[0])

    def test_unsupported_target_extension_is_rejected(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                   link_overrides={"path_2": "הערות על X.pdf"})
        self.assertEqual(len(errors), 1)
        self.assertIn("path_2", errors[0])

    def test_matching_target_out_of_range_link_is_still_rejected(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "n"],
                                   link_overrides={"line_index_2": 100})
        self.assertTrue(any("מעבר לסוף ספר היעד" in e for e in errors))

    def test_unlinked_heading_and_blank_lines_are_allowed(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>T</h1>", "n", "", "<h2>S</h2>"]), ([], []))

    def test_linked_blank_or_heading_lines_still_fail(self):
        for note in ("", "<h2>S</h2>"):
            with self.subTest(note=note):
                errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", note, ""])
                self.assertTrue(errors)


# Characters Kotlin's String.trim() removes (Character.isWhitespace || isSpaceChar),
# measured on the JVM against SeforimLibrary's ConnectionType.fromKnownStringOrNull.
# Notably NOT U+0085 (str.strip() removes it), U+200B, U+FEFF.
KOTLIN_TRIM_BMP = {0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0xa0, 0x1680,
              0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008,
              0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000}


class NormalizeCtypeKotlinTrimTests(unittest.TestCase):
    def test_trim_matches_kotlin_over_the_bmp(self):
        norm = validate_sidecars.normalize_ctype
        for cp in range(0x10000):
            if 0xD800 <= cp <= 0xDFFF:
                continue
            c = chr(cp)
            for s in (c + "source", "source" + c):
                self.assertEqual(norm(s) == "source", cp in KOTLIN_TRIM_BMP, hex(cp))

    def test_null_is_empty_like_the_generator(self):
        self.assertEqual(validate_sidecars.normalize_ctype(None), "")


if __name__ == "__main__":
    unittest.main()
