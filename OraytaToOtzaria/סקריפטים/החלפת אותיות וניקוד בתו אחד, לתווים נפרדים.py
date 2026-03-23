import os
import unicodedata

# נתיב התיקייה
folder_path = r"C:\Users\Otzaria\Desktop\otzaria-library\OraytaToOtzaria\ספרים\אוצריא"

def fix_hebrew_presentation_forms(text):
    result = []

    for char in text:
        code = ord(char)

        # אם זה תו מהטווח הבעייתי
        if 0xFB1D <= code <= 0xFB4F:
            # מפרק רק אותו
            decomposed = unicodedata.normalize('NFKD', char)
            result.append(decomposed)
        else:
            result.append(char)

    return ''.join(result)


for root, dirs, files in os.walk(folder_path):
    for file in files:
        if file.endswith(".txt"):
            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                new_content = fix_hebrew_presentation_forms(content)

                if content != new_content:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)

                    print(f"✔ עודכן: {file_path}")
                else:
                    print(f"— ללא שינוי: {file_path}")

            except Exception as e:
                print(f"שגיאה בקובץ {file_path}: {e}")