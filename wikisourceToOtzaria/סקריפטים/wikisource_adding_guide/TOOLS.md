# הכלים: תיעוד והרצה

## 1. התקנה (Python 3.12+ חובה)

הסיבה ל-3.12: `mediawikitootzaria/template_funcs.py` משתמש ב-f-strings מקוננות (תחביר שנתמך רק מ-3.12). חבילות: `mwparserfromhell wikitextparser gematriapy wikiexpand beautifulsoup4 requests openpyxl tqdm`
(+ `zstandard` ל-`db_search.py`). ‏`wikiexpand` מושך את `pywikibot` (כבד, אבל עובד). המומלץ: venv **מחוץ לריפו**.

### לינוקס / macOS
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh          # או: pip install uv
uv python install 3.12
uv venv --python 3.12 ~/venvs/ws
source ~/venvs/ws/bin/activate
uv pip install -r wikisourceToOtzaria/סקריפטים/wikisource_adding_guide/scripts/requirements.txt
export PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1
```
### Windows (PowerShell)
```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv python install 3.12
uv venv --python 3.12 $HOME\venvs\ws
& $HOME\venvs\ws\Scripts\Activate.ps1
uv pip install -r wikisourceToOtzaria\סקריפטים\wikisource_adding_guide\scripts\requirements.txt
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONDONTWRITEBYTECODE = "1"
```
הערות סביבה:
- תמיד `python -X utf8 ...`. בחלונות הקונסולה משבשת עברית: כתוב פלט לקבצים (הכלי כותב דוחות לקבצים) וקרא אותם. פייתון עם `-I` מתעלם מ-`sys.path`/משתני סביבה - הכלים כאן מטפלים בזה לבד.
- בחלונות, `python3` בתוך Git Bash עלול להיות stub של Microsoft Store (מדפיס "Python " ולא מריץ) - השתמש ב-`python` של ה-venv.
- ארגומנט עם מרכאה כפולה (`ספר זכרון (ריק"ם)`): בלינוקס `--page 'ספר זכרון (ריק"ם)'`. ב-PowerShell 7.3+ אותו דבר עובד; בגרסאות ישנות יש לכתוב `'ספר זכרון (ריק\"ם)'`.
  **ודא תמיד** שהכותרת בשורה הראשונה של הדוח זהה למה שהתכוונת.
- אין צורך בהתקנת ריפו נוסף: הכלי מוצא את `wikisourceToOtzaria/סקריפטים/mediawikitootzaria` שבריפו. (אם הערכה הועתקה אל מחוץ לריפו: `--lib-dir <שורש הריפו>/wikisourceToOtzaria/סקריפטים` או `OTZARIA_WS_LIB`.)

### בדיקת תקינות מלאה
```bash
python -X utf8 $G/scripts/ws_book.py --help                                   # מדפיס את הדגלים (לא טוען את המנוע)
python -X utf8 $G/scripts/ws_book.py --page 'ספר זכרון (ריק"ם)' --out /tmp/ws_smoke --plan-only --delay 0.5   # טוען מנוע + מתחבר לוויקיטקסט
```
צפוי: "סטטוס: תוכנית בלבד"; בדוח "נמצאו 14 תתי-דפים", 13 בתוכנית ("פתיחה", "שער א"-"שער יא", "נספחים"), "שלם" מדולג. (`G=wikisourceToOtzaria/סקריפטים/wikisource_adding_guide`.)

## 2. `ws_book.py` - הורדה והמרה

מה הוא עושה: מאתר תתי-דפים (`allpages`), קובע סדר לפי הקישורים בדף הראשי/בדפי הפרקים (לא לפי א"ב), מרחיב מקומית `{{#קטע:..}}` ו-`{{:..}}` (ספרים שתתי-הדפים שלהם מצטטים את דף "/שלם"),
ממיר עם הקוד הקיים של הריפו (`mediawikitootzaria`: `mediawikitohtml`, `templates`, `htmltootzaria`) **בתוספת תיקונים בצד הכלי**, בונה כותרות היררכיות, שומר הערות לספר "הערות על X" עם קישורי footnotes, כותב שורת זכויות,
מריץ את הוולידטורים של הסקיל ומפיק דוח. הוא **אינו משנה את הריפו**. הוא אינו עובר על שום דף מעבר ל-API הרשמי (`https://he.wikisource.org/w/api.php`, User-Agent `OtzariaLibraryBot/1.0`).

### דגלים

| דגל | משמעות |
|---|---|
| `--page "<כותרת>"` (חובה) | כותרת הדף הראשי כפי שבוויקיטקסט (עם רווחים; לא URL). אם הדף הוא הפניה - הכלי עוקב ורושם בדוח. אפשר גם כותרת עם `/` (למשל `תפארת ישראל על המשנה/דרוש אור החיים`). |
| `--out <תיקייה>` (חובה) | תיקיית פלט (נוצרת). |
| `--name "<שם>"` | שם הספר ב-`<h1>` ובשם הקובץ (לפני ניקוי). ברירת מחדל: כותרת הדף בלי הסוגריים האחרונים. |
| `--author "<שם>"` | שורה 2 בקובץ (ריק = שורה ריקה). רמזים למחבר מהדף מופיעים בדוח ("רמזים למחבר"). |
| `--mode auto\|chapters\|full` | `auto` (ברירת מחדל): `chapters` אם יש תתי-דפים, אחרת `single` (הדף הראשי עצמו). `chapters`: תתי-דפים לפי תוכן העניינים. `full`: רק דף "הכול" (`שלם`/`הכול`/`הכל`/`הכל בדף אחד`/`כל הספר`...; `--full-page` לשם אחר) - קוד 5 אם אין. |
| `--full-page <שם תת-דף>` | שם תת-הדף של "הכול" (ל-full, ולהשוואת שלמות ב-chapters). |
| `--exclude-page <תת-דף>` | תת-דף להחרגה (שם יחסי או מלא); חוזר. (דוגמה: `--exclude-page "לפי דפים"` במכלול.) |
| `--include-page <תת-דף>` | תת-דף שמוחרג אוטומטית (דף הכול/תוכן/ניווט) ורוצים לכלול. |
| `--include-main` | לכלול גם את גוף הדף הראשי לפני הפרקים. **לא** כשהדף הראשי כולל את תתי-הדפים (כפילות). הדוח מעיר "יש טקסט משמעותי, ייתכן שצריך --include-main" כשיש מעל 80 מילים. |
| `--template-map file.json` | `{שם תבנית: פעולה}`. פעולות: `remove` (הסר), `keep_all`, `keep_first`, `keep_last` (הפרמטר המיקומי האחרון - ברירת המחדל לתבנית לא ממופה), `bold`, `big`, `small`, `italic`, `parenthesize`, `line_break`, `new_line`, `underline`, `literal:טקסט`. |
| `--marker-style bare\|gray` | סמן ההערה בבסיס: `bare` = `<sup>N</sup>` (ברירת מחדל, בטוח ב-RTL) \| `gray` = `<sup style="color: gray;">N</sup>`. |
| `--note-line-style sup\|plain` | תחילת שורת הערה בספר ההערות: `sup` = `<sup>N</sup> טקסט` (ברירת מחדל, כבבית אהרן וישראל) \| `plain` = `N טקסט`. |
| `--plan-only` | רק תוכנית הדפים והדוח, בלי המרה (עדיין מורידים את כל הדפים). |
| `--allow-partial` | כותב ספר גם כשדף נחסם/נכשל - בשם `...PARTIAL_BLOCKED` (גם `הערות על ...PARTIAL_BLOCKED.txt` ו-`path_2` בקובץ links מכילים את הסיומת!). **אין להכניס ספר כזה לספרייה.** (נועד לדיבוג.) |
| `--delay <שניות>` | השהיה בין בקשות (ברירת מחדל 0.25; ב-429 העלה ל-2-3). |
| `--lib-dir <נתיב>` | `wikisourceToOtzaria/סקריפטים` (עם `mediawikitootzaria`). בברירת מחדל מחפש לבד (כלפי מעלה מהקובץ ומה-cwd), גם `OTZARIA_WS_LIB`. |
| `--no-validate` | לא להריץ `validate_book`/`validate_sidecars` (דורש את `.claude/skills/otzaria-book-format/scripts` בריפו). |

### פלט (בתיקיית `--out`)

- `<שם>.txt` - ספר הבסיס: שורה 1 `<h1>`, שורה 2 מחבר, שורה 3 זכויות.
- `הערות על <שם>.txt` - אם יש הערות; שורה 1 `<h1>הערות על <שם></h1>`, ואז `<sup>N</sup> טקסט` לכל הערה.
- `links/<שם>_links.json` - אם יש הערות; רשומות `footnotes` (`line_index_1` בבסיס, `line_index_2` בהערות = N+1).
- `_report/<שם>.report.txt` ו-`.json` - הדוח. מקטעים: נחסם בנטפרי; דפים שנכשלו/אדומים/חסרים/ריקים/שאינם בתוכן/שדולגו; transclusion שלא נפתר; אזהרות (כולל "בדיקת שימור"); תבניות לא ממופות (עם דוגמה); שאריות סימון;
  סטטיסטיקה; חוזה מיזוג הערות; בדיקת שימור טקסט; השוואה לדף הכול; רמזים למחבר; מידע; **תוכנית הדפים**; תוצאות הוולידטורים.

### קודי יציאה

| קוד | משמעות |
|---|---|
| 0 | הסתיים. **גם עם ממצאים** - צריך לקרוא את "סטטוס" ואת הדוח ("נכתב" = נקי; "נכתב - יש ממצאים לבדיקה (ראה דוח)"; "תוכנית בלבד"). |
| 1 | הספר נכתב אבל הוולידטור מצא שגיאות. (גם `SystemExit` עם הודעה, למשל "לא נמצאה חבילת mediawikitootzaria" - שגיאת סביבה.) |
| 2 | שימוש שגוי בפקודה (argparse). |
| 3 | **נחסם** (בנטפרי/שרת חוסם). הספר לא נכתב (אלא עם `--allow-partial`). |
| 4 | כשל בדפים (רשת אחרי 3 ניסיונות, 429/5xx, שגיאת המרה, גודל לא תואם). |
| 5 | הדף הראשי חסר/ריק, אין דף הכול ב-`--mode full`, או אין שום דף תוכן. |

### איך הוא מזהה חסימה

`Blocked` (-> "נחסם בנטפרי: <דף> (<סיבה>)", קוד 3, **בלי שום ניסיון חלופי ובלי שימוש בתוכן**) כאשר: שגיאת SSL; הפניה (redirect) למארח שאינו `he.wikisource.org`; כותרות תגובה שמכילות `netfree`; קוד HTTP שאינו 200
ואינו 429/5xx (למשל 418, 403); `Content-Type` שאינו JSON; גוף שאינו JSON תקין; מבנה בלתי צפוי. לעומת זאת: 429/5xx/timeouts/`ratelimited`/`maxlag` - עד 3 ניסיונות עם המתנה (3*ניסיון שניות) ואז `failed` (קוד 4) - זה **לא** חסימה;
שגיאת API אחרת = `failed`; `size` שאינו תואם לתוכן = `mismatch` (קטיעה?) - **לא** מתאים למרחב "עמוד:" (ראה LESSONS). מצבי דף: `ok | missing | empty | blocked | failed | mismatch`.

### מגבלות ידועות

- **`<pages>`** (ProofreadPage): לא נתמך - מופיעה אזהרה והטקסט לא נטען. הפתרון: examples/selichot_baer ו-examples/toldot_tanaim.
- **דפים שטוחים** (בלי `/`) / תוכן עניינים ידני: דרוש driver (examples/kohelet_moshe_driver.py).
- **טבלאות** (`{| |}`) מומרות לטבלת HTML בשורה אחת (colspan/rowspan; תאים מקוננים נתמכים חלקית); **רשימות מקוננות** מוצמדות לפריט הקודם; תמונות/קבצים/gallery/קטגוריות/`<references/>` מוסרים.
- **תבנית לא ממופה** - מוחלפת בפרמטר המיקומי האחרון (`keep_last`), ומדווחת. זו לא תמיד התוצאה הנכונה: פרמטר עם `=` נחשב "בשם" ולא מיקומי.
- **`{{דף שער}}`** נמחק (תוכן הכריכה לא נכנס) - אם רוצים אותו, מדביקים ידנית.
- **הערות**: `<ref>`, `{{הערה|..}}`, ותבניות הערה אחרות ב-`templates.footnote_templates`. פורמטים אחרים (ftn/ftnref) - ראה examples/korban_eliyahu_ftn_notes.py. סמן הערה בתוך כותרת מועבר לשורת הטקסט הבאה (אזהרה); הערה ריקה מוסרת.
- **`''` ו-`'''`**: ר''ת/חז''ל מוגנים (1-2 אותיות אחרי); `ה''` בסוף ציטוט (`'ימלטהו ה''`) עלול להיתפס כסימון נטוי - שאריות.
- **transclusion**: רק `{{#קטע:}}`, `{{#section:}}`, `{{:דף}}`, `{{/תת}}`; עומק 6; מעגלי = שגיאה.
- **הערות מיוחדות**: הכלי מוסיף `<h1>` ו-`<h2>`+ לפי עומק הדף; דילוג רמות כותרת מוחלש לרצף (ספירה בסטטיסטיקה "כותרות שרמתן הוחלשה").

## 3. כלי העזר (בערכה)

| סקריפט | מה עושה | שימוש |
|---|---|---|
| `scripts/db_search.py` | חיפוש ב-`seforim.db`: `find`, `title`, `text`, `lines`, `tree` | `python -X utf8 db_search.py --db <DB> title "..."`; ראה `--help`. התוכן דחוס zstd+מילון (בלוק `zstd_dict`); דורש `zstandard`. |
| `scripts/check_exists.py` | חיפוש בריפו: נתיבים (`[נארז]`/`[לא-נארז]`) + 8 מרשמים | `python -X utf8 check_exists.py "שם" ["שם2" ...]` |
| `scripts/register_metadata.py` | רישום בשלושת המרשמים, על עותקי LF, עם round-trip ובדיקת התנגשות | `--records meta.json [--write]` |
| `scripts/recompute_lineage.py` | חישוב hashes של lineage ב-LF; `--write` לעדכון; `--ref REF` לאימות קומיט | ראה PROCESS סעיף 8 |
| `scripts/run_validators.py` | כל הוולידטורים + קומיט זמני מ-index זמני | `--tests` מוסיף בדיקות יחידה; `--no-fordb` מדלג על `validate_fordb_book_names` (איטי: ~2 דקות) |
| `scripts/qa_vs_rendered.py` | שימור טוקנים מול HTML מרונדר | `--main "<דף ראשי>" --book <קובץ> [--notes <קובץ>]` |
| `.claude/skills/otzaria-book-format/scripts/*` | `validate_book`, `validate_sidecars`, `inspect_book`, `make_metadata` (בריפו) | ראה SKILL.md |

### מתי להשתמש בכל אחד מ-`scripts/examples/`

| מצב | סקריפט |
|---|---|
| הספר בנוי מדפים בשמות שטוחים ("קהלת משה א ב") ותוכן עניינים ידני | `kohelet_moshe_driver.py` (תבנית ל-build_plan משלך) |
| ההערות הן קישורי עוגן `[[דף#ftnN|[N]]]` + `[[דף#ftnrefN|[N]]]` | `korban_eliyahu_ftn_notes.py` |
| תבנית צבע/סידור מיוחד, `--order-page`, תיקוני הקלדה במקור | `sefer_michlol/ws_book_michlol.py` + `michlol_fix.py` |
| טקסט הדף הוא `<pages>`/`<section>` של עמודי סריקה, **מעט** דפים | `selichot_baer/` (fetch_pages -> compose -> run_book) |
| אלפי דפי ערכים שכולם `<pages>` | `toldot_tanaim/` (prefetch -> prefetch2 -> run_toldot; `expand_pages_tag.py`) |
| תבניות סימון שצריכות לוגיקה (רקע אפור, כפתורי ניווט) / שמירת `background-color` | `shlosha_dikduk/wrap.py` |
| בדיקת שימור שמכירה `{{נ|תיקון|..}}` | `shlosha_dikduk/chk_pres.py` |
| השוואה של שני נוסחים של אותו ספר (ויקיטקסט מול דיקטה) | `tur_bareket/cmp.py`, `cmp2.py`, `fetch_raw.py` |
| להמיר wikitext גולמי מקומי בלי הורדה (ניסוי/בדיקת תבניות) | `tur_bareket/convert_demo.py` |
| לעבור מ"ספר + הערות" ל-inline | `selichot_baer/make_inline.py` |

## 4. הסקריפטים של הסקיל (בריפו)

`.claude/skills/otzaria-book-format/scripts/`: `validate_book.py <קבצים>` (0 שגיאות = תנאי), `validate_sidecars.py --links L --book B [--target N]`, `inspect_book.py <קובץ> --toc --stats [--line N --context K] [--find טקסט]`,
`make_metadata.py --title T --check-name --repo .` (+ דגלי מטא-דאטה; `--desc-csv`, `--book-info-csv`). הם הוולידטורים הקובעים; `ws_book.py` מריץ את שני הראשונים אוטומטית אחרי כתיבה.
