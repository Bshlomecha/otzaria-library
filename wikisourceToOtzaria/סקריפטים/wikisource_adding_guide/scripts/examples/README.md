# examples - סקריפטי עזר שנכתבו לספרים ספציפיים

כל אלה **דוגמאות**: הם נכתבו כדי להתגבר על מבנה חריג של ספר אחד, ושימושיים כתבנית כשנתקלים במבנה דומה. בראש כל קובץ
יש הסבר מה הוא עושה ועל איזה ספר נכתב. כולם נטענים את `../ws_book.py` מהמיקום היחסי שלהם (אין נתיבים קשיחים), ולכן
אפשר להריץ אותם מכל תיקייה: `python -X utf8 <נתיב>/examples/<קובץ>.py ...`.

**כל מה שהורץ כאן אומת:** `selichot_baer` (fetch -> compose -> run_book -> make_inline), `korban_eliyahu_ftn_notes.py` ו-`sefer_michlol`
משחזרים בית-בבית את הקבצים שבריפו (ספר, הערות, links), `kohelet_moshe_driver.py` רץ ב-`--plan-only`, `toldot_tanaim/run_toldot.py` רץ על
אות אחת (צ) ו-`tur_bareket`/`shlosha_dikduk` נבדקו רק לתחביר (ראה BLOCKED_BOOKS.md).

| קובץ/תיקייה | הספר | הבעיה שהוא פותר |
|---|---|---|
| `kohelet_moshe_driver.py` | קהלת משה (משה הכהן) | ספר מדפים **שטוחים** בלי `/` ("קהלת משה א ב") ותוכן עניינים ידני: מחליף את `build_plan` ב-monkey-patch. כולל `ACCEPT_MISSING` לקישורים אדומים אמיתיים. |
| `korban_eliyahu_ftn_notes.py` | קרבן אליהו | הערות בפורמט `[[דף#ftnN\|[N]]]` + `[[דף#ftnrefN\|[N]]]` (לא `<ref>`): המרה ל-`<ref>` לפני ההמרה. |
| `sefer_michlol/` | ספר מכלול | גרסה מורחבת של `ws_book.py` (צבע גופן, retry ארוך, `--order-page`, תיקוני מקור `michlol_fix.py`, `norm_start` לרמות כותרת), `tmap.json`. |
| `selichot_baer/` | הסליחות לכל השנה | דפים שמורכבים מ-`<pages>`/`<section>` של עמודי סריקה (מרחב "עמוד:"): `fetch_pages.py` -> `compose.py` -> `run_book.py`; `qa_tokens.py`/`parse_rendered.py` לבדיקה מול ה-HTML המרונדר; `make_inline.py` (הערות inline). |
| `shlosha_dikduk/wrap.py` | שלשה ספרי דקדוק | מיפוי תבניות סימון אפור + שמירת `background-color`; דפוס "עטוף את ws_book". `chk_pres.py` - בדיקת שימור שמכירה `{{נ\|..}}`. |
| `toldot_tanaim/` | תולדות תנאים ואמוראים | 2,217 דפי ערכים שכולם `<pages .../>`: `prefetch.py`/`prefetch2.py` (הורדה בצובר), `expand_pages_tag.py` (הרחבת `<pages>`), `run_toldot.py` (טיוטה: cache + הרחבה + `--letters`), `analyze_letters.py` (קישורים אדומים), `analyze_pages_tags.py`, `run_cached.py` (המקורי). |
| `tur_bareket/` | טור ברקת | השוואה לדיקטה: `fetch_raw.py` (הורדת wikitext גולמי), `cmp.py`, `cmp2.py` (יישור יחידות, סיווג הבדלים), `convert_demo.py` (שימוש ב-ws_book כספרייה), `raw_status.json` (מצב ההורדה ב-2026). |
| `meta_samples/` | כל הנ"ל | דוגמאות לקובץ הרשומות ש-`register_metadata.py` קורא, ודוגמת קובץ links של footnotes. **ה-notes שבהן נכתבו לפני שהשורש `wikisourceToOtzaria/links` הוחלף ל-present** - ההערות על "links לא הועתק" אינן עדכניות. |

דפוס חוזר שכדאי להכיר (בכל הדוגמאות): `import ws_book` -> דריסה של פונקציה אחת (`WikiClient.get_page`, `WikiClient.allpages`, `build_plan`,
`convert_page`, `apply_template_map`, `clean_style`) -> `sys.exit(ws_book.main())`. ws_book.py עצמו אינו משתנה.
