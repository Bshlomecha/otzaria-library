import unittest

from split_hok_targum import Splitter, TeIndex, apply_joins, joined_parts, real_words, same_but_spaces, split_word


class SplitWordTest(unittest.TestCase):
    def test_niqqud_stays_on_its_letter(self):
        # שלושת המקרים ש-PR #66 פיצל בהם במקום הלא נכון.
        cases = [
            ("וּפוּקְדָנִייִנְטַר", (7, 4), "וּפוּקְדָנִי יִנְטַר"),
            ("וּבְשֶׁבַעאַסְלְיַת", (5, 5), "וּבְשֶׁבַע אַסְלְיַת"),
            ("וִחְיוּוְהַלִּיכוּ", (4, 6), "וִחְיוּ וְהַלִּיכוּ"),
        ]
        for word, lengths, expected in cases:
            with self.subTest(word=word):
                self.assertEqual(split_word(word, lengths), expected)

    def test_three_words(self):
        self.assertEqual(split_word("דְּלָאיָדַעיָת", (3, 3, 2)), "דְּלָא יָדַע יָת")


class SplitterTest(unittest.TestCase):
    def make(self, te: str) -> Splitter:
        return Splitter(joined_parts([te]), real_words([te]))

    def test_splits_j_pairs_from_torat_emet(self):
        sp = self.make("וּפוּקְדָנִי<j>יִנְטַר. וּבְשֶׁבַע<j>אַסְלְיַת")
        line = "וּבְשֶׁבַעאַסְלְיַת וּפוּקְדָנִייִנְטַר:"
        self.assertEqual(sp.line(line), "וּבְשֶׁבַע אַסְלְיַת וּפוּקְדָנִי יִנְטַר:")
        self.assertEqual(sp.added, 2)

    def test_idempotent(self):
        sp = self.make("וִחְיוּ<j>וְהַלִּיכוּ")
        once = sp.line("וִחְיוּוְהַלִּיכוּ")
        self.assertEqual(sp.line(once), once)

    def test_skips_concatenation_that_is_a_real_word(self):
        sp = self.make("יָת<j>בְּרָךְ. יִתְבָּרַךְ")
        self.assertEqual(sp.line("יָתבְּרָךְ"), "יָתבְּרָךְ")
        self.assertEqual(sp.skipped[("ית", "ברך")], 1)

    def test_only_spaces_added(self):
        self.assertTrue(same_but_spaces("אב\nגד", "א ב\nגד"))
        self.assertFalse(same_but_spaces("אב\nגד", "אב גד"))
        self.assertFalse(same_but_spaces("אב", "אג"))


class AmbiguousTest(unittest.TestCase):
    """חיבור שהוא מילה אמיתית מפוצל רק כשהאותיות שסביבו מסמנות בתורת אמת <j> במקום החיתוך."""

    TE = 'וְלָא מְנַעְתָּא יָת<j>בְּרָךְ יָת יְחִידָךְ. בָּרוּךְ הַקָּבָּ"ה יִתְבָּרַךְ שְׁמוֹ.'

    def make(self, te: str = TE) -> Splitter:
        return Splitter(joined_parts([te]), real_words([te]), TeIndex([te]))

    def test_splits_targum_occurrence(self):
        sp = self.make()
        line = 'וְלָא מְנַעְתָּא יָתבְּרָךְ יָת יְחִידָךְ:'
        self.assertEqual(sp.line(line), 'וְלָא מְנַעְתָּא יָת בְּרָךְ יָת יְחִידָךְ:')
        self.assertEqual(sum(sp.resolved.values()), 1)

    def test_keeps_real_word(self):
        sp = self.make()
        line = 'בָּרוּךְ הַקָּבָּ"ה יִתְבָּרַךְ שְׁמוֹ'
        self.assertEqual(sp.line(line), line)
        self.assertEqual(sum(sp.skipped.values()), 1)

    def test_idempotent(self):
        sp = self.make()
        once = sp.line('וְלָא מְנַעְתָּא יָתבְּרָךְ יָת יְחִידָךְ:')
        self.assertEqual(sp.line(once), once)

    def test_denied_mid_word_j(self):
        te = 'וּנְפַק סִיחוֹן מַ<j>לְכָּא דְחֶשְׁבּוֹן. מַלְכָּא רַבָּא'
        sp = self.make(te)
        line = 'וּנְפַק סִיחוֹן מַלְכָּא דְחֶשְׁבּוֹן'
        self.assertEqual(sp.line(line), line)


class JoinsTest(unittest.TestCase):
    def test_removes_listed_space_only(self):
        line, removed = apply_joins('כּוּלָנָא גְּבַר לָ בֵיל אוֹרְחֵיהּ')
        self.assertEqual(line, 'כּוּלָנָא גְּבַר לָבֵיל אוֹרְחֵיהּ')
        self.assertEqual(removed, 1)

    def test_several_spaces(self):
        line, removed = apply_joins('וְיָת כָּל דְּמֵהּ יֵשׁוֹד לִיסוֹדָא דְ מַ דְבְּחָא:')
        self.assertEqual(line, 'וְיָת כָּל דְּמֵהּ יֵשׁוֹד לִיסוֹדָא דְמַדְבְּחָא:')
        self.assertEqual(removed, 2)

    def test_needs_whole_words(self):
        line = 'גְּבַר לָא בֵיל'
        self.assertEqual(apply_joins(line), (line, 0))


if __name__ == "__main__":
    unittest.main()
