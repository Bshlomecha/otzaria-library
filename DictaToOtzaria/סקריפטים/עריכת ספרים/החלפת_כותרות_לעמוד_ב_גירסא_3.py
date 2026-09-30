import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dicta_edit_core as core  # noqa: E402  (הלוגיקה והבדיקות — שם)

def update_file(replace_type):
    if not file_path:
        messagebox.showerror("קלט לא תקין", "לא נבחר קובץ.")
        return
    text = core.read_file(file_path)
    style = "colon" if replace_type == "נקודותיים" else "ayin"
    new, replacements_made = core.replace_page_b_headers(text, style)
    if replacements_made:
        core.write_file(file_path, new)
    if replacements_made == 0:
        messagebox.showinfo("!שים לב", "לא נמצא מה להחליף")
    else:
        messagebox.showinfo("!מזל טוב", f"!הקובץ עודכן בהצלחה\n\nבוצעו {replacements_made} החלפות")


# משתנה לשמירת נתיב הקובץ שנבחר
file_path = None

def choose_file():
    global file_path
    file_path = filedialog.askopenfilename(title="בחר קובץ טקסט", filetypes=[("Text Files", "*.txt")])
    if file_path:
        entry_file_path.delete(0, tk.END)  # מנקה את השדה
        entry_file_path.insert(0, file_path)  # מציג את הנתיב הנבחר
        choose_button.config(text="קובץ נבחר, המשך לבחירת סוג ההחלפה")


# יצירת חלון ראשי
root = tk.Tk()
root.title("החלפת כותרות לעמוד ב")
root.geometry("410x510")
root.configure(bg='lightblue')

# יצירת תוויות וכפתורים
label = tk.Label(root, text="!שים לב\nהתוכנה פועלת רק אם הדפים והעמודים הוגדרו כבר ככותרות\n[לא משנה באיזה רמת כותרת]\nוכן הלאה      </h3>עמוד ב<h3> :או    </h2>עמוד ב<h2> :כגון\n\n!זהירות\nבדוק היטיב שלא פספסת שום כותרת של 'דף' לפני שאתה מריץ תוכנה זו\nכי במקרה של פספוס, הכותרת 'עמוד ב' שאחרי הפספוס תהפך לכותרת שגויה", bg='lightblue', anchor='e')
label.pack(pady=10)

# כפתור לבחירת הקובץ
choose_button = tk.Button(root, text="בחר קובץ", relief="groove", bd=2, command=choose_file, bg='lightyellow')
choose_button.pack(pady=10)

# יצירת שורת עריכת נתיב
entry_file_path = tk.Entry(root, relief="groove", bd=2, width=50, bg='lightyellow')
entry_file_path.pack(pady=5)

# הודעת הסבר למשתמש
label = tk.Label(root, text=":בחר את סוג ההחלפה", bg='lightblue', anchor='e')
label.pack(pady=10)

# אפשרויות בחירה
replace_type = tk.StringVar(value="נקודותיים")

radio1 = tk.Radiobutton(root, relief="groove", bd=2, text=":החלפה לנקודותיים", variable=replace_type, value="נקודותיים", anchor='n', bg='lightblue')
radio1.pack(padx=20, pady=0)

# הסבר לדוגמא
example1 = tk.Label(root, text=":לדוגמא\n:דף ב:   דף ג:   דף ד:   דף ה\nוכן הלאה", bg='lightblue')
example1.pack(pady=5)

radio2 = tk.Radiobutton(root, relief="groove", bd=2, text=":החלפה לע\"ב", variable=replace_type, value="ע\"ב", anchor='n', bg='lightblue')
radio2.pack(padx=20, pady=0)

# הסבר לדוגמא
example2 = tk.Label(root, text=":לדוגמא\nדף ב ע\"ב   דף ג ע\"ב   דף ד ע\"ב   דף ה ע\"ב\nוכן הלאה", bg='lightblue')
example2.pack(pady=5)

# כפתור לביצוע ההחלפה
button = tk.Button(root, relief="groove", bd=2, text="בצע החלפה", command=lambda: update_file(replace_type.get()), bg='lightgreen')
button.pack(pady=20)

# התחלת הלולאה הראשית של ה-Tkinter
root.mainloop()
