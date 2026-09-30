import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.ttk import Combobox
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dicta_edit_core as core  # noqa: E402  (הלוגיקה והבדיקות — שם)

def process_file(file_path, header_level):
    """כותרת 'עמוד ב' לכל שורה שמתחילה ב'עמוד ב' / ע"ב (ר' core.create_page_b_headers).

    "עבודה" / "עב" אינם ע"ב, ושום פיסוק בשורה אינו נמחק (באגים שתוקנו).
    """
    text = core.read_file(file_path)
    new, count = core.create_page_b_headers(text, header_level)
    if count:
        core.write_file(file_path, new)
    if count == 0:
        messagebox.showinfo("!שים לב", "לא נמצא מה להחליף")
    else:
        messagebox.showinfo("!מזל טוב", f"נוספו {count} כותרות לקובץ.")




# פונקציה לבחירת קובץ
def select_file():
    file_path = filedialog.askopenfilename(
        title="בחר קובץ", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    if file_path:
        file_entry.delete(0, tk.END)
        file_entry.insert(0, file_path)

# פונקציה להרצת הסקריפט
def run_script():
    file_path = file_entry.get()

    try:
        header_level = int(header_var.get())  # המרה למספר שלם
    except ValueError:
        messagebox.showwarning("שגיאה", "רמת הכותרת צריכה להיות מספר בין 2 ל-9")
        return    

    if not file_path:
        messagebox.showwarning("קלט לא תקין", "בחר קובץ תחילה")
        return
    
    if header_level < 2 or header_level > 9:
        messagebox.showwarning("שגיאה", "בחר רמת כותרת בין 2 ל-9")
        return
    
    process_file(file_path, header_level)

# יצירת ממשק גרפי
root = tk.Tk()
root.title("'יצירת כותרות ל'עמוד ב")
root.configure(bg='lightyellow')

label = tk.Label(root, text="'התוכנה יוצרת כותרת בכל מקום בקובץ שכתוב בתחילת שורה - 'עמוד ב', או 'ע\"ב\nבאם כתוב את המילה 'שם' לפני המילים הנ\"ל, המילה 'שם' נמחקת\n'ובאם כתוב את המילה 'גמרא' לפני המילים 'עמוד ב' או 'ע\"ב\nהתוכנה תעביר את המילה 'גמרא' לתחילת השורה שאחרי הכותרת\n!בזכות כללים אלו בעז\"ה לא נפספס שום כותרת", bg='lightyellow')
label.grid(row=0, column=0, columnspan=3, sticky="n", padx=10, pady=15)

# שדה לבחירת קובץ
tk.Label(root, text=":נתיב קובץ", bg='lightyellow').grid(row=1, column=2, padx=20, pady=5, sticky="e")
file_entry = tk.Entry(root, relief="groove", bd=2, width=41)
file_entry.grid(row=1, column=1, columnspan=3, padx=0, pady=5, sticky="w")
tk.Button(root, text="עיון", command=select_file, bg='#F0E68C', relief="groove").grid(row=1, column=0, columnspan=3, padx=30, pady=5, sticky="w")

# בחירת רמת כותרת
tk.Label(root, text=":בחר רמת כותרת", bg='lightyellow', anchor='e').grid(row=2, column=2, padx=1, pady=5, sticky="nw")
header_var = tk.StringVar(root)  
header_choices = [str(i) for i in range(2, 10)]  # ערכים תקינים בין 2 ל-9
header_menu = Combobox(root, textvariable=header_var, values=header_choices, width=1, justify=tk.RIGHT)
header_menu.grid(row=2, column=1, padx=1, pady=5, sticky="e")
header_var.set("3")

# כפתור 'הרץ כעת'
tk.Button(root, text="הרץ כעת", command=run_script, bg='#F0E68C', relief="groove").grid(row=3, column=0, columnspan=3, padx=10, pady=10)

root.mainloop()
