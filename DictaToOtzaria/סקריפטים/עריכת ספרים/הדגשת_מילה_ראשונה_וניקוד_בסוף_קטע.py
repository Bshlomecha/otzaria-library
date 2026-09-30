import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dicta_edit_core as core  # noqa: E402  (הלוגיקה והבדיקות — שם)

def process_file(file_path, add_ending, emphasize_start):
    """ר' core.emphasize_and_punctuate. מתחיל אחרי שורת <h1> ושורת המחבר
    (הגרסה הקודמת דילגה גם על השורה השלישית), ושתי הפעולות יחד כבר לא
    מאבדות את סימן הסוף."""
    try:
        text = core.read_file(file_path)
        ending = {"נקודה": ".", "נקודתיים": ":"}.get(add_ending or "")
        new, changes = core.emphasize_and_punctuate(text, ending=ending,
                                                    emphasize=bool(emphasize_start))
        if changes:
            core.write_file(file_path, new)
            messagebox.showinfo("!מזל טוב", f"השינויים נשמרו בהצלחה ({changes} שורות)")
        else:
            messagebox.showinfo("!שים לב", "אין מה לשנות")
    except Exception as e:
        messagebox.showerror("!שגיאה", f"שגיאה בעיבוד הקובץ: {str(e)}")


def run_processing():
    # תוקן: selected_file_path לא התעדכן אף פעם (update_file_path לא חובר)
    path = file_path_entry.get().strip() or selected_file_path
    if path:
        process_file(path, ending_var.get(), emphasize_var.get())
    else:
        messagebox.showinfo("קלט לא תקין", "אנא בחר קובץ תחילה")



def select_file():
    file_path = filedialog.askopenfilename(title="בחר קובץ", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
    if file_path:
        file_path_entry.delete(0, tk.END)
        file_path_entry.insert(0, file_path)

def update_file_path():
    global selected_file_path
    selected_file_path = file_path_entry.get()


# יצירת הממשק הגרפי
root = tk.Tk()
root.title("הדגשה וניקוד")
root.geometry("280x350")

selected_file_path = None

open_button = tk.Button(root, relief="groove", bd=2, text="בחר קובץ", command=select_file)
open_button.pack(pady=10)

tk.Label(root, text=":נתיב קובץ").pack(pady=0)
file_path_entry = tk.Entry(root, relief="groove", bd=2, width=40)
file_path_entry.pack(pady=10)

# בחירה להוספת נקודה או נקודותיים
ending_var = tk.StringVar(value="נקודה")
tk.Label(root, text=":בחר פעולה לסוף קטע").pack(padx=10, pady=5)
tk.Radiobutton(root, text="הוסף נקודה", variable=ending_var, value="נקודה").pack(padx=15, anchor=tk.E)
tk.Radiobutton(root, text="הוסף נקודתיים", variable=ending_var, value="נקודתיים").pack(padx=15, anchor=tk.E)
tk.Radiobutton(root, text="ללא הוספת סימן", variable=ending_var, value=None).pack(padx=15, anchor=tk.E)

# בחירה להדגשת תחילת קטע
emphasize_var = tk.BooleanVar()
tk.Checkbutton(root, text="הדגש את תחילת הקטעים", variable=emphasize_var).pack(padx=15, pady=20, anchor=tk.E)

run_button = tk.Button(root, relief="groove", bd=2, text="הרץ כעת", command=run_processing)
run_button.pack(pady=20)

root.mainloop()
