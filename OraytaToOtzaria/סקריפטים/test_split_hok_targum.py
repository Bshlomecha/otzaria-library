import unittest

from split_hok_targum import Splitter, joined_parts, real_words, same_but_spaces, split_word


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


if __name__ == "__main__":
    unittest.main()
