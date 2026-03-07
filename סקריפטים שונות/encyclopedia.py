import re
from pathlib import Path
from typing import Literal

COLUMN_PATTERN = re.compile(r"\[טור .*?\]")
COLUMN_PATTERN_B = re.compile(r"\[עמוד [א-ת]{1,3} טור")
SPLITTER_PATTERN = re.compile(r"^=+\s*$")
CHAPTER_PATTERN = re.compile(r"^([א-ת]+)\.\s*(.*)[;.]$")
CHAPTER_WITHOUT_LETTER_PATTERN = re.compile(r"^(.{1,30}?)\s*[;.]$")
BOOK_NAME_PATTERN = re.compile(r"אנציקלופדיה תלמודית כרך [א-ת]{1,3}, ")
TALMUD_PATTERN = re.compile(r"^אנציקלופדיה תלמודית מפתח תלמודי ([א-ת ]+?) דף ([א-ת]+?) עמוד ([א-ת]+?)$")


def fix_line(line: str) -> str:
    line = re.sub(COLUMN_PATTERN, "", line).strip()
    return re.sub(COLUMN_PATTERN_B, "", line).strip()


def talmud(line: str) -> Literal[False] | tuple[str, str, str]:
    match = re.match(TALMUD_PATTERN, line)
    if not match:
        return False
    return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()


def is_splitter(line: str) -> bool:
    if not line.strip():
        return False
    return not bool(re.sub(SPLITTER_PATTERN, "", line).strip())


def header(line: str) -> str:
    return re.sub(BOOK_NAME_PATTERN, "", line).strip()


def chapter(line: str) -> tuple[str, str]:
    match = re.match(CHAPTER_PATTERN, line.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", ""


def chapter_without_letter(line: str) -> str:
    match = re.match(CHAPTER_WITHOUT_LETTER_PATTERN, line.strip())
    if match:
        return match.group(1).strip()
    return ""


def process_book(string: str) -> str:
    # string = fix_file(string)
    result = []
    lines = string.split("\n")
    chapter_section = False
    chapter_dict = {}
    chapters_without_letters = set()
    current_ot = None
    talmud_section = False
    talmud_mas = None
    talmud_daf = None
    for index, line in enumerate(lines):
        line = fix_line(line)
        if is_splitter(line):
            continue
        if index + 1 < len(lines) and is_splitter(lines[index + 1]):
            talmud_sec = talmud(line)
            if talmud_sec:
                if talmud_section is False:
                    result.append("<h2>מפתח תלמודי</h2>")
                    talmud_section = True
                mas, daf, amud = talmud_sec
                if mas != talmud_mas:
                    result.append(f"<h3>{mas}</h3>")
                    result.append(f"<h4>{daf}</h4>")
                    result.append(f"<h5>{amud}</h5>")
                    talmud_mas, talmud_daf = mas, daf
                    continue
                if daf != talmud_daf:
                    result.append(f"<h4>{daf}</h4>")
                    result.append(f"<h5>{amud}</h5>")
                    talmud_daf = daf
                    continue
                result.append(f"<h5>{amud}</h5>")
                continue
            header_text = header(line)
            if header_text[0] != current_ot:
                result.append(f"<h2>אות {header_text[0]}</h2>")
                current_ot = header_text[0]
            result.append(f"<h3>{header_text}</h3>")
            continue
        if line.strip() == "הפרקים:":
            chapter_section = True
            if chapter_dict:
                print(chapter_dict)
            if chapters_without_letters:
                print(chapters_without_letters)
            chapter_dict.clear()
            chapters_without_letters.clear()
            continue
        if not line.strip():
            chapter_section = False
            continue
        if chapter_section:
            chapter_num, chapter_title = chapter(line)
            if not chapter_num or not chapter_title:
                chapter_title = chapter_without_letter(line)
                if chapter_title:
                    chapters_without_letters.add(chapter_title)
                else:
                    print(line.strip())
                    result.append(f"////{line.strip()}////")
                continue
            chapter_dict[chapter_num] = chapter_title
            continue
        letter, _, text_body = line.partition(".")
        if text_body.strip() and letter.strip():
            letter = letter.strip()
            text_body = text_body.strip()
            if letter in chapter_dict:
                result.append(f"<h4>{letter} {chapter_dict[letter]}</h4>")
                del chapter_dict[letter]
                result.append(text_body)
                continue
            if letter in chapters_without_letters:
                result.append(f"<h4>{letter}</h4>")
                chapters_without_letters.remove(letter)
                result.append(text_body)
                continue
        result.append(line.strip())
    return "\n".join(result)


def main() -> None:
    file = Path("אנציקלופדיה תלמודית.txt")
    out_file = Path("res.txt")
    text = file.read_text("utf-8")
    result = process_book(text)
    out_file.write_text(result, "utf-8")


if __name__ == "__main__":
    main()
