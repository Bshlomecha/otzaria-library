# -*- coding: utf-8 -*-
"""בדיקות לכללי ה־OCR של dicta_clean.py (P, S, R, T) — חיוביות ושליליות לכל כלל."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import dicta_clean as CL  # noqa: E402

# מילון שכיחות קטן ומבוקר (כדי שהבדיקות לא יהיו תלויות בקובץ הנתונים)
FREQ = {
    "דאסור": 56578, "דאמור": 2289, "דאם": 1191, "ור": 30,
    "וזה": 228658, "זה": 500000, "נזה": 37,
    "המים": 63454, "של": 1100558,
    "לכן": 3543, "לכוף": 6313,
    "בגיטן": 126, "ין": 4338, "גיטין": 38187,
    "מפני": 218931, "ממני": 13106,
    "זכר": 41107, "נכר": 3302, "וכר": 284,
    "סוף": 106803, "סן": 19,
    "משום": 1041029,
    "שמם": 3046, "שם": 900000,
}


def P(s):
    return CL.ocr_paren_vav(s)


def S(s, freq=FREQ):
    return CL.ocr_final_letters(s, freq=freq)


class ParenVav(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(P('כדאיתא בשבת ודף כ"ג) והובא'), 'כדאיתא בשבת (דף כ"ג) והובא')
        self.assertEqual(P("בב\"ב ודף כג.) ע\"ש"), "בב\"ב (דף כג.) ע\"ש")
        self.assertEqual(P("עיין במג\"א וסי' א' ס\"ק ח') דלכך"), "עיין במג\"א (סי' א' ס\"ק ח') דלכך")
        self.assertEqual(P("הרמב\"ן ופרק בית כור) כתב"), "הרמב\"ן (פרק בית כור) כתב")
        self.assertEqual(P("בפסחים ושם) ילפינן"), "בפסחים (שם) ילפינן")
        self.assertEqual(P("ברכות וד' ל\"ג ע\"א) הנ\"ל"), "ברכות (ד' ל\"ג ע\"א) הנ\"ל")

    def test_positive_across_bold_tag(self):
        self.assertEqual(P("<b>בשבת</b> ודף כ\"ג) והובא"), "<b>בשבת</b> (דף כ\"ג) והובא")

    def test_negative(self):
        cases = [
            "ודף כ\"ג ע\"ב והובא",                      # אין ")" בכלל
            "(עיין שבת ודף כ\"ג) והובא",                # בתוך סוגריים פתוחים — רשימה
            "וד' יאיר עיני: ו) להרז\"ה",                 # ד' = השם; סוף משפט באמצע
            "וד' הגמ' דע\"ג) אימור",                     # "ד'" = דברי, לא מספר
            "ושם יהיו בוזזים אותם *):",                 # "ושם" = וְשָׁם
            "ושם בקדרה ב') בפלוגתת",                     # "שם" + מילה — לא ודאי
            "בפ' יש נוחלין ה) ופ' האשה שנתאלמנה ו) אהא",  # תווית רשימה "ו)"
            "וע\"א אומר לא נטמאת) לא היתה",              # ע"א = עד אחד — לא ברשימה
            "ובמ\"א וסי' פ\"ה ס\"ק ב' וסי' קצ\"ג) וביד",  # שני מועמדים לאותו ")"
            "ועיין זבחים דף י\"ב ודף ל\"ג ע\"ב) וזה",      # ו' החיבור בין שתי הפניות
            "שבת ד' ע\"ד וד' קכ\"ז) ובביצה",
            "ובדף כ\"ג) והובא",                          # לא ו' בתחילת מילה
            "ודף שלם ארוך מאוד מאוד מאוד מאוד מאוד מאוד) x",  # לא מספר / ארוך
        ]
        for c in cases:
            self.assertEqual(P(c), c, c)

    def test_idempotent_and_log(self):
        log = []
        once = CL.ocr_paren_vav('בשבת ודף כ"ג) והובא', log)
        self.assertEqual(log, [(5, "ו", "(")])
        self.assertEqual(P(once), once)


class FinalLetters(unittest.TestCase):
    def test_positive_substitution(self):
        self.assertEqual(S("אבל דאםור לעשות"), "אבל דאסור לעשות")
        self.assertEqual(S("ןזה אינו"), "וזה אינו")
        self.assertEqual(S("משןם דלא"), "משום דלא")
        self.assertEqual(S("<b>סןף</b> דבר"), "<b>סוף</b> דבר")

    def test_positive_split(self):
        self.assertEqual(S("שכל המיםשל היתר"), "שכל המים של היתר")

    def test_negative(self):
        cases = [
            "לכןף",              # "לכן" + סימן דבוק
            "בגיטןין",           # "בגיטן ין" — חלק של 2 אותיות שאינו מילה
            "מםני המחלוקת",      # ממני / מפני — לא מוכח
            "ןכר",               # נכר / זכר — לא מוכח
            "שםם",               # "שם" + אות אחת
            "קדםיי",             # לא במילון, ואין מועמד
            "דאם\"ור",           # צמוד לגרשיים
            "דא<b>םור</b>",      # צמוד לתג
            "דָאםור",            # ניקוד — לא נוגעים
            "שלום עליכם",        # אין אות סופית באמצע
        ]
        for c in cases:
            self.assertEqual(S(c), c, c)

    def test_known_word_is_kept(self):
        freq = dict(FREQ, דאםור=500)
        self.assertEqual(S("דאםור", freq), "דאםור")

    def test_empty_dictionary_is_noop(self):
        self.assertEqual(S("דאםור", {}), "דאםור")

    def test_shipped_dictionary(self):
        if not CL.WORD_FREQ_FILE.exists():
            self.skipTest("dicta_word_freq.tsv.gz חסר")
        self.assertEqual(CL.ocr_final_letters("משןם דאםור"), "משום דאסור")
        self.assertEqual(CL.ocr_final_letters("מםני"), "מםני")


class Rambam(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(CL.ocr_rambam('דעת הרמב"מ בזה'), 'דעת הרמב"ם בזה')
        self.assertEqual(CL.ocr_rambam("ולהרמב״מ."), "ולהרמב״ם.")
        self.assertEqual(CL.ocr_rambam('<b>והרמב"מ</b> ס"ל'), '<b>והרמב"ם</b> ס"ל')

    def test_negative(self):
        for c in ('הרמב"ם', 'הרמב"ן', 'רמב"מה', 'ב"מ', 'ארמב"מ'):
            self.assertEqual(CL.ocr_rambam(c), c, c)


class Tosafot(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(CL.ocr_tosafot('כתבו התוס (דף כ"ט)'), "כתבו התוס' (דף כ\"ט)")
        self.assertEqual(CL.ocr_tosafot('ועי\' תוס ד"ה'), "ועי' תוס' ד\"ה")
        self.assertEqual(CL.ocr_tosafot("<b>בתוס</b> ד\"ה"), "<b>בתוס'</b> ד\"ה")
        self.assertEqual(CL.ocr_tosafot("כמש\"כ התוס:"), "כמש\"כ התוס':")
        self.assertEqual(CL.ocr_tosafot("רש״י ותוס׳ ורש״י ותוס"), "רש״י ותוס׳ ורש״י ותוס׳")

    def test_negative(self):
        cases = [
            "התוס' ד\"ה", "תוס׳", "תוספות", "ביתוס בן זונין", "אל תוס, דבר",
            "תוס 'ד\"ה", "תוס.' ב\"ק", "אתוס", "תוס\"ה", "מתוסף",
        ]
        for c in cases:
            self.assertEqual(CL.ocr_tosafot(c), c, c)


class Pipeline(unittest.TestCase):
    def test_rules_exported_in_order(self):
        self.assertEqual([f.rule_name for f in CL.OCR_RULES], ["P", "S", "R", "T"])
        names = [n for n, _ in CL.PIPELINE]
        self.assertLess(names.index("T"), names.index("M"))
        self.assertLess(names.index("F"), names.index("P"))

    def test_apply_ocr_rules_log(self):
        log = []
        out = CL.apply_ocr_rules('הרמב"מ והתוס בשבת ודף כ"ג)', rules=[
            CL.ocr_paren_vav, CL.ocr_rambam, CL.ocr_tosafot], log=log)
        self.assertEqual(out, "הרמב\"ם והתוס' בשבת (דף כ\"ג)")
        self.assertEqual([e[0] for e in log], ["P", "R", "T"])

    def test_on_by_default_and_only(self):
        text = '<h1>הרמב"מ</h1>\ny\nהרמב"מ והתוס'
        out, rep = CL.clean_text(text)
        self.assertEqual(out, '<h1>הרמב"מ</h1>\ny\nהרמב"ם והתוס\'')   # שורת השם לא נוגעים
        self.assertEqual(rep.counts.get("R_rambam_fixed"), 1)
        out, _ = CL.clean_text(text, only={"R"})
        self.assertEqual(out.split("\n")[2], 'הרמב"ם והתוס')
        out, _ = CL.clean_text(text, skip={"R", "T"})
        self.assertEqual(out, text)

    def test_cli_names(self):
        self.assertEqual(CL._letters("ocr"), {"P", "S", "R", "T"})
        self.assertEqual(CL._letters("finals,m"), {"S", "M"})

    def test_tosafot_marker_then_not_merged(self):
        # אחרי T, "תוס'" הוא סמן מקור ו־M לא מאחד אותו עם ד"ה
        out, _ = CL.clean_text("<h1>x</h1>\ny\n<b>תוס</b> <b>ד\"ה</b> ולא")
        self.assertEqual(out.split("\n")[2], "<b>תוס'</b> <b>ד\"ה</b> ולא")

    def test_idempotent(self):
        text = "<h1>x</h1>\ny\nבשבת ודף כ\"ג) הרמב\"מ והתוס ןזה"
        once, _ = CL.clean_text(text)
        twice, _ = CL.clean_text(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
