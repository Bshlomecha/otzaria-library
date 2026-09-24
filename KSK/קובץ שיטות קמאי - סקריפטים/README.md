# Kovetz Shitot Kamai - official 2026 edition converters

These scripts produced the 38 per-tractate books now kept under
`KSK/קובץ שיטות קמאי/סדר <seder>/`
(28 from Word 97-2003 `.doc` sources, 10 from HED PRESS PDFs, including
Menachot, which had no earlier edition). `KSK/` is not in `BOOK_ROOTS`, so
neither these books nor anything in this folder is packaged into the library
release; the scripts are kept here for reproducibility only.

Output is deterministic: re-running on the same sources gives byte-identical
books (checked for one `.doc` and one PDF tractate when these files were added).

## Requirements

Python 3.10+ with `olefile` (the `.doc` parser) and `pypdf`, `pymupdf` and
`fonttools` (the PDF decoders). A virtualenv is recommended; none is kept here.

## Inputs and configuration

The scripts read and write everything in a *work directory*, `$KSK_WORK`
(by default this folder; point it somewhere outside the repo):

| file | contents |
| --- | --- |
| `manifest.json` | `{"<idx>": {"path": <absolute source file>, "rel", "type": ".doc"/".pdf", "size"}}` for the 42 files of the official source folder (one file per tractate, with Menachot split over 5 PDF volumes) |
| `mapping.json` | `{"<idx>": {"file", "type", "tractate_he", "filename_stem", "translit", "title_line"}}`; needed only for a PDF tractate with no earlier file (Menachot) |

Neither file is checked in: both hold local absolute paths to the source
folder. Rebuild them from a listing of that folder.

Environment variables (all optional):

- `KSK_WORK`: the work directory above.
- `KSK_REPO`: the otzaria-library checkout (default: two levels above this folder).
- `KSK_OLD_ROOT`: the **pre-2026** `KSK/` tree. The converters copy each book's
  `<h1>` and file name from the old file and QA compares against it. The new
  books overwrote the old ones at the same `KSK/` paths, so the default
  (`$KSK_REPO/KSK`) now points at the new books themselves: the `<h1>`/name
  lookup still works, but QA then compares a book with itself. For a real
  comparison, extract the old tree from the last commit that had it:
  `git archive 93c9fa6d KSK | tar -x -C /some/dir` and set
  `KSK_OLD_ROOT=/some/dir/KSK`.
- `KSK_VALIDATOR`: path to `validate_book.py` (default: the repo's
  `.claude/skills/otzaria-book-format/scripts/validate_book.py`).

`convert_doc.py` also reads `replace.csv` from this folder: the label fixes
(cp1255) moved here from the old `KSK/fix and split/` scripts, which were removed.

## Pipeline and run order

Run every command from `$KSK_WORK`.

`.doc` tractates (indices listed in `convert_doc.DOC_IDX`):

1. `extract.py <idx>`: parses the `.doc` file with `docparse.py` (piece table +
   paragraph/character properties) into `txt/`, `html/` and `paras/<idx>.jsonl`.
   `convert_doc.py` runs this for you when `paras/<idx>.jsonl` is missing.
2. `convert_doc.py [idx ...]`: writes `out/<idx>.txt`, `out/<idx>.stats.json` and
   `out/names.json` (idx -> target book name).
3. `qa.py [idx ...]`: compares each book with the old one and runs the validator;
   writes `out/qa.json`. It prints structure and counts only.

PDF tractates (keys listed in `convert_pdf.BOOKS`):

1. `convert_pdf.py [key ...]`: decodes the PDFs with `kskdec.py` (glyph names to
   cp1255, per-span fonts, two-column reading order), caching decoded pages in
   `work/dec/<idx>.jsonl.gz`. The cache is rebuilt whenever `kskdec.py` changes.
   Writes `out_pdf/<key>.txt`, `out_pdf/names.json` and `out_pdf/report.json`.
2. `qa_pdf.py [key ...]`: structural QA against the old files and the validator;
   writes `out_pdf/qa.json`.

`pdfdecode.py` and `runpdf.py <idx>` are the first, simpler PDF decoder. They
dump raw decoded pages to `pdfdec/` for inspection, and `convert_pdf.py` does not
use them.

## Installing the output

Copy `out/<idx>.txt` / `out_pdf/<key>.txt` to
`KSK/קובץ שיטות קמאי/סדר <seder>/<name>.txt`, using the name from the
matching `names.json`. The metadata registries (`ForDB/all_metadata.json`,
`all_metadata*.json`, `SourcesBooks.csv`) key on that name. They are not in
`ForDB/generations.csv`, which lists only packaged books.
