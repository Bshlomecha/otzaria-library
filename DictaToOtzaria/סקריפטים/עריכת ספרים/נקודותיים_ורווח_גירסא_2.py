# -*- coding: utf-8 -*-
"""נקודותיים ורווח → נקודותיים וירידת שורה (סוף עניין בספרים הישנים).

הלוגיקה ב־dicta_edit_core.colon_newline. תוקן לעומת הגרסה הקודמת, שהחליפה
כל ':' + רווח (`re.sub(r':\\s', ':\\n')`) בכל הקובץ:
  * לא בשורות כותרת, ולא בשתי השורות הראשונות (<h1> ומחבר);
  * לא בתוך תג פתוח (<b>מחצלת: עשויה</b>);
  * לא אחרי מבוא לציטוט (וז"ל: / וזה לשונו:);
  * לא יוצרת שורות ריקות (': \\n' כבר בסוף שורה נשאר כמו שהוא).
"""
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dicta_edit_core as core  # noqa: E402

root = tk.Tk()
root.withdraw()  # מסתיר את החלון הראשי

file_path = filedialog.askopenfilename(title="בחר קובץ טקסט", filetypes=[("Text Files", "*.txt")])
try:
    if not file_path:
        messagebox.showinfo("קלט לא תקין", "לא נבחר קובץ")
    else:
        content = core.read_file(file_path)
        new_content, count = core.colon_newline(content)
        if not count:
            messagebox.showinfo("!שים לב", "לא נמצא מה להחליף")
        else:
            core.write_file(file_path, new_content)
            messagebox.showinfo("!מזל טוב", f"ההחלפה הושלמה בהצלחה! ({count} שורות חדשות)")
except Exception as e:
    messagebox.showerror("שגיאה", f"ארעה שגיאה במהלך העיבוד: {str(e)}")
