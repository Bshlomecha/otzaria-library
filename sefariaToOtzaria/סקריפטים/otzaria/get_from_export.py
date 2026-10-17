import re
from pathlib import Path

from .utils import has_value, read_json, to_daf, to_eng_daf, to_gematria

# סימני ניקוד וטעמים בלבד; בלי מקף, פסק, סוף פסוק ונו"ן הפוכה, שהם פיסוק.
NIKUD = r"[\u0591-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]*"
# ערכי האותיות למספר עברי (דף); ט"ו/ט"ז הם החריגים היחידים לסדר היורד.
# המסכת הארוכה בבבלי (בבא בתרא) מסתיימת בדף קעו.
LAST_DAF = 176
GEMATRIA = dict(zip("אבגדהוזחטיכךלמםנןסעפףצץקרשת", (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 20, 30, 40, 40, 50, 50, 60, 70, 80, 80, 90, 90, 100, 200, 300, 400)))
QUOTES = "\"'״׳"
# כתובת דף אחרי שם המסכת: "דף"/"ד'", או מספר ואחריו . : , ע"א א' או סוגר.
DAF_ADDRESS = re.compile(
    r"(?:דף|ד['׳])\s"
    r"|(?P<num>[א-ת](?:[\"'״׳]?[א-ת]){0,2}[\"'״׳]?)"
    r"(?:\s*[.:]|\s*,\s*[אב](?![א-ת])|\s+ע[\"'״׳]?[אב](?![א-ת])|\s+[אב]['׳]?(?=[\s)\],.;:])|(?=[)\]]))"
)
# בסוגר שאחרי "ירושלמי"/"תוספתא" שם המסכת הוא של ספר אחר.
OTHER_WORK = re.compile(r"(?<![א-ת])(?:ו|ב|ה|וב|וה|ובה|ד|וד)?(?:ירושלמי|ירוש['׳]|תוספתא|תוספת['׳])\s*$")


def is_daf_number(token: str) -> bool:
    letters = [c for c in token if c not in QUOTES]
    values = [GEMATRIA[c] for c in letters]
    if "".join(letters) in ("טו", "טז"):
        return True
    return all(a > b for a, b in zip(values, values[1:])) and sum(values) <= LAST_DAF


def same_tractate_patterns(tractate: str) -> tuple[re.Pattern, re.Pattern]:
    chars = {" ": r"\s+", '"': '["״]', "״": '["״]', "'": "['׳]", "׳": "['׳]"}
    name = NIKUD.join(chars.get(c, re.escape(c)) for c in re.sub(NIKUD, "", tractate))
    words = "|".join(NIKUD.join(word) for word in ("לקמן", "לעיל", "להלן"))
    relative = re.compile(rf"(?<![א-ת])((?:ו?(?:כד|כ|ד)?)(?:{words}){NIKUD})\s+{name}{NIKUD}(?=\s)")
    bracketed = re.compile(rf"([(\[]){name}{NIKUD}\s+")
    return relative, bracketed


def inside_bracket(text: str, pos: int) -> bool:
    opened = max(text.rfind("(", 0, pos), text.rfind("[", 0, pos))
    return opened > max(text.rfind(")", 0, pos), text.rfind("]", 0, pos))


def drop_same_tractate(text: str, patterns: tuple[re.Pattern, re.Pattern] | None) -> str:
    """בפירושי הבבלי ספריא הוסיפה את שם המסכת עצמה להפניות, שאינו בדפוס וילנא:
    "(לקמן מכות דף ט.)", "לקמן (מכות דף ט.)", "בפרק כירה (שבת דף מד)" ← בלי השם."""
    if patterns is None or ("(" not in text and "[" not in text):
        return text
    relative, bracketed = patterns
    text = relative.sub(lambda m: m.group(1) if inside_bracket(m.string, m.start()) else m.group(0), text)

    def bare(m: re.Match) -> str:
        address = DAF_ADDRESS.match(m.string, m.end())
        if address is None or (address.group("num") and not is_daf_number(address.group("num"))):
            return m.group(0)
        if OTHER_WORK.search(m.string, 0, m.start()):
            return m.group(0)
        return m.group(1)

    return bracketed.sub(bare, text)


class Book:
    def __init__(
        self,
        book_title: str,
        lang: str,
        text_file_path: Path,
        schema_file_path: Path,
        he_title: str | None = None
    ) -> None:

        self.book_title = book_title
        self.metadata = {"heSeries": None, "series": None, "series-index": None}
        self.lang = lang[:2]
        self.refs = []
        self.long_lang = lang
        self.section_names_lang = (self.lang
                                   if self.lang in ("he", "en")
                                   else "en")
        self.book_content = []
        self.text = read_json(text_file_path)
        self.schema = read_json(schema_file_path)
        self.he_title = he_title
        self.same_tractate_ref = self.get_same_tractate_ref(Path(schema_file_path))

    def get_same_tractate_ref(self, schema_file_path: Path) -> tuple[re.Pattern, re.Pattern] | None:
        base_titles = self.schema.get("base_text_titles") or []
        if len(base_titles) != 1:
            return None
        # הייצוא (Index.contents) נותן {"en", "he"}; רשומת אינדקס גולמית נותנת מחרוזת.
        base_title = base_titles[0]["en"] if isinstance(base_titles[0], dict) else base_titles[0]
        base_schema_path = schema_file_path.parent / f"{base_title.replace(' ', '_')}.json"
        if not base_schema_path.exists():
            return None
        base_schema = read_json(base_schema_path)
        tractate = base_schema.get("heTitle")
        if base_schema.get("categories", [])[:2] != ["Talmud", "Bavli"] or not tractate:
            return None
        return same_tractate_patterns(tractate)

    def drop_same_tractate_name(self, text: str) -> str:
        return drop_same_tractate(text, self.same_tractate_ref)

    def get_metadata(self) -> tuple[dict, list[str]]:
        era_dict = {
            "GN": {"en": "Gaonim", "he": "גאונים"},
            "RI": {"en": "Rishonim", "he": "ראשונים"},
            "AH": {"en": "Achronim", "he": "אחרונים"},
            "T": {"en": "Tannaim", "he": "תנאים"},
            "A": {"en": "Amoraim", "he": "אמוראים"},
            "CO": {"en": "Contemporary", "he": "מחברי זמננו"},
        }
        en_authors_list = []
        he_authors_list = []
        authors = self.schema.get("authors")
        if authors:
            for i in authors:
                en_author = i.get("en")
                he_author = i.get("he")
                if en_author:
                    en_authors_list.append(en_author)
                if he_author:
                    he_authors_list.append(he_author)
        self.metadata["authors"] = en_authors_list
        self.metadata["heAuthors"] = he_authors_list
        self.metadata["title"] = self.he_title or self.schema.get("heTitle")
        self.metadata["enTitle"] = self.schema.get("title")
        self.metadata["enDesc"] = self.schema.get("enDesc")
        self.metadata["enShortDesc"] = self.schema.get("enShortDesc")
        self.metadata["heDesc"] = self.schema.get("heDesc")
        self.metadata["heShortDesc"] = self.schema.get("heShortDesc")
        self.metadata["publisher"] = "sefaria"
        categories = self.schema.get("categories")
        self.metadata["categories"] = categories
        he_categories = self.schema.get("heCategories")
        self.metadata["heCategories"] = he_categories
        era = era_dict.get(self.schema.get("era", ""), {})
        self.metadata["era"] = era.get("en")
        self.metadata["heEra"] = era.get("he")
        self.metadata["language"] = self.lang
        self.metadata["pubDate"] = self.schema.get("pubDate")
        self.metadata["compDate"] = self.schema.get("compDate")
        self.metadata["pubPlace"] = None
        self.metadata["compPlace"] = self.schema.get("compPlace")
        comp_date_string = self.schema.get("compDateString", {})
        self.metadata["compDateStringEn"] = comp_date_string.get("en")
        self.metadata["compDateStringHe"] = comp_date_string.get("he")
        pub_date_string = self.schema.get("pubDateString", {})
        self.metadata["pubDateStringEn"] = pub_date_string.get("en")
        self.metadata["pubDateStringHe"] = pub_date_string.get("he")
        comp_place_string = self.schema.get("compPlaceString", {})
        self.metadata["compPlaceStringEn"] = comp_place_string.get("en")
        self.metadata["compPlaceStringHe"] = comp_place_string.get("he")
        pub_place_string = self.schema.get("pubPlaceString", {})
        self.metadata["pubPlaceStringEn"] = pub_place_string.get("en")
        self.metadata["pubPlaceStringHe"] = pub_place_string.get("he")
        extra_titles = self.schema.get("titles", [])
        self.metadata["extraTitlesHe"] = [title.get("text") for title in extra_titles if title.get("lang") == "he" and title.get("text") != self.metadata["title"] and title.get("text")]
        self.metadata["extraTitlesEn"] = [title.get("text") for title in extra_titles if title.get("lang") == "en" and title.get("text") != self.metadata["enTitle"] and title.get("text")]

        return self.metadata, he_categories if self.section_names_lang == "he" else categories

    def set_series(self, text: dict) -> None:
        if not self.metadata.get("heSeries"):
            self.metadata["heSeries"] = text.get("heCollectiveTitle")
        if not self.metadata.get("series"):
            self.metadata["series"] = text.get("collectiveTitle")
        if not self.metadata.get("series-index") and text.get("order") and isinstance(text["order"], list) and len(text["order"]) > 0:
            self.metadata["series-index"] = text["order"][-1]

    def process_book(self) -> list | None:
        self.book_content.append(f"<h1>{self.he_title or self.schema.get("heTitle")}</h1>\n")
        authors_list = []
        authors = self.schema.get("authors")
        if authors:
            for i in authors:
                i = i.get(self.section_names_lang)
                if i:
                    authors_list.append(i)
        if authors:
            self.book_content.append(f"{' ,  '.join(authors_list)}\n")
        if self.schema["schema"].get("nodes"):
            for node in self.schema['schema']['nodes']:
                key = [self.schema["schema"]["title"]]
                heb_key = [self.schema["schema"]["heTitle"]]
                if node["key"] != "default":
                    key.append(node["key"])
                    heb_key.append(node["heTitle"])
                self.process_node(key, node, self.text['text'][node['title']] if node['key'] != 'default' else self.text['text'][''], level=2, heb_title=heb_key)
        else:
            self.process_simple_book(self.schema["schema"]["title"], self.schema["schema"]["heTitle"])
        return self.book_content

    def process_simple_book(self, ref: str, heb_title: str | None = None) -> None:
        if self.section_names_lang == "he":
            section_names = self.schema["schema"].get(
                "heSectionNames"
            )
        else:
            section_names = self.schema["schema"].get(
                "sectionNames"
            )
        depth = self.schema["schema"]["depth"]
        text = self.text.get("text")
        if text:
            if has_value(text):
                self.recursive_sections(ref, section_names, text, depth, 2, heb_title=heb_title)
            else:
                print(self.book_title)

    def process_node(self, key: list, node: dict, text: list, level: int = 1, heb_title: list[str] | None = None) -> None:
        if heb_title is None:
            heb_title = []
        node_title = node['heTitle'] if self.section_names_lang == "he" else node["title"]
        if node_title:
            self.book_content.append(f"<h{min(level, 6)}>{node_title}</h{min(level, 6)}>\n")
            level += 1
        if node.get("nodes"):
            for sub_node in node['nodes']:
                if node["key"] != "default":
                    new_key = key.copy()
                    new_heb_title = heb_title.copy()
                    new_key.append(node["title"])
                    if len(set(new_key)) != len(new_key):
                        print(f"{new_key=} {key=}")
                    new_heb_title.append(node["heTitle"])
                self.process_node(new_key, sub_node, text[sub_node['title']] if sub_node['key'] != 'default' else text[''], level=level, heb_title=new_heb_title)
                # if node["key"] != "default":
                #     key.pop()
                #     heb_title.pop()
        else:  # Process nested arrays
            if self.section_names_lang == "he":
                section_names = node.get(
                    "heSectionNames"
                )
            else:
                section_names = node.get(
                    "sectionNames"
                )
            depth = node.get('depth', 1)
            ref = ", ".join(key)
            heb_ref = ", ".join(heb_title)
            self.recursive_sections(ref, section_names, text, depth, level, heb_title=heb_ref)

    def recursive_sections(
        self,
        ref: str,
        section_names: list | None,
        text: list,
        depth: int,
        level: int = 0,
        anchor_ref: list[str] | None = None,
        heb_anchor_ref: list[str] | None = None,
        heb_title: str | None = None,
        links: bool = False,
        letter: str = ""
    ) -> None:

        if anchor_ref is None:
            anchor_ref = []
        if heb_anchor_ref is None:
            heb_anchor_ref = []

        skip_section_names = ("שורה", "פירוש", "פסקה", "Line", "Comment", "Paragraph")
        """
        Recursively generates section names based on depth and appends to output list.
        :param section_names: list of section names
        :param text: input text
        :param depth: current depth of recursion
        :return: None
        """
        if depth == 0 and text != [] and not isinstance(text, bool):
            assert isinstance(text, str)
            anchor_ref_address = f"{ref} {":".join(anchor_ref)}"
            he_ref = f"{heb_title} {"&&&".join(heb_anchor_ref)}"
            if text.strip():
                self.book_content.append(f"{letter}{self.drop_same_tractate_name(text.strip()).replace("\n", "<br>")}" + "\n")
                if anchor_ref_address == "Genesis 1:1":
                    print(f"{len(self.book_content)}")
                    print(f"{self.book_content=}")
                self.refs.append({"ref": anchor_ref_address, "he_ref": he_ref, "line_index": len(self.book_content)})
        elif not isinstance(text, bool):
            if depth == 1:
                assert isinstance(text, list)
            for i, item in enumerate(text, start=1):
                letter = ""
                if has_value(item):
                    if section_names:
                        letter = (
                            to_daf(i)
                            if section_names[-depth] in ("דף", "Daf")
                            else to_gematria(i)
                        )
                    if depth > 1 and section_names and section_names[-depth] not in skip_section_names:
                        self.book_content.append(
                            f"<h{min(level, 6)}>{section_names[-depth]} {letter}</h{min(level, 6)}>\n"
                        )
                    elif section_names and section_names[-depth] not in skip_section_names and letter:
                        letter = f"({letter}) "
                    else:
                        letter = ""
                anchor_ref.append(to_eng_daf(i) if section_names and section_names[-depth] in ("דף", "Daf") else str(i))
                heb_anchor_ref.append(to_daf(i) if section_names and section_names[-depth] in ("דף", "Daf") else to_gematria(i))
                self.recursive_sections(
                    ref,
                    section_names, item,
                    depth - 1, level + 1,
                    anchor_ref,
                    heb_anchor_ref,
                    heb_title,
                    links,
                    letter
                )
                anchor_ref.pop()
                heb_anchor_ref.pop()
