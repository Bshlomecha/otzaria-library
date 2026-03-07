import html
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


def fix_bold(text: str):
    esc = re.escape("*")
    lookbehind = r'(?<!\w)'
    regex = fr"{lookbehind}{esc}([^\\s{esc}](?:[^{esc}]*[^\\s{esc}])?){esc}(?!\\w)|{esc}([^\\s{esc}]+){esc}"

    def replacement(match: re.Match) -> str:
        content = match.group(1) or match.group(2)
        return f"<b>{content}</b>"
    if re.sub(regex, replacement, text) != text:
        print("eroor hear")
    return re.sub(regex, replacement, text)


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

    for link in soup.find_all("a", id=re.compile(r"fnref.*")):
        link_href = link["href"][1:]
        link_id = link["id"]
        # print(f"{link_href=} {link_id=}")
        # print(f"{link=} {link["id"]=}")
        # link_split = link["id"].replace("fnref", "").split("_")
        # # print(link["id"])
        # book_ref_1.append(link_split[0])
        # book_ref_2.append(link_split[1])
        if link_href not in refs_set and link_id not in refs_set:
            new_tag = soup.new_tag("sup")
            ref_num += 1
            # new_tag.string = re.sub(r"\D", "", str(ref_num))
            new_tag.string = str(ref_num)
            new_tag["style"] = "color: gray;"
            link.replace_with(new_tag)
            refs_set.add(link_href)
            refs_set.add(link_id)
            refs_all[link_href] = str(ref_num)
            refs_all[link_id] = str(ref_num)
        else:
            # print(link)
            parent = link.parent
            # print(parent.name)
            new_tag = soup.new_tag("small")
            ref_name = refs_all.get(link_href, refs_all.get(link_id))
            link.find("sup").string = ref_name
            # link.unwrap()
            # print(f"{list(link.children)=}")
            new_tag["style"] = "color: gray;"
            parent.wrap(new_tag)
            # comments_dict[ref_name] = parent.extract()
            # parent.replace_with(new_tag)

    for tag in soup.find_all(True):
        all_tags.add(tag.name)
        if tag.has_attr("id"):
            del tag["id"]
        # all_tags.add(tag.name)
    for section in soup.find_all(["section", "p"]):
        if section.id == "תוכן_העניינים":
            section.decompose()
        else:
            section.unwrap()
    for heading in soup.find_all(re.compile('^h[1-6]$')):
        current_level = int(heading.name[1])
        new_level = min(current_level + 1, 6)
        heading.name = f'h{new_level}'
    for tag in soup.find_all(["style", "script", "del"]):
        tag.decompose()
    for tag in soup.find_all(["a", "ins"]):
        tag.unwrap()
    text = str(soup)
    # text = f'<html dir="rtl"><body><h1>{book_name}</h1>\n{book_other}\n{text}</body></html>'
    text = f'<h1>{book_name}</h1>\n{book_other}\n{text}'
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
all_tags = set()
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
