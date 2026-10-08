import html
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


# כוכביות שנשארו בטקסט: הדגשה בתוך שורה אחת בלבד, כדי ששתי כוכביות רחוקות לא יהפכו לטווח ארוך
BOLD_RE = re.compile(r"(?<!\w)\*([^\s*<>](?:[^*\n<>]*[^\s*<>])?)\s?\*(?!\w)")
TOC_HEADING_RE = re.compile(r"^\s*תוכן (ה)?עניינים\s*$")


def fix_bold(text: str):
    return BOLD_RE.sub(r"<b>\1</b>", text)


def is_note_definition(link) -> bool:
    """הגדרת הערה ב-dar היא '[^N] טקסט' בתחילת פסקה; קריאה להערה נמצאת בתוך הטקסט."""
    for sibling in link.previous_siblings:
        if getattr(sibling, "name", None) is not None or str(sibling).strip():
            return False
    return link.parent is not None and link.parent.name == "p"


def drop_generated_toc(soup):
    for ul in soup.find_all("ul"):
        if ul.decomposed or ul.find_parent("ul"):
            continue
        links = ul.find_all("a")
        if links and all(a.get("href", "").startswith("#") for a in links):
            parent = ul.parent
            ul.decompose()
            if parent is not None and parent.name == "p" and not parent.get_text(strip=True):
                parent.decompose()
    for section in soup.find_all("section"):
        heading = section.find(re.compile("^h[1-6]$"))
        if heading and TOC_HEADING_RE.match(heading.get_text()):
            rest = section.get_text(strip=True)[len(heading.get_text(strip=True)):]
            if not rest:
                section.decompose()


def normalize_spaces(text: str) -> str:
    parts = re.split(r"(<pre>.*?</pre>)", text, flags=re.S)
    for i in range(0, len(parts), 2):
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in parts[i].split("\n")]
        parts[i] = "\n".join(lines)
    return "".join(parts)


WORD_CHARS = re.compile(r'[\w\'"\u05f3\u05f4\u2019]')


def _edge_char(node, last: bool) -> str:
    if node is None:
        return ""
    text = node if isinstance(node, str) else node.get_text()
    if not text:
        return ""
    return text[-1] if last else text[0]


def render_corrections(soup):
    """
    סימון התיקון ~למחוק~{להוסיף} (del/ins של dar): מילים שלמות מוצגות "(למחוק) [להוסיף]", כפי שהקהילה
    תיקנה ידנית בספרי פנינים; תיקון בתוך מילה (אות שנוספה לכתיב מלא וכד') מוצג בנוסח המתוקן בלבד.
    """
    for tag in soup.find_all(["del", "ins"]):
        if tag.parent is None:
            continue
        if tag.name == "del":
            dele = tag
            ins = tag.next_sibling if getattr(tag.next_sibling, "name", None) == "ins" else None
        else:
            dele, ins = None, tag
        first, last = dele or ins, ins or dele
        before = _edge_char(first.previous_sibling, True)
        after = _edge_char(last.next_sibling, False)
        in_word = bool(WORD_CHARS.match(before or " ") or WORD_CHARS.match(after or " "))
        if dele is not None:
            if in_word or not re.search(r"\w", dele.get_text()):
                dele.decompose()
            else:
                dele.insert(0, "(")
                dele.append(") " if ins is not None else ")")
                dele.unwrap()
        if ins is not None:
            if not in_word and re.search(r"\w", ins.get_text()):
                ins.insert(0, "[")
                ins.append("]")
            ins.unwrap()


def convert_html(html_file: Path) -> str:
    print(html_file)
    book_ref_1 = []
    book_ref_2 = []
    with html_file.open("r", encoding="utf-8") as f:
        content = f.read()
    content = html.unescape(content)
    content = fix_bold(content)
    soup = BeautifulSoup(content, "html.parser")
    all_p = soup.find_all("p")
    refs_all = {}
    ref_num = 0
    refs_set = set()
    comments_dict = {}

    book_name, book_other, printing_place, *_ = all_p
    book_name = book_name.get_text(strip=True)
    book_other = book_other.get_text(strip=True)
    printing_place = printing_place.get_text(strip=True)
    # print(f"{book_name=}, {book_other=}, {printing_place=}")

    # # מציאת הקטע של ההקדשות
    # dedications_section = soup.find("section", id="הקדשות")

    # if dedications_section:
    #     # מחיקת כל התוכן עד סוף ההקדשות
    #     for elem in list(soup.contents):
    #         elem.decompose()
    #         if elem == dedications_section:
    #             break

    # קריאה והגדרה של אותה הערה מקושרות זו לזו ב-id/href; התפקיד נקבע לפי המיקום ולא לפי הסדר
    note_links = soup.find_all("a", id=re.compile(r"fnref.*"))
    group_of = {}
    for link in note_links:
        a, b = link["id"], link["href"][1:]
        root = group_of.get(a) or group_of.get(b) or a
        group_of[a] = group_of[b] = root
    roles = [(link, group_of[link["id"]], is_note_definition(link)) for link in note_links]
    groups_with_call = {group for _, group, is_definition in roles if not is_definition}
    for link, group, is_definition in roles:
        if group not in refs_all and (not is_definition or group not in groups_with_call):
            ref_num += 1
            refs_all[group] = str(ref_num)
    for link, group, is_definition in roles:
        if not is_definition:
            new_tag = soup.new_tag("sup")
            new_tag.string = refs_all[group]
            new_tag["style"] = "color: gray;"
            link.replace_with(new_tag)
        else:
            link.find("sup").string = refs_all[group]
            new_tag = soup.new_tag("small")
            new_tag["style"] = "color: gray;"
            link.parent.wrap(new_tag)

    drop_generated_toc(soup)
    for tag in soup.find_all(True):
        all_tags.add(tag.name)
        if tag.has_attr("id"):
            del tag["id"]
    for section in soup.find_all(["section", "p"]):
        section.unwrap()
    for heading in soup.find_all(re.compile('^h[1-6]$')):
        current_level = int(heading.name[1])
        new_level = min(current_level + 1, 6)
        heading.name = f'h{new_level}'
        for br in heading.find_all("br"):
            br.replace_with(" ")
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()
    render_corrections(soup)
    for tag in soup.find_all("a"):
        tag.unwrap()
    for old_name, new_name in (("strong", "b"), ("em", "i")):
        for tag in soup.find_all(old_name):
            tag.name = new_name
    text = str(soup)
    text = re.sub(r"<(h[1-6])>(.*?)</\1>", lambda m: m.group(0).replace("\n", " "), text, flags=re.S)
    text = f'<h1>{book_name}</h1>\n{book_other}\n{text}'
    text = normalize_spaces(text)
    text = re.sub(r"\n+", "\n", text)
    # print(f"{len(book_ref_1)=} {len(set(book_ref_1))=}")
    # print(f"{len(book_ref_2)=} {len(set(book_ref_2))=}")
    # print(comments_dict)
    final_comments = {}
    # final_text_lines = text.strip().split("\n")
    # for key, comment in comments_dict.items():
    #     for tag in comment.find_all(["a", "p"]):
    #         tag.unwrap()
    #     for tag in comment.find_all(True):
    #         if tag.has_attr("id"):
    #             del tag["id"]
    #     final_comments[int(key)] = comment.decode_contents().strip()
    dict_links = []
    # for index, line in enumerate(final_text_lines, start=1):
    #     find = re.findall(r'<sup style="color: gray;">(\d+)</sup>', line)
    #     dict_links.extend([
    #         {
    #             "line_index_1": index,
    #             "heRef_2": "הערות",
    #             "path_2": f"הערות על {html_file.stem}.txt",
    #             "line_index_2": int(i),
    #             "Conection Type": "commentary"
    #         } for i in find
    #     ])

    # print(final_comments)
    return text.strip(), book_name, book_other, printing_place


all_tags = set()


def main():
    main_folder = Path("new/html")
    target_folder = Path("new/converted_html")
    books_folder = target_folder / "אוצריא"
    comments_folde = books_folder / "הערות"
    links_folder = target_folder / "links"
    metadata_file = books_folder / "metadata.json"
    target_folder.mkdir(exist_ok=True, parents=True)
    books_folder.mkdir(exist_ok=True, parents=True)
    # comments_folde.mkdir(exist_ok=True, parents=True)
    # links_folder.mkdir(exist_ok=True, parents=True)
    parents = set()
    metadata = []
    for root, _, files in main_folder.walk():
        root_path = Path(root)
        for file in files:
            if not file.endswith(".html"):
                continue
            html_file = root_path / file
            # print(f"Processing {html_file}")
            new_html, book_name, book_other, printing_place = convert_html(html_file)
            relative_path = html_file.relative_to(main_folder)
            # target_file = (books_folder / relative_path).with_suffix(".txt")
            target_file = books_folder.joinpath(*(p.replace("_", " ") for p in relative_path.parts)).with_suffix(".txt")
            metadata_entry = {
                "title": target_file.stem,
                "heAuthors": [book_other],
                "pubPlaceStringHe": printing_place,
                "heCategories": [p.replace("_", " ") for p in relative_path.parent.parts],
                "Sourcefolder": "pninim",
                "publisher": "pninim"
            }
            metadata.append(metadata_entry)

            target_file.parent.mkdir(exist_ok=True, parents=True)
            with target_file.open("w", encoding="utf-8") as f:
                f.write(new_html)

    with metadata_file.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        # target_comments_file = comments_folde / f"הערות על {target_file.stem}.txt"
        # if final_comments:
        #     with target_comments_file.open("w", encoding="utf-8") as f:
        #         for key in sorted(final_comments.keys()):
        #             f.write(f"{key} {final_comments[key]}\n")
        # json_file = links_folder / f"{target_file.stem}_links.json"
        # if dict_links:
        #     with json_file.open("w", encoding="utf-8") as f:
        #         import json
        #         json.dump(dict_links, f, ensure_ascii=False, indent=2)
    # print(parents)
    print(all_tags)


if __name__ == "__main__":
    main()
