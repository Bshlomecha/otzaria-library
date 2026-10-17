import json
import tempfile
import unittest
from pathlib import Path

from otzaria.get_from_export import Book


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class SameTractateRefTest(unittest.TestCase):
    def make_book(self, base_title: str, base_schema: dict | None, lines: list[str], raw_index: bool = False) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            if base_schema is not None:
                write_json(folder / f"{base_title.replace(' ', '_')}.json", base_schema)
            # הייצוא (Index.contents) נותן {"en", "he"}; רשומת אינדקס גולמית נותנת מחרוזת.
            base_entry = base_title if raw_index else {"en": base_title, "he": (base_schema or {}).get("heTitle", "")}
            schema = write_json(folder / "Commentary.json", {
                "title": "Commentary", "heTitle": "פירוש", "base_text_titles": [base_entry],
                "schema": {"title": "Commentary", "heTitle": "פירוש", "depth": 1, "heSectionNames": ["פסקה"]},
            })
            text = write_json(folder / "merged.json", {"text": lines})
            return Book("Commentary", "hebrew", text, schema).process_book()[1:]

    def test_drops_own_tractate_after_lekaman_and_leil(self):
        out = self.make_book("Bava Metzia", {"heTitle": "בבא מציעא", "categories": ["Talmud", "Bavli", "Seder Nezikin"]}, [
            "כדאמרינן (לקמן בבא מציעא דף ט.) וכן (לעיל בבא  מציעא ב, א)",
            "(לקמן בבא קמא דף ב.) (לקמן פרק א' בבא מציעא דף ג.) (לקמן בבא מציעאי)",
            "(לְקַמָּן בָּבָא מְצִיעָא דף ד.)",
        ])
        self.assertEqual(out, [
            "כדאמרינן (לקמן דף ט.) וכן (לעיל ב, א)\n",
            "(לקמן בבא קמא דף ב.) (לקמן פרק א' בבא מציעא דף ג.) (לקמן בבא מציעאי)\n",
            "(לְקַמָּן דף ד.)\n",
        ])

    def test_matches_own_tractate_without_nikud_in_text(self):
        out = self.make_book("Makkot", {"heTitle": "מַכּוֹת", "categories": ["Talmud", "Bavli"]}, ["(לעיל מכות דף ה:)"])
        self.assertEqual(out, ["(לעיל דף ה:)\n"])

    def test_keeps_text_when_base_is_not_bavli_or_missing(self):
        line = "(לקמן ברכות דף ב.)"
        mishnah = {"heTitle": "ברכות", "categories": ["Mishnah", "Seder Zeraim"]}
        self.assertEqual(self.make_book("Mishnah Berakhot", mishnah, [line]), [line + "\n"])
        self.assertEqual(self.make_book("Berakhot", None, [line]), [line + "\n"])

    def test_raw_index_string_base_title(self):
        out = self.make_book("Makkot", {"heTitle": "מכות", "categories": ["Talmud", "Bavli"]}, ["(לעיל מכות דף ה:)"], raw_index=True)
        self.assertEqual(out, ["(לעיל דף ה:)\n"])

    def test_non_bavli_commentary_from_real_export_shape(self):
        # רש"י על בראשית: בסיס יחיד בצורת הייצוא, לא בבלי — הטקסט נשאר כמו שהוא.
        genesis = {"heTitle": "בראשית", "categories": ["Tanakh", "Torah"]}
        line = "(לקמן בראשית ב, ג)"
        self.assertEqual(self.make_book("Genesis", genesis, [line]), [line + "\n"])

    def test_keeps_punctuation_after_tractate(self):
        # סוף פסוק אחרי השם אינו ניקוד: אין התאמה, ושום תו לא נמחק.
        line = "(לקמן מכות\u05c3 דף ה:)"
        self.assertEqual(self.make_book("Makkot", {"heTitle": "מכות", "categories": ["Talmud", "Bavli"]}, [line]), [line + "\n"])

    SHABBAT = {"heTitle": "שבת", "categories": ["Talmud", "Bavli", "Seder Moed"]}

    def test_drops_own_tractate_inside_the_bracket_after_lekaman(self):
        out = self.make_book("Shabbat", self.SHABBAT, [
            "דפריך לקמן (שבת דף ה:) ולעיל (שבת סז, ב) ובמתני' לקמן [שבת לט ע\"ב]",
            "(כלקמן שבת נט, ב) (וכדלקמן שבת מט, א) (להלן שבת כו,א)",
            "(לעיל שבת דף מה. ולקמן שבת דף ס:)",
        ])
        self.assertEqual(out, [
            "דפריך לקמן (דף ה:) ולעיל (סז, ב) ובמתני' לקמן [לט ע\"ב]\n",
            "(כלקמן נט, ב) (וכדלקמן מט, א) (להלן כו,א)\n",
            "(לעיל דף מה. ולקמן דף ס:)\n",
        ])

    def test_drops_own_tractate_before_a_daf_address(self):
        out = self.make_book("Shabbat", self.SHABBAT, [
            "בפרק כירה (שבת דף מד) ובפ' המצניע (שבת ד' צג:) ובסוף פירקין (שבת קנ\"ז ע\"ב)",
            "(שבת קנז.) (שבת טו, א) (שבת פב ב') (שבת פב)",
        ])
        self.assertEqual(out, [
            "בפרק כירה (דף מד) ובפ' המצניע (ד' צג:) ובסוף פירקין (קנ\"ז ע\"ב)\n",
            "(קנז.) (טו, א) (פב ב') (פב)\n",
        ])

    def test_keeps_tractate_that_is_not_a_daf_reference(self):
        # בלי כתובת דף, מספר שאינו דף, שם כמילה בטקסט, ושם ארוך יותר — הכול נשאר.
        lines = [
            "(שבת שנטמא) [שבת] (שבת בלעם) (שבת שם) (גזרו שבת) (שבתות דף ב.) (שבת פ\"ג ה\"א)",
            "(לקמן פרק א' שבת דף ג.) (לקמן שבת)",
        ]
        self.assertEqual(self.make_book("Shabbat", self.SHABBAT, lines), [line + "\n" for line in lines])

    def test_keeps_yerushalmi_and_tosefta_of_the_same_name(self):
        lines = ["ובירושלמי (שבת ג,א) גרסינן", "לו.<br>ובירושלמי (שבת ג,א)", "בתוספתא (שבת ג, א)", "ירושלמי [שבת דף ג.]"]
        self.assertEqual(self.make_book("Shabbat", self.SHABBAT, lines), [line + "\n" for line in lines])


if __name__ == "__main__":
    unittest.main()
