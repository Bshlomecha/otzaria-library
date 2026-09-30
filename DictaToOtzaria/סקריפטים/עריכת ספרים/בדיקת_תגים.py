# -*- coding: utf-8 -*-
"""בודק הספרים האוטומטי — רצף מספרי הכותרות (h2–h6) ותקינות התגים.

הלוגיקה ב־dicta_edit_core.validate_headings / validate_tags.
במצב רגיל כל כותרת מושווית לבאה אחריה. "מצב ש"ס" (דף ב. / דף ב: כשתי
כותרות לאותו מספר) משווה לשתיים אחריה — זו ההתנהגות של "בדיקת תגים גירסא 2".
"""
import os
import sys
import tkinter as tk
from tkinter import filedialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dicta_edit_core as core  # noqa: E402

DEFAULT_SHAS = False
DEFAULT_GERSHAYIM = False


def open_file():
    file_path = filedialog.askopenfilename(filetypes=[("txt files", "*.txt")])
    if not file_path:
        return
    text = core.read_file(file_path)
    res = core.validate_headings(text, re_start_entry.get(), re_end_entry.get(),
                                 gershayim=gershayim_var.get(), shas=shas_var.get())
    tags = core.validate_tags(text)
    unmatched_regex_text.delete(1.0, tk.END)
    unmatched_tags_text.delete(1.0, tk.END)
    unmatched_regex_text.insert(tk.END, "\n".join(res["unmatched_regex"]))
    lines = list(res["unmatched_tags"])
    lines += [f"אין כותרות ברמה h{lv}" for lv in res["missing_levels"]]
    lines += [f"שורה {n}: <{t}> בלי סגירה" for n, t, _ in tags["opening_without_closing"]]
    lines += [f"שורה {n}: </{t}> בלי פתיחה" for n, t, _ in tags["closing_without_opening"]]
    lines += [f"שורה {n}: טקסט ליד כותרת" for n, _ in tags["heading_errors"]]
    unmatched_tags_text.insert(tk.END, "\n".join(lines))


root = tk.Tk()
root.title("בודק הספרים האוטומטי")

tk.Label(root, text="תו בתחילת הכותרת").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
re_start_entry = tk.Entry(root)
re_start_entry.grid(row=0, column=1, padx=10, pady=5)

tk.Label(root, text="תו בסוף הכותרת").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
re_end_entry = tk.Entry(root)
re_end_entry.grid(row=1, column=1, padx=10, pady=5)

gershayim_var = tk.BooleanVar(value=DEFAULT_GERSHAYIM)
tk.Checkbutton(root, text="כולל גרשיים", variable=gershayim_var).grid(row=2, column=0, padx=10, pady=5)
shas_var = tk.BooleanVar(value=DEFAULT_SHAS)
tk.Checkbutton(root, text='מצב ש"ס (דף ב. / דף ב:)', variable=shas_var).grid(row=2, column=1, padx=10, pady=5)

tk.Button(root, text="בחר קובץ", command=open_file).grid(row=3, columnspan=2, padx=10, pady=10)

tk.Label(root, text="כותרות שאינן תואמות את התבנית").grid(row=4, column=0, padx=10, pady=5, sticky=tk.W)
unmatched_regex_text = tk.Text(root, wrap=tk.WORD, height=10, width=50)
unmatched_regex_text.grid(row=5, column=0, columnspan=2, padx=10, pady=5)

tk.Label(root, text="רצף / תגים לא תקינים").grid(row=6, column=0, padx=10, pady=5, sticky=tk.W)
unmatched_tags_text = tk.Text(root, wrap=tk.WORD, height=10, width=50)
unmatched_tags_text.grid(row=7, column=0, columnspan=2, padx=10, pady=5)

root.mainloop()
