"""Exercise actual importer/installer entrypoints against complete offline registries."""
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from book_info_writer import HEADER, encode_rows, plan_registration, apply_registration

ROOT = Path(__file__).resolve().parents[2]


def load_script(relative):
    spec = importlib.util.spec_from_file_location('writer_integration', ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WriterTest(unittest.TestCase):
    def test_additive_registration_blank_fallback_coauthors_sort_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ForDB/book_info.csv'
            path.parent.mkdir()
            existing = [['קיים', 'אחד', 'ראשונים', 'ראשוני הראשונים', '100', '200'],
                        ['קיים', 'שני', 'מחברי זמננו', '', '', '']]
            path.write_text(encode_rows([HEADER, *existing]), encoding='utf-8')
            entries = [['קיים', '', 'אחרונים', '', '', ''], ['קיים', 'אחד', 'אחרונים', '', '', ''],
                       ['חדש', 'שלישי', 'אחרונים', '', '', '']]
            apply_registration(tmp, plan_registration(tmp, entries))
            rows = list(csv.reader(io.StringIO(path.read_text(), newline='')))
            self.assertEqual(rows, [HEADER, entries[2], *existing])
            self.assertEqual(plan_registration(tmp, entries), {})

    def test_storage_contract_rejects_invalid_source_and_proposal_before_writes(self):
        valid = encode_rows([HEADER, ["ספר", "מחבר", "ראשונים", "", "100", "200"]])
        corrupt = ["\ufeff" + valid, valid.replace("\n", "\r\n"), valid.replace("מחבר", "מח\0בר"),
                   valid.replace('"100"', '"100.5"'), valid.replace('"100"', '"2147483648"'),
                   valid.replace('"100"', '"300"'), valid + "\n", valid.replace("מחבר", "מח\ufeffבר"), valid.replace('"ראשונים",""', '"ראשונים","ראשוני האחרונים"')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ForDB/book_info.csv'
            path.parent.mkdir()
            for text in corrupt:
                with self.subTest(source=text):
                    path.write_bytes(text.encode('utf-8'))
                    with self.assertRaises(ValueError):
                        plan_registration(tmp, [["חדש", "מחבר", "ראשונים", "", "", ""]])
                    self.assertEqual(path.read_bytes(), text.encode('utf-8'))
            path.write_bytes(valid.encode('utf-8'))
            for year in ('1.5', '2147483648', '-2147483649'):
                with self.subTest(proposalYear=year), self.assertRaises(ValueError):
                    plan_registration(tmp, [["חדש", "מחבר", "ראשונים", "", year, ""]])
            self.assertEqual(path.read_bytes(), valid.encode('utf-8'))

    def test_missing_new_source_is_not_created_from_empty_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'ForDB').mkdir()
            (Path(tmp) / 'ForDB/generations.csv').write_text('שם ספר,קבוצת דור\nישן,ראשונים\n')
            with self.assertRaises(FileNotFoundError):
                plan_registration(tmp, [['חדש', '', 'ראשונים', '', '', '']])
            self.assertFalse((Path(tmp) / 'ForDB/book_info.csv').exists())

    def test_production_make_metadata_prints_and_registers_six_fields_per_author(self):
        module = load_script('.claude/skills/otzaria-book-format/scripts/make_metadata.py')
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / 'ForDB/book_info.csv'
            info.parent.mkdir()
            info.write_text(encode_rows([HEADER]))
            output = io.StringIO()
            argv = ['make_metadata.py', '--title', 'ספר', '--author', 'מחבר א', '--author', 'מחבר ב',
                    '--generation', 'ראשונים', '--book-info-csv', str(info), '--print-fordb']
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                self.assertEqual(module.main(), 0)
            rows = list(csv.reader(io.StringIO(info.read_text(), newline='')))
            self.assertEqual(rows[1:], [['ספר', 'מחבר א', 'ראשונים', '', '', ''], ['ספר', 'מחבר ב', 'ראשונים', '', '', '']])
            for row in rows[1:]:
                self.assertIn(encode_rows([row]).strip(), output.getvalue())


if __name__ == '__main__':
    unittest.main()
