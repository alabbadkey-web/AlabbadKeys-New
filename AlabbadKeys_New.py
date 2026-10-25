import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import re, sqlite3, os, sys, hashlib, secrets, hmac, shutil, tempfile, webbrowser, html, json, threading, zipfile
import subprocess, ssl
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

DB = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "alabbad_keys_new.db")

# ------------------------------------------------------------------ الألوان والخط
APP_VERSION = "16.4.1"
GITHUB_REPO = "alabbadkey-web/AlabbadKeys-New"
UPDATE_ASSET_NAME = "AlabbadKeys_New.exe"
FONT = "Segoe UI"
NAVY = "#0f172a"
SIDEBAR = "#111827"
ACCENT = "#2563eb"
ACCENT_D = "#1d4ed8"
BG = "#f1f5f9"
TEXT = "#0f172a"
MUTED = "#64748b"
GREEN = "#16a34a"
RED = "#dc2626"
AMBER = "#d97706"
BORDER = "#e2e8f0"

# ------------------------------------------------------------------ الصلاحيات
# (المفتاح، الوصف، مفعّل افتراضيًا للموظف الجديد)
PERMS = [
    ("inv_add", "إضافة أصناف جديدة", True),
    ("inv_edit", "تعديل الأصناف", False),
    ("barcode", "طباعة الباركود", True),
    ("view_wholesale", "رؤية سعر الجملة", False),
    ("view_cost", "رؤية وتحديد التكلفة والأرباح", False),
    ("sales", "إصدار فواتير البيع", True),
    ("sell_wholesale", "البيع بالجملة", False),
    ("below_price", "البيع بأقل من الحد المسموح", False),
    ("sales_all", "رؤية مبيعات كل الموظفين", False),
    ("whatsapp", "إرسال الفاتورة واتساب", True),
    ("customers", "صفحة العملاء والديون", False),
    ("debt_pay", "تسجيل دفعات الديون", False),
    ("purchases", "المشتريات (تظهر الأسعار)", False),
    ("suppliers", "الموردون وبياناتهم", False),
    ("expenses", "المصروفات", False),
    ("reports", "التقارير", False),
    ("bonus", "تسجيل الأعمال والبونص", True),
    ("shortage", "قائمة النواقص وإرسالها لمسؤول المشتريات", False),
    ("po", "إنشاء طلب شراء للمورد (يُرسل لجوال المدير)", True),
]
PERM_LABELS = {k: l for k, l, _ in PERMS}
DEFAULT_PERMS = {k for k, _, d in PERMS if d}
ALL_PERMS = {k for k, _, _ in PERMS}


def perms_to_str(p):
    return ",".join(sorted(p))


def str_to_perms(s):
    if s is None:
        return set(DEFAULT_PERMS)
    return {x for x in str(s).split(",") if x in ALL_PERMS}


# قائمة ابتدائية للشركات والموديلات (تقدر تعدّلها من صفحة "السيارات")
SEED_CARS = {
    "تويوتا": ["كامري", "كورولا", "يارس", "لاندكروزر", "هايلكس", "فورتشنر", "أفالون", "برادو", "راف فور"],
    "نيسان": ["صني", "التيما", "باترول", "ماكسيما", "اكستيرا", "كيكس"],
    "هيونداي": ["النترا", "سوناتا", "اكسنت", "توسان", "سنتافي", "ازيرا"],
    "كيا": ["سيراتو", "اوبتيما", "ريو", "سبورتاج", "سورنتو"],
    "فورد": ["تورس", "اكسبلورر", "اكسبيديشن", "ايدج", "موستنج"],
    "شيفروليه": ["ماليبو", "كابرس", "تاهو", "سوبربان", "سلفرادو"],
    "جي إم سي": ["يوكن", "سييرا"],
    "هوندا": ["اكورد", "سيفيك", "سي آر في"],
    "مازدا": [], "ميتسوبيشي": [], "لكزس": [], "مرسيدس": [], "بي إم دبليو": [],
    "سوزوكي": [], "ايسوزو": [], "جيب": [], "دودج": [], "ام جي": [], "شانجان": [], "جيلي": [], "هافال": [],
}

SEED_JOBS = ["برمجة سيارة داخل العمل", "برمجة سيارة خارج العمل", "دوام أوفر تايم"]

STATUS_AR = {"pending": "⏳ بانتظار الاعتماد", "approved": "✅ معتمد", "rejected": "❌ مرفوض"}


def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def pw_hash(p, s=None):
    s = s or secrets.token_hex(16)
    return s, hashlib.pbkdf2_hmac("sha256", p.encode(), bytes.fromhex(s), 150000).hex()


def num(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0


def sar(v):
    return f"{v:,.2f} ر.س"


def clean_name(v):
    return " ".join(str(v or "").split())


def normalize_phone(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("05"):
        digits = "966" + digits[1:]
    elif len(digits) == 9 and digits.startswith("5"):
        digits = "966" + digits
    return digits


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ التحديث من GitHub Releases
def _ssl_contexts():
    """شهادات الأمان: نجرّب الشهادات المدمجة في البرنامج (certifi) ثم شهادات ويندوز."""
    ctxs = []
    try:
        import certifi
        ctxs.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    ctxs.append(ssl.create_default_context())
    return ctxs


def safe_urlopen(req, timeout=15):
    """مثل urlopen لكنه لا يفشل إذا كانت شهادات ويندوز ناقصة (خطأ CERTIFICATE_VERIFY_FAILED)."""
    last = None
    for ctx in _ssl_contexts():
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ssl.SSLError) as e:
            if not isinstance(getattr(e, "reason", e), ssl.SSLError):
                raise
            last = e
    raise last


def version_tuple(v):
    """'v16.0.1' -> (16, 0, 1)"""
    nums = [int(x) for x in re.findall(r"\d+", str(v or ""))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(latest, current):
    return version_tuple(latest) > version_tuple(current)


def fetch_latest_release(repo=None, api="https://api.github.com", timeout=15):
    """يرجع بيانات آخر إصدار منشور، أو None إذا لا يوجد إصدار منشور بعد."""
    repo = repo or GITHUB_REPO
    req = urllib.request.Request(f"{api}/repos/{repo}/releases/latest",
                                 headers={"User-Agent": "AlabbadKeys-Updater", "Accept": "application/vnd.github+json"})
    try:
        with safe_urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    tag = str(rel.get("tag_name", "")).strip()
    asset = next((a for a in rel.get("assets", []) if a.get("name") == UPDATE_ASSET_NAME and a.get("browser_download_url")), None)
    digest = str((asset or {}).get("digest") or "")
    return {
        "tag": tag,
        "version": tag.lstrip("vV"),
        "url": (asset or {}).get("browser_download_url", ""),
        "has_asset": asset is not None,
        "sha256": digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else "",
        "notes": str(rel.get("body") or "").strip(),
        "page": rel.get("html_url") or f"https://github.com/{repo}/releases/latest",
    }


def download_update(url, sha256="", progress=None):
    """ينزّل ملف EXE الجديد إلى مجلد مؤقت ويتحقق منه، ويرجع مساره."""
    temp_dir = tempfile.mkdtemp(prefix="alabbad_update_")
    new_exe = os.path.join(temp_dir, UPDATE_ASSET_NAME)
    req = urllib.request.Request(url, headers={"User-Agent": "AlabbadKeys-Updater"})
    h = hashlib.sha256()
    with safe_urlopen(req, timeout=60) as r, open(new_exe, "wb") as out:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
    if os.path.getsize(new_exe) < 1_000_000:
        raise RuntimeError("حجم ملف التحديث غير متوقع؛ لم يتم تثبيته.")
    if sha256 and h.hexdigest().lower() != sha256:
        raise RuntimeError("فشل التحقق من سلامة الملف المنزّل؛ لم يتم تثبيته.")
    return new_exe


def update_bat_text():
    """سكربت يستبدل ملف EXE بعد إغلاق البرنامج (قاعدة البيانات والصور لا تُلمس)."""
    lines = [
        "@echo off",
        "set OLD=%~1",
        "set NEW=%~2",
        "set /a W=0",
        ":wait",
        'tasklist /FI "IMAGENAME eq %~nx1" 2>NUL | find /I "%~nx1" >NUL',
        "if errorlevel 1 goto copy",
        "set /a W+=1",
        "if %W% GEQ 40 goto copy",
        "timeout /t 1 /nobreak >NUL",
        "goto wait",
        ":copy",
        "set /a T=0",
        ":again",
        'copy /Y "%NEW%" "%OLD%" >NUL 2>&1',
        "if not errorlevel 1 goto ok",
        "set /a T+=1",
        "if %T% GEQ 15 goto fail",
        "timeout /t 1 /nobreak >NUL",
        "goto again",
        ":ok",
        'start "" "%OLD%"',
        'del "%NEW%" >NUL 2>&1',
        'del "%~f0" >NUL 2>&1',
        "exit /b 0",
        ":fail",
        "echo Update failed. The old version and your data are untouched.",
        "pause",
        "exit /b 1",
    ]
    return "\r\n".join(lines) + "\r\n"


def launch_update_installer(new_exe):
    """يشغّل سكربت الاستبدال ثم على البرنامج أن يُغلق نفسه."""
    current_exe = os.path.abspath(sys.executable)
    bat_path = os.path.join(os.path.dirname(new_exe), "install_update.bat")
    with open(bat_path, "w", encoding="utf-8", newline="") as f:
        f.write(update_bat_text())
    # مهم: نسخة EXE الجديدة يجب أن تفك نفسها من جديد، فلا نورّثها متغيرات PyInstaller الخاصة بالنسخة الحالية
    env = {k: v for k, v in os.environ.items() if not (k.startswith("_PYI") or k == "_MEIPASS2")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(["cmd.exe", "/c", "start", "", bat_path, current_exe, new_exe],
                     cwd=os.path.dirname(current_exe), env=env,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))



# ------------------------------------------------------------------ صور المنتجات
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "alabbad_item_images_new")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")


def store_image(src):
    """ينسخ الصورة إلى مجلد item_images بجانب البرنامج ويرجع اسم الملف المحفوظ."""
    if not src:
        return ""
    ext = os.path.splitext(src)[1].lower()
    if ext not in IMG_EXT:
        raise ValueError("نوع الصورة غير مدعوم. استخدم PNG أو JPG")
    if not os.path.isfile(src):
        raise ValueError("ملف الصورة غير موجود")
    os.makedirs(IMG_DIR, exist_ok=True)
    name = secrets.token_hex(8) + ext
    shutil.copy2(src, os.path.join(IMG_DIR, name))
    return name


def image_path(name):
    return os.path.join(IMG_DIR, name) if name else ""


def delete_image(name):
    try:
        if name:
            os.remove(os.path.join(IMG_DIR, name))
    except OSError:
        pass


def load_photo(path, box=(220, 220)):
    """يرجع صورة جاهزة للعرض (أو None). JPG يحتاج مكتبة Pillow، أما PNG/GIF فتعمل بدونها."""
    try:
        from PIL import Image, ImageTk
        im = Image.open(path)
        im.thumbnail(box)
        return ImageTk.PhotoImage(im)
    except ImportError:
        pass
    except Exception:
        return None
    try:
        ph = tk.PhotoImage(file=path)
        f = max(1, -(-ph.width() // box[0]), -(-ph.height() // box[1]))
        return ph.subsample(f, f) if f > 1 else ph
    except Exception:
        return None


def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,salt TEXT,hash TEXT,role TEXT,perms TEXT);
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,part TEXT,car TEXT,y1 TEXT,y2 TEXT,kind TEXT,qty INTEGER,buy REAL,expense REAL,profit REAL,retail REAL,location TEXT,notes TEXT,item_no TEXT,condition TEXT DEFAULT 'NEW');
        CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY,name TEXT UNIQUE,phone TEXT,notes TEXT);
        CREATE TABLE IF NOT EXISTS item_types(id INTEGER PRIMARY KEY,name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS car_makes(id INTEGER PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS car_models(id INTEGER PRIMARY KEY,make_id INTEGER NOT NULL,name TEXT NOT NULL COLLATE NOCASE,UNIQUE(make_id,name));
        CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY,batch TEXT,date TEXT,item_id INTEGER,supplier TEXT,qty INTEGER,buy REAL,expense REAL,landed REAL);
        CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY,invoice TEXT,date TEXT,customer TEXT,item_id INTEGER,qty INTEGER,price REAL,kind TEXT,paid REAL,approved_by TEXT,seller TEXT);
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT DEFAULT '', created_at TEXT);
        CREATE TABLE IF NOT EXISTS debt_payments(id INTEGER PRIMARY KEY, customer_id INTEGER, date TEXT, amount REAL NOT NULL, notes TEXT DEFAULT '', seller TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,date TEXT,category TEXT,amount REAL,notes TEXT);
        CREATE TABLE IF NOT EXISTS item_supplier_codes(id INTEGER PRIMARY KEY,item_id INTEGER,supplier TEXT,code TEXT,UNIQUE(item_id,supplier));
        CREATE TABLE IF NOT EXISTS reps(id INTEGER PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE,phone TEXT DEFAULT '',supplier TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS purchase_orders(id INTEGER PRIMARY KEY,po_no TEXT UNIQUE,created_at TEXT,created_by TEXT,rep_name TEXT,note TEXT DEFAULT '',status TEXT DEFAULT 'pending');
        CREATE TABLE IF NOT EXISTS po_lines(id INTEGER PRIMARY KEY,po_id INTEGER,item_id INTEGER,name TEXT,part TEXT,rep_code TEXT,qty INTEGER);
        CREATE TABLE IF NOT EXISTS job_types(id INTEGER PRIMARY KEY,name TEXT UNIQUE,rate REAL DEFAULT 0,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS bonus_claims(id INTEGER PRIMARY KEY,employee TEXT,work_date TEXT,created_at TEXT,status TEXT DEFAULT 'pending',total REAL DEFAULT 0,note TEXT DEFAULT '',decided_by TEXT,decided_at TEXT,decision_note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS bonus_lines(id INTEGER PRIMARY KEY,claim_id INTEGER,job_id INTEGER,job_name TEXT,cnt INTEGER,rate REAL DEFAULT 0,amount REAL DEFAULT 0);
        """)

        # ---- المستخدمون
        ucols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        if "perms" not in ucols:
            c.execute("ALTER TABLE users ADD COLUMN perms TEXT")

        # ---- المبيعات
        cols = {r[1] for r in c.execute("PRAGMA table_info(sales)").fetchall()}

        if "approved_by" not in cols:
            c.execute("ALTER TABLE sales ADD COLUMN approved_by TEXT")

        if "seller" not in cols:
            c.execute("ALTER TABLE sales ADD COLUMN seller TEXT")
            c.execute("UPDATE sales SET seller=COALESCE(NULLIF(approved_by, ''), 'غير مسجل') WHERE seller IS NULL OR seller=''")

        if "customer_phone" not in cols:
            c.execute("ALTER TABLE sales ADD COLUMN customer_phone TEXT DEFAULT ''")

        if "customer_id" not in cols:
            c.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER")

        if "payment_type" not in cols:
            c.execute("ALTER TABLE sales ADD COLUMN payment_type TEXT DEFAULT 'كاش'")

        for col_name, col_def in (("bundle_name", "TEXT DEFAULT ''"), ("bundle_qty", "INTEGER DEFAULT 0"), ("bundle_group", "TEXT DEFAULT ''")):
            if col_name not in cols:
                c.execute(f"ALTER TABLE sales ADD COLUMN {col_name} {col_def}")

        # ---- المشتريات
        pcols = {r[1] for r in c.execute("PRAGMA table_info(purchases)").fetchall()}
        if "status" not in pcols:
            # المشتريات القديمة كانت تُضاف للمخزون مباشرة، لذلك تُعتبر مستلمة
            c.execute("ALTER TABLE purchases ADD COLUMN status TEXT DEFAULT 'received'")
        if "received_at" not in pcols:
            c.execute("ALTER TABLE purchases ADD COLUMN received_at TEXT")

        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone) WHERE phone IS NOT NULL AND phone<>''")

        for sale in c.execute("SELECT id, customer, customer_phone, customer_id FROM sales WHERE COALESCE(customer,'')<>'' ORDER BY id").fetchall():
            if sale["customer_id"]:
                continue

            phone = normalize_phone(sale["customer_phone"] or "")
            cust = c.execute("SELECT id FROM customers WHERE phone=? AND phone<>''", (phone,)).fetchone() if phone else None

            if not cust:
                cust = c.execute("SELECT id FROM customers WHERE name=? COLLATE NOCASE ORDER BY id LIMIT 1", (sale["customer"].strip(),)).fetchone()

            if not cust:
                cur = c.execute(
                    "INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)",
                    (sale["customer"].strip(), phone, now_str())
                )
                customer_id = cur.lastrowid
            else:
                customer_id = cust["id"]
                if phone:
                    c.execute("UPDATE customers SET phone=? WHERE id=? AND (phone IS NULL OR phone='')", (phone, customer_id))

            c.execute(
                "UPDATE sales SET customer_id=?, customer_phone=COALESCE(NULLIF(customer_phone,''),?), payment_type=CASE WHEN (price*qty-COALESCE(paid,0))>0 THEN 'دين' ELSE 'كاش' END WHERE id=?",
                (customer_id, phone, sale["id"])
            )

        # ---- الأصناف
        item_cols = {r[1] for r in c.execute("PRAGMA table_info(items)").fetchall()}

        if "category" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN category TEXT DEFAULT 'غير محدد'")

        if "item_no" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN item_no TEXT")

        if "condition" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN condition TEXT DEFAULT 'NEW'")

        if "make" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN make TEXT DEFAULT ''")

        if "model" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN model TEXT DEFAULT ''")

        if "supplier" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN supplier TEXT DEFAULT ''")

        if "incomplete" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN incomplete INTEGER DEFAULT 0")

        if "image" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN image TEXT DEFAULT ''")

        if "rep_name" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN rep_name TEXT DEFAULT ''")

        if "rep_code" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN rep_code TEXT DEFAULT ''")

        # الأصل: أصلي / صيني
        if "origin" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN origin TEXT DEFAULT ''")

        # حد تنبيه النواقص (فارغ = بدون تنبيه، 0 = عند النفاد فقط)
        if "min_qty" not in item_cols:
            c.execute("ALTER TABLE items ADD COLUMN min_qty INTEGER")
        c.execute("CREATE TABLE IF NOT EXISTS stock_alerts(item_id INTEGER,username TEXT,notified_at TEXT,PRIMARY KEY(item_id,username))")

        # المنتجات المركّبة (صنفان أو أكثر يُباعون معًا)
        c.execute("CREATE TABLE IF NOT EXISTS bundles(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT NOT NULL,retail REAL DEFAULT 0,active INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS bundle_items(id INTEGER PRIMARY KEY,bundle_id INTEGER NOT NULL,item_id INTEGER NOT NULL,qty INTEGER NOT NULL DEFAULT 1)")

        # رموز بديلة للصنف (تبقى بعد دمج صنفين مكررين حتى لا يتكرر الصنف في الفواتير القادمة)
        c.execute("CREATE TABLE IF NOT EXISTS item_aliases(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL,supplier TEXT DEFAULT '',code TEXT NOT NULL,UNIQUE(item_id,code))")
        c.execute("CREATE TABLE IF NOT EXISTS dup_ignored(a_id INTEGER,b_id INTEGER,PRIMARY KEY(a_id,b_id))")

        # رمز المورد (يظهر في الباركود ليدل على مصدر القطعة)
        scols = {r[1] for r in c.execute("PRAGMA table_info(suppliers)").fetchall()}
        if "code" not in scols:
            c.execute("ALTER TABLE suppliers ADD COLUMN code TEXT DEFAULT ''")
        for r in c.execute("SELECT id FROM suppliers WHERE COALESCE(code,'')='' ORDER BY id").fetchall():
            c.execute("UPDATE suppliers SET code=? WHERE id=?", (next_supplier_code(c), r["id"]))

        # الربح للجملة صار نسبة مئوية: نحوّل الأرقام القديمة (مبالغ) إلى نسب مرة واحدة فقط
        if not c.execute("SELECT 1 FROM settings WHERE k='profit_is_percent'").fetchone():
            c.execute("""UPDATE items SET profit = CASE WHEN COALESCE(buy,0)+COALESCE(expense,0)>0
                         THEN ROUND(COALESCE(profit,0)*100.0/(COALESCE(buy,0)+COALESCE(expense,0)),2) ELSE 0 END""")
            c.execute("INSERT INTO settings VALUES('profit_is_percent','1')")

        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_item_no ON items(item_no) WHERE item_no IS NOT NULL AND item_no<>''")

        for row in c.execute("SELECT id,condition FROM items WHERE item_no IS NULL OR item_no='' ORDER BY id").fetchall():
            state = 'USED' if (row['condition'] or 'NEW').upper() == 'USED' else 'NEW'
            code = next_item_no(c, state)
            c.execute("UPDATE items SET item_no=?,condition=? WHERE id=?", (code, state, row['id']))

        for typ in ("ريموت", "غلاف مفتاح", "شريحة", "نصلة", "مفتاح كامل", "أزرار ريموت", "قطع إلكترونية", "أخرى"):
            c.execute("INSERT OR IGNORE INTO item_types(name) VALUES(?)", (typ,))

        # القائمة الابتدائية للسيارات (تتعبأ مرة واحدة فقط إذا كانت فاضية)
        if c.execute("SELECT COUNT(*) FROM car_makes").fetchone()[0] == 0:
            for make, models in SEED_CARS.items():
                cur = c.execute("INSERT INTO car_makes(name) VALUES(?)", (make,))
                for m in models:
                    c.execute("INSERT OR IGNORE INTO car_models(make_id,name) VALUES(?,?)", (cur.lastrowid, m))

        # تصحيح اسم موديل كان خاطئًا في نسخة سابقة
        bad = c.execute("SELECT id,make_id FROM car_models WHERE name='اوبتima'").fetchone()
        if bad and not c.execute("SELECT 1 FROM items WHERE model='اوبتima'").fetchone():
            c.execute("DELETE FROM car_models WHERE id=?", (bad["id"],))
            c.execute("INSERT OR IGNORE INTO car_models(make_id,name) VALUES(?,?)", (bad["make_id"], "اوبتيما"))

        # أنواع الأعمال الابتدائية للبونص (قيمتها 0 حتى يحددها المدير)
        if c.execute("SELECT COUNT(*) FROM job_types").fetchone()[0] == 0:
            for name in SEED_JOBS:
                c.execute("INSERT INTO job_types(name,rate,active) VALUES(?,0,1)", (name,))

        c.execute("INSERT OR IGNORE INTO settings VALUES('expense','0')")
        c.execute("INSERT OR IGNORE INTO settings VALUES('profit','25')")
        c.execute("INSERT OR IGNORE INTO settings VALUES('sheets_url','')")
        c.execute("INSERT OR IGNORE INTO settings VALUES('sheets_token','')")
        c.execute("INSERT OR IGNORE INTO settings VALUES('sheets_last_sync','')")
        c.execute("INSERT OR IGNORE INTO settings VALUES('sheets_last_error','')")

        if not c.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
            s, h = pw_hash("ChangeMe123!")
            c.execute("INSERT INTO users(username,salt,hash,role,perms) VALUES(?,?,?,'admin',NULL)", ("admin", s, h))


def setting(k):
    with connect() as c:
        r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
        return r[0] if r else ""


def setsetting(k, v):
    with connect() as c:
        c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def next_item_no(c, state):
    """يولّد رقم صنف جديد مثل NEW-0001 / USED-0001 بدون تكرار."""
    prefix = "USED" if str(state).upper() == "USED" else "NEW"
    rows = c.execute("SELECT item_no FROM items WHERE item_no LIKE ?", (prefix + "-%",)).fetchall()
    nums = []

    for row in rows:
        try:
            nums.append(int(str(row["item_no"]).split("-")[-1]))
        except Exception:
            pass

    return f"{prefix}-{(max(nums) if nums else 0) + 1:04d}"


def try_save(fn):
    try:
        fn()
    except Exception as e:
        messagebox.showerror("خطأ", str(e))


def default_password_in_use():
    try:
        with connect() as c:
            r = c.execute("SELECT salt,hash FROM users WHERE username='admin'").fetchone()
        return bool(r) and hmac.compare_digest(pw_hash("ChangeMe123!", r["salt"])[1], r["hash"])
    except Exception:
        return False


# ------------------------------------------------------------------ الجداول
def make_tree(parent, cols, heads, widths=None, height=None):
    fr = ttk.Frame(parent)
    fr.pack(fill="both", expand=True, pady=6)
    kw = {"height": height} if height else {}
    t = ttk.Treeview(fr, columns=cols, show="headings", **kw)
    widths = widths or {}
    for col in cols:
        t.heading(col, text=heads.get(col, col))
        t.column(col, width=widths.get(col, 110), anchor="center", stretch=True)
    sc = ttk.Scrollbar(fr, orient="vertical", command=t.yview)
    sx = ttk.Scrollbar(fr, orient="horizontal", command=t.xview)
    t.configure(yscrollcommand=sc.set, xscrollcommand=sx.set)
    sx.pack(side="bottom", fill="x")
    sc.pack(side="left", fill="y")
    t.pack(side="right", fill="both", expand=True)
    t.tag_configure("odd", background="#f1f5f9")
    t.tag_configure("even", background="white")
    t.tag_configure("out", foreground=RED)
    t.tag_configure("low", foreground=AMBER)
    t.tag_configure("incomplete", background="#fef3c7")
    t.tag_configure("best", background="#dcfce7", foreground="#166534")
    return t


def add_row(t, values, iid=None, extra=()):
    n = len(t.get_children())
    extra = tuple(extra)
    tags = extra if ("incomplete" in extra or "best" in extra) else (("odd" if n % 2 else "even"),) + extra
    t.insert("", "end", iid=iid, values=values, tags=tags)


def clear_tree(t):
    for i in t.get_children():
        t.delete(i)


# ------------------------------------------------------------------ إطار يتمدد مع الشاشة وله سكرول
_SCROLLERS = set()


def make_scrollable(parent, bg=BG, ttk_inner=True, pad=0, bar=True):
    """إطار يتمدد على قدر النافذة، وإذا كان المحتوى أطول من الشاشة يظهر سكرول (فلا يختفي أي زر)."""
    outer = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0, yscrollincrement=30)
    inner = ttk.Frame(canvas, padding=pad) if ttk_inner else tk.Frame(canvas, bg=bg)
    wid = canvas.create_window((0, 0), window=inner, anchor="nw")
    if bar:
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
    canvas.pack(side="right", fill="both", expand=True)
    last = [None]

    def fit(_e=None):
        try:
            w, h = canvas.winfo_width(), canvas.winfo_height()
            hh = max(h, inner.winfo_reqheight())
            if last[0] != (w, hh):
                last[0] = (w, hh)
                canvas.itemconfigure(wid, width=w, height=hh)
                canvas.configure(scrollregion=(0, 0, w, hh))
        except tk.TclError:
            return False
        return True

    def poll():
        if fit():
            try:
                canvas.after(250, poll)
            except tk.TclError:
                pass

    canvas.bind("<Configure>", fit)
    canvas.after(50, poll)
    _SCROLLERS.add(canvas)
    canvas.bind("<Destroy>", lambda e: _SCROLLERS.discard(canvas))
    return outer, inner, canvas


def _on_wheel(root, e):
    """عجلة الماوس تحرّك الصفحة (إلا فوق الجداول والقوائم فهي تتحرك بنفسها)."""
    try:
        w = root.winfo_containing(e.x_root, e.y_root)
    except Exception:
        w = None
    if w is None or isinstance(w, (ttk.Treeview, tk.Listbox, tk.Text)):
        return
    cur = w
    while cur is not None:
        if cur in _SCROLLERS:
            try:
                if cur.yview() != (0.0, 1.0):
                    num_ = getattr(e, "num", None)
                    if num_ == 4:
                        d = -1
                    elif num_ == 5:
                        d = 1
                    else:
                        d = -1 if e.delta > 0 else 1
                    cur.yview_scroll(d * 2, "units")
            except tk.TclError:
                pass
            return
        cur = getattr(cur, "master", None)


# ------------------------------------------------------------------ الباركود
_CODE39 = {
    "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn", "4": "nnnwwnnnw", "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw", "8": "wnnwnnwnn", "9": "nnwwnnwnn",
    "A": "wnnnnwnnw", "B": "nnwnnwnnw", "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn", "F": "nnwnwwnnn", "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
    "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww", "O": "wnnnwnnwn", "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn", "S": "nnwnnnwwn", "T": "nnnnwnwwn",
    "U": "wwnnnnnnw", "V": "nwwnnnnnw", "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn", "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "$": "nwnwnwnnn", "/": "nwnwnnnwn", "+": "nwnnnwnwn", "%": "nnnwnwnwn", "*": "nwnnwnwnn"}


def code39_svg(value):
    value = str(value).upper()
    value = ''.join(ch for ch in value if ch in _CODE39 and ch != '*')
    value = '*' + value + '*'
    x = 2
    parts = []
    narrow = 1.0
    wide = 2.0
    height = 42

    for char in value:
        pat = _CODE39[char]
        for i, ch in enumerate(pat):
            width = wide if ch == 'w' else narrow
            if i % 2 == 0:
                parts.append(f'<rect x="{x:.2f}" y="2" width="{width:.2f}" height="{height}" fill="#000"/>')
            x += width
        x += narrow

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{x + 2:.2f}" height="46" viewBox="0 0 {x + 2:.2f} 46" preserveAspectRatio="none">' + ''.join(parts) + '</svg>'


def barcode_label_name(r):
    """اسم الملصق: نوع القطعة + الشركة + الموديل + نوع المفتاح + الأصل."""
    make, model = (r["make"] or "").strip(), (r["model"] or "").strip()
    car = f"{make} {model}".strip() or (r["car"] or "").strip()
    cat = (r["category"] or "").strip()
    parts = ["" if cat == "غير محدد" else cat, car, (r["kind"] or "").strip(), (r["origin"] or "").strip()]
    return " ".join(x for x in parts if x)


def make_labels_html(entries):
    """ملصقات 40×30 مم. كل سجل: رقم الصنف، الاسم، العدد، رمز المورد، رقم القطعة، السعر."""
    labels = []
    for item_no, name, count, sup_code, part_no, price in entries:
        barcode_value = f"{item_no}-{sup_code}" if sup_code else str(item_no)
        safe_name = html.escape(str(name or ""))
        safe_part = html.escape(str(part_no or ""))
        safe_item_no = html.escape(str(item_no or ""))
        safe_price = html.escape(f"{num(price):.2f} ر.س" if price not in (None, "") else "")
        barcode = code39_svg(barcode_value)
        for _ in range(int(count)):
            labels.append(
                '<section class="label">'
                f'<div class="name" dir="rtl">{safe_name}</div>'
                f'<div class="details" dir="rtl"><span>القطعة: {safe_part}</span>'
                f'<span>الصنف: {safe_item_no}</span><span>السعر: {safe_price}</span></div>'
                f'<div class="barcode">{barcode}</div>'
                f'<div class="code">{html.escape(barcode_value)}</div>'
                '</section>'
            )

    return '''<!doctype html><html lang="ar"><head><meta charset="utf-8"><title>طباعة باركود</title><style>
@page{size:40mm 30mm;margin:0}*{box-sizing:border-box}html,body{margin:0;padding:0;width:40mm;font-family:Arial,sans-serif}.label{width:40mm;height:30mm;padding:0.7mm 1mm;overflow:hidden;page-break-after:always;break-after:page;display:flex;flex-direction:column;align-items:center;justify-content:space-evenly}.name{font-size:6.5pt;font-weight:bold;max-width:38mm;line-height:1.05;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:clip}.details{width:100%;display:flex;flex-direction:column;align-items:center;gap:0.2mm;font-size:5.5pt;font-weight:bold;line-height:1.05;white-space:nowrap}.barcode{width:38mm;height:12mm;display:flex;align-items:center;justify-content:center;flex-shrink:0}.barcode svg{display:block;width:38mm;height:12mm}.code{font-size:6pt;font-weight:bold;letter-spacing:.2px;line-height:1} @media screen{body{background:#ddd}.label{background:#fff;margin:5mm auto;box-shadow:0 0 2mm #888}}</style></head><body>''' + ''.join(labels) + '''<script>window.onload=()=>setTimeout(()=>window.print(),500)</script></body></html>'''


def make_label_html(code, name, count, sup_code="", part_no="", price=""):
    return make_labels_html([(code, name, count, sup_code, part_no, price)])


def parse_barcode(text):
    """يفكّ نص الباركود NEW-0001-S03 إلى (رقم الصنف، رمز المورد)."""
    m = re.fullmatch(r"\s*((?:NEW|USED)-\d+)(?:-([A-Za-z0-9]{1,8}))?\s*", str(text or ""), re.I)
    return (m.group(1).upper(), (m.group(2) or "").upper()) if m else None


def next_supplier_code(c):
    nums = []
    for r in c.execute("SELECT code FROM suppliers WHERE COALESCE(code,'')<>''").fetchall():
        m = re.fullmatch(r"S(\d+)", str(r["code"]).upper())
        if m:
            nums.append(int(m.group(1)))
    return f"S{(max(nums) if nums else 0) + 1:02d}"


def wholesale_price(buy, expense, profit_pct):
    """سعر الجملة = (الشراء + المصاريف) × (1 + نسبة الربح)."""
    return round((num(buy) + num(expense)) * (1 + num(profit_pct) / 100.0), 2)


def item_display_name(r):
    """اسم المنتج للعرض: النوع + السيارة + نوع المفتاح."""
    years = f"{r['y1'] or ''}-{r['y2'] or ''}" if (r["y1"] or r["y2"]) else ""
    name = " ".join(x for x in (r["category"], r["car"], r["kind"], years) if x)
    return name or (r["part"] or "")


# ------------------------------------------------------------------ تنبيهات النواقص
def low_stock_rows(c):
    """الأصناف التي وصلت كميتها إلى حد التنبيه المحدد لها أو أقل (أو نفدت)."""
    return c.execute("""
        SELECT * FROM items
        WHERE min_qty IS NOT NULL AND COALESCE(qty,0) <= min_qty
        AND NOT EXISTS (SELECT 1 FROM purchases p WHERE p.item_id=items.id AND p.status='pending')
        ORDER BY COALESCE(NULLIF(supplier,''),'~'), item_no
    """).fetchall()


def stock_alert_state(c, username):
    """يرجع (كل النواقص الحالية، الجديدة التي لم يُبلَّغ بها هذا المستخدم)، وينظّف الأصناف التي تعافت."""
    low = low_stock_rows(c)
    ids = {r["id"] for r in low}
    for (gone,) in c.execute("SELECT DISTINCT item_id FROM stock_alerts").fetchall():
        if gone not in ids:
            c.execute("DELETE FROM stock_alerts WHERE item_id=?", (gone,))
    notified = {r[0] for r in c.execute("SELECT item_id FROM stock_alerts WHERE username=?", (username,)).fetchall()}
    return low, [r for r in low if r["id"] not in notified]


def mark_alerts_notified(c, item_ids, username):
    for i in item_ids:
        c.execute("INSERT OR IGNORE INTO stock_alerts(item_id,username,notified_at) VALUES(?,?,?)", (i, username, now_str()))


# ------------------------------------------------------------------ المنتجات المركّبة
def next_bundle_code(c):
    nums = []
    for r in c.execute("SELECT code FROM bundles").fetchall():
        m = re.fullmatch(r"BND-(\d+)", str(r["code"]).upper())
        if m:
            nums.append(int(m.group(1)))
    return f"BND-{(max(nums) if nums else 0) + 1:04d}"


def bundle_components(c, bundle_id):
    rows = c.execute("""
        SELECT bi.item_id, bi.qty AS comp_qty, i.item_no, i.part, i.car, i.category, i.kind, i.y1, i.y2,
               COALESCE(i.qty,0) AS stock, i.retail, i.buy, i.expense, i.profit
        FROM bundle_items bi JOIN items i ON i.id=bi.item_id
        WHERE bi.bundle_id=? ORDER BY bi.id
    """, (bundle_id,)).fetchall()
    return [dict(r) for r in rows]


def bundle_available(comps):
    """كم منتجًا مركّبًا يمكن بيعه الآن (حسب أقل صنف مخزونًا)."""
    if not comps:
        return 0
    return min(int((c["stock"] or 0) // max(int(c["comp_qty"] or 1), 1)) for c in comps)


def bundle_wholesale(comps):
    return round(sum(wholesale_price(c["buy"], c["expense"], c["profit"]) * c["comp_qty"] for c in comps), 2)


def expand_bundle_sale(comps, unit_price):
    """يوزّع سعر المنتج المركّب على أصنافه بنسبة سعر المفرد (المجموع يطابق سعر البيع تمامًا)."""
    weights = [max(num(c["retail"]), 0) * c["comp_qty"] for c in comps]
    if sum(weights) <= 0:
        weights = [float(c["comp_qty"]) for c in comps]
    total_w = sum(weights)
    return [(c, (unit_price * w / total_w) / c["comp_qty"]) for c, w in zip(comps, weights)]


def expand_invoice_lines(c, invoice_items, invoice_no):
    """يفك المنتجات المركّبة إلى أصنافها، ويتحقق من كفاية المخزون الكلي، ويرجع صفوف البيع."""
    rows_out, need = [], {}
    for idx, x in enumerate(invoice_items, start=1):
        r = x["item"]
        if isinstance(r, dict) and r.get("bundle_id"):
            comps = bundle_components(c, r["bundle_id"])
            if not comps:
                raise ValueError(f"المنتج المركّب {r['part']} لا يحتوي أصنافًا")
            grp = f"{invoice_no}-{idx}"
            for comp, unit in expand_bundle_sale(comps, x["price"]):
                q_ = comp["comp_qty"] * x["qty"]
                rows_out.append({"item_id": comp["item_id"], "qty": q_, "price": unit, "kind": x["kind"],
                                 "bundle_name": r["part"], "bundle_qty": x["qty"], "bundle_group": grp})
                need[comp["item_id"]] = need.get(comp["item_id"], 0) + q_
        else:
            rows_out.append({"item_id": r["id"], "qty": x["qty"], "price": x["price"], "kind": x["kind"],
                             "bundle_name": "", "bundle_qty": 0, "bundle_group": ""})
            need[r["id"]] = need.get(r["id"], 0) + x["qty"]
    for item_id, q_ in need.items():
        fresh = c.execute("SELECT qty,item_no FROM items WHERE id=?", (item_id,)).fetchone()
        if not fresh or (fresh["qty"] or 0) < q_:
            raise ValueError(f"الكمية غير كافية للصنف {fresh['item_no'] if fresh else item_id}")
    return rows_out


# ------------------------------------------------------------------ اقتراحات العملاء
def customer_suggestions(c, text, limit=8):
    """عملاء من قاعدة البيانات يطابقون ما كُتب (اسم أو جزء من رقم الجوال)."""
    t = clean_name(text)
    if len(t) < 2:
        return []
    digits = "".join(ch for ch in t if ch.isdigit()).lstrip("0")
    like_phone = "%" + digits + "%" if len(digits) >= 3 else None
    return c.execute("""
        SELECT cu.id, cu.name, cu.phone,
        COALESCE((SELECT SUM(s.price*s.qty-COALESCE(s.paid,0)) FROM sales s WHERE s.customer_id=cu.id),0)
        -COALESCE((SELECT SUM(dp.amount) FROM debt_payments dp WHERE dp.customer_id=cu.id),0) AS debt
        FROM customers cu
        WHERE cu.name LIKE ? OR (? IS NOT NULL AND cu.phone LIKE ?)
        ORDER BY cu.name LIMIT ?
    """, ("%" + t + "%", like_phone, like_phone, limit)).fetchall()


# ------------------------------------------------------------------ كشف الأصناف المكررة (بين الموردين)
def norm_code(s):
    """يوحّد الرمز: حروف كبيرة وبدون رموز/فراغات (TY-123 = ty 123)."""
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def image_dhash(path):
    """بصمة بصرية للصورة (dHash 64 بت): الصور المتشابهة تعطي بصمات متقاربة."""
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((9, 8))
        px = list(im.getdata())
        bits = 0
        for r_ in range(8):
            for c_ in range(8):
                bits = (bits << 1) | (1 if px[r_ * 9 + c_] > px[r_ * 9 + c_ + 1] else 0)
        return bits
    except Exception:
        return None


def hamming(a, b):
    return bin(a ^ b).count("1")


_HASH_CACHE = {}


def item_image_hash(name):
    if not name:
        return None
    path = image_path(name)
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key not in _HASH_CACHE:
        _HASH_CACHE[key] = image_dhash(path)
    return _HASH_CACHE[key]


def _kind_key(s):
    m = re.search(r"\d(?:\+\d)?", str(s or ""))
    return m.group(0) if m else re.sub(r"\s+", "", str(s or "")).lower()


def _year_range(y1, y2):
    def one(v):
        m = re.search(r"(?:19|20)\d{2}", str(v or ""))
        return int(m.group(0)) if m else None
    a, b = one(y1), one(y2)
    if a is None and b is None:
        return None
    a = a if a is not None else b
    b = b if b is not None else a
    return (min(a, b), max(a, b))


def similarity(a, b):
    """يقارن صنفين (قاموسين) ويرجع (نسبة التشابه 0-100، أسباب). الأصلي والصيني أو الجديد والمستعمل ليسا مكررين."""
    ca = {norm_code(x) for x in [a.get("part"), a.get("rep_code"), *(a.get("codes") or [])]} - {""}
    cb = {norm_code(x) for x in [b.get("part"), b.get("rep_code"), *(b.get("codes") or [])]} - {""}
    if ca & cb:
        return 100, ["نفس رمز المنتج"]
    s, why = 0, []
    if a.get("make") and a.get("make") == b.get("make"):
        s += 10
        if a.get("model") and a.get("model") == b.get("model"):
            s += 20
            why.append("نفس السيارة والموديل")
    if a.get("category") and a.get("category") == b.get("category"):
        s += 20
        why.append("نفس نوع القطعة")
    ka, kb = _kind_key(a.get("kind")), _kind_key(b.get("kind"))
    if ka and kb:
        if ka == kb:
            s += 20
            why.append("نفس نوع المفتاح")
        else:
            s -= 15
    ya, yb = _year_range(a.get("y1"), a.get("y2")), _year_range(b.get("y1"), b.get("y2"))
    if ya and yb:
        if ya[0] <= yb[1] and yb[0] <= ya[1]:
            s += 15
            why.append("سنوات متقاطعة")
        else:
            s -= 25
    ha, hb = a.get("img_hash"), b.get("img_hash")
    if ha is not None and hb is not None:
        d = hamming(ha, hb)
        if d <= 6:
            s += 35
            why.append("صورة متطابقة تقريبًا")
        elif d <= 12:
            s += 20
            why.append("صورة مشابهة")
    oa, ob = a.get("origin") or "", b.get("origin") or ""
    if oa and ob and oa != ob:
        s *= 0.4
        why.append(f"الأصل مختلف ({oa} / {ob})")
    if (a.get("condition") or "NEW").upper() != (b.get("condition") or "NEW").upper():
        s *= 0.4
        why.append("الحالة مختلفة")
    return max(0, min(99, int(round(s)))), why


def _item_profile(r, codes):
    return {"part": r["part"], "rep_code": r["rep_code"], "category": r["category"], "make": r["make"], "model": r["model"],
            "y1": r["y1"], "y2": r["y2"], "kind": r["kind"], "origin": r["origin"], "condition": r["condition"],
            "codes": codes, "img_hash": item_image_hash(r["image"])}


def _extra_codes(c, ids):
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        marks = ",".join("?" * len(part))
        for tbl in ("item_supplier_codes", "item_aliases"):
            for r in c.execute(f"SELECT item_id, code FROM {tbl} WHERE item_id IN ({marks})", part).fetchall():
                out.setdefault(r["item_id"], set()).add(r["code"])
    return out


def _named_codes(c, ids):
    """رموز الصنف عند الموردين: {رقم الصنف: ["المورد: الرمز", ...]}"""
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        marks = ",".join("?" * len(part))
        for tbl in ("item_supplier_codes", "item_aliases"):
            for r in c.execute(f"SELECT item_id, supplier, code FROM {tbl} WHERE item_id IN ({marks})", part).fetchall():
                txt = f"{r['supplier']}: {r['code']}" if r["supplier"] else str(r["code"])
                lst = out.setdefault(r["item_id"], [])
                if txt not in lst:
                    lst.append(txt)
    return out


def _item_brief(r, codes=""):
    return {"id": r["id"], "item_no": r["item_no"], "part": r["part"] or "", "rep_code": r["rep_code"] or "", "codes": codes,
            "name": item_display_name(r), "qty": r["qty"] or 0, "origin": r["origin"] or ""}


def codes_label(b):
    """نص موحّد لأرقام الصنف: رقم القطعة + رمز المورد + رموز الموردين الأخرى."""
    return " / ".join(x for x in (f"قطعة {b['part']}" if b["part"] else "", f"مورد {b['rep_code']}" if b["rep_code"] else "", b["codes"]) if x)


COMPARE_FIELDS = [("part", "رقم القطعة"), ("rep_code", "رمز المنتج عند المورد"), ("codes", "رموز الصنف عند الموردين"), ("car", "السيارة"),
                  ("years", "السنوات"), ("category", "نوع القطعة"), ("kind", "نوع المفتاح"), ("origin", "الأصل"), ("cond", "الحالة")]


def find_similar_items(c, cand, exclude_id=None, limit=5, threshold=65):
    """أصناف موجودة قد تكون هي نفس الصنف الجديد (cand: قاموس بنفس مفاتيح similarity)."""
    codes = {x for x in (norm_code(cand.get("part")), norm_code(cand.get("rep_code"))) if x}
    pool = set()
    if cand.get("make") and cand.get("model"):
        pool.update(r[0] for r in c.execute("SELECT id FROM items WHERE COALESCE(make,'')=? AND COALESCE(model,'')=? LIMIT 600",
                                            (cand["make"], cand["model"])).fetchall())
    elif cand.get("category"):
        pool.update(r[0] for r in c.execute("SELECT id FROM items WHERE COALESCE(category,'')=? LIMIT 600", (cand["category"],)).fetchall())
    if codes:
        for r in c.execute("SELECT id,part,rep_code FROM items").fetchall():
            if {norm_code(r["part"]), norm_code(r["rep_code"])} & codes:
                pool.add(r["id"])
        for r in c.execute("SELECT item_id, code FROM item_supplier_codes UNION ALL SELECT item_id, code FROM item_aliases").fetchall():
            if norm_code(r["code"]) in codes:
                pool.add(r["item_id"])
    pool.discard(exclude_id)
    if not pool:
        return []
    ids = list(pool)
    extra = _extra_codes(c, ids)
    named = _named_codes(c, ids)
    out = []
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in c.execute(f"SELECT * FROM items WHERE id IN ({','.join('?' * len(part))})", part).fetchall():
            sc, why = similarity(cand, _item_profile(r, extra.get(r["id"], set())))
            if sc >= threshold:
                out.append(dict(_item_brief(r, " / ".join(named.get(r["id"], []))), score=sc, reasons=why))
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def find_duplicate_pairs(c, threshold=65, limit=300):
    """يفحص كل المخزون ويرجع أزواج الأصناف المشتبه بتكرارها (بدون الأزواج التي حدّدت أنها مختلفة)."""
    rows = c.execute("SELECT * FROM items").fetchall()
    by_id = {r["id"]: r for r in rows}
    extra = _extra_codes(c, by_id.keys())
    named = _named_codes(c, by_id.keys())
    ignored = {(r[0], r[1]) for r in c.execute("SELECT a_id,b_id FROM dup_ignored").fetchall()}
    profiles = {i: _item_profile(r, extra.get(i, set())) for i, r in by_id.items()}
    pairs = {}

    def add(i, j):
        a, b = (i, j) if i < j else (j, i)
        if a == b or (a, b) in pairs or (a, b) in ignored:
            return
        sc, why = similarity(profiles[a], profiles[b])
        if sc >= threshold:
            pairs[(a, b)] = (sc, why)

    blocks = {}
    for i, r in by_id.items():
        key = (r["make"], r["model"]) if (r["make"] and r["model"]) else ("", r["category"] or "")
        blocks.setdefault(key, []).append(i)
    for ids in blocks.values():
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                add(ids[x], ids[y])
    by_code = {}
    for i, p in profiles.items():
        for cd in {norm_code(x) for x in [p["part"], p["rep_code"], *p["codes"]]} - {""}:
            by_code.setdefault(cd, set()).add(i)
    for ids in by_code.values():
        ids = sorted(ids)
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                add(ids[x], ids[y])
    out = [{"a": _item_brief(by_id[a], " / ".join(named.get(a, []))), "b": _item_brief(by_id[b], " / ".join(named.get(b, []))), "score": sc, "reasons": why}
           for (a, b), (sc, why) in pairs.items()]
    out.sort(key=lambda p: -p["score"])
    return out[:limit]


def merge_items(c, keep_id, drop_id):
    """يدمج صنفًا مكررًا (drop) في الصنف المُبقى (keep): الكمية تُجمع والتكلفة بالمتوسط المرجّح،
    وكل المشتريات والمبيعات والطلبات تنتقل، ورموز الصنف المحذوف تبقى رموزًا بديلة."""
    if keep_id == drop_id:
        raise ValueError("اختر صنفين مختلفين")
    keep = c.execute("SELECT * FROM items WHERE id=?", (keep_id,)).fetchone()
    drop = c.execute("SELECT * FROM items WHERE id=?", (drop_id,)).fetchone()
    if not keep or not drop:
        raise ValueError("أحد الصنفين غير موجود")
    q1, q2 = max(int(keep["qty"] or 0), 0), max(int(drop["qty"] or 0), 0)
    b1, e1, b2, e2 = num(keep["buy"]), num(keep["expense"]), num(drop["buy"]), num(drop["expense"])
    if (b1 + e1) > 0 and (b2 + e2) > 0 and q1 + q2 > 0:
        nb, ne = (q1 * b1 + q2 * b2) / (q1 + q2), (q1 * e1 + q2 * e2) / (q1 + q2)
        profit = num(keep["profit"])
    elif (b1 + e1) > 0:
        nb, ne, profit = b1, e1, num(keep["profit"])
    else:
        nb, ne, profit = b2, e2, num(drop["profit"])
    retail = num(keep["retail"]) if num(keep["retail"]) > 0 else num(drop["retail"])
    image = keep["image"] or drop["image"]
    min_qty = keep["min_qty"] if keep["min_qty"] is not None else drop["min_qty"]
    c.execute("""UPDATE items SET qty=?, buy=?, expense=?, profit=?, retail=?, image=?, min_qty=?,
                 supplier=COALESCE(NULLIF(supplier,''),?), rep_code=COALESCE(NULLIF(rep_code,''),?), incomplete=? WHERE id=?""",
              (q1 + q2, round(nb, 4), round(ne, 4), profit, retail, image or "", min_qty,
               drop["supplier"] or "", drop["rep_code"] or "", 0 if (nb + ne) > 0 else 1, keep_id))
    for tbl in ("purchases", "sales", "po_lines", "bundle_items"):
        c.execute(f"UPDATE {tbl} SET item_id=? WHERE item_id=?", (keep_id, drop_id))
    aliases = [("", cd) for cd in (drop["part"], drop["rep_code"], drop["item_no"]) if cd]
    for tbl in ("item_supplier_codes", "item_aliases"):
        aliases += [(r["supplier"] or "", r["code"]) for r in c.execute(f"SELECT supplier, code FROM {tbl} WHERE item_id=?", (drop_id,)).fetchall()]
    for sup, cd in aliases:
        c.execute("INSERT OR IGNORE INTO item_aliases(item_id,supplier,code) VALUES(?,?,?)", (keep_id, sup, cd))
    for r in c.execute("SELECT supplier, code FROM item_supplier_codes WHERE item_id=?", (drop_id,)).fetchall():
        c.execute("INSERT OR IGNORE INTO item_supplier_codes(item_id,supplier,code) VALUES(?,?,?)", (keep_id, r["supplier"], r["code"]))
    for tbl in ("item_supplier_codes", "item_aliases"):
        c.execute(f"DELETE FROM {tbl} WHERE item_id=?", (drop_id,))
    c.execute("DELETE FROM stock_alerts WHERE item_id=?", (drop_id,))
    c.execute("DELETE FROM dup_ignored WHERE a_id=? OR b_id=?", (drop_id, drop_id))
    c.execute("DELETE FROM items WHERE id=?", (drop_id,))
    return {"qty": q1 + q2, "delete_image": drop["image"] if (drop["image"] and drop["image"] != image) else ""}


# ------------------------------------------------------------------ صور الأصناف داخل فاتورة PDF
def _native_pdf_image(im):
    """الصورة الأصلية من داخل الـ PDF بدقتها الكاملة (JPEG أو RGB/رمادي خام). يرجع None إذا تعذّر (فنرسم الصفحة بدلًا)."""
    try:
        import io
        from PIL import Image
        st = im["stream"]
        f = st.get_any(("F", "Filter"))
        names = [str(x) for x in (f if isinstance(f, list) else [f])] if f is not None else []
        if st.get_any(("SMask", "Mask")) is not None:
            return None
        data = st.get_data()
        if any("DCT" in n or "JPX" in n for n in names):
            pic = Image.open(io.BytesIO(data))
            pic.load()
            return pic.convert("RGB")
        w, h = im["srcsize"]
        cs = str(st.get_any(("CS", "ColorSpace")))
        if int(st.get_any(("BPC", "BitsPerComponent")) or 8) == 8:
            if "DeviceRGB" in cs and len(data) == w * h * 3:
                return Image.frombytes("RGB", (w, h), data)
            if "DeviceGray" in cs and len(data) == w * h:
                return Image.frombytes("L", (w, h), data).convert("RGB")
    except Exception:
        return None
    return None


def extract_pdf_row_images(path, lines, out_dir=None):
    """يقصّ صورة كل صنف من الفاتورة (الصورة الواقعة بجانب سطر الصنف) ويرجع {رقم السطر في القائمة: مسار PNG}."""
    out_dir = out_dir or tempfile.mkdtemp(prefix="alabbad_pdfimg_")
    result, renders = {}, {}
    try:
        import pdfplumber
    except Exception:
        return result
    with pdfplumber.open(path) as pdf:
        for idx, ln in enumerate(lines):
            pi = ln.get("page")
            if pi is None or pi >= len(pdf.pages) or ln.get("lo") is None:
                continue
            page = pdf.pages[pi]
            best = None
            for im in page.images:
                x0, x1, top, bottom = im["x0"], im["x1"], im["top"], im["bottom"]
                w, h = x1 - x0, bottom - top
                cy = (top + bottom) / 2.0
                if w < 15 or h < 15 or top < ln["hdr"] - 2:
                    continue  # شعار أو زخرفة أعلى الجدول
                if ln["lo"] <= cy < ln["hi"] and (best is None or w * h > best[0]):
                    best = (w * h, (max(x0, 0), max(top, 0), min(x1, page.width), min(bottom, page.height)), im)
            if not best:
                continue
            native = _native_pdf_image(best[2])
            if native is not None:
                native.thumbnail((700, 700))
                p = os.path.join(out_dir, f"line_{idx}.jpg")
                native.save(p, quality=90)
                result[idx] = p
                continue
            try:
                s = 200 / 72.0
                if pi not in renders:  # نرسم كل صفحة مرة واحدة ثم نقصّ منها (أسرع بكثير)
                    renders[pi] = page.to_image(resolution=200).original.convert("RGB")
                bx0, btop, bx1, bbot = best[1]
                ox, oy = page.bbox[0], page.bbox[1]
                pic = renders[pi].crop((int((bx0 - ox) * s), int((btop - oy) * s), int((bx1 - ox) * s), int((bbot - oy) * s)))
                pic.thumbnail((700, 700))
                p = os.path.join(out_dir, f"line_{idx}.png")
                pic.save(p)
                result[idx] = p
            except Exception:
                continue
    return result


# ------------------------------------------------------------------ قراءة فواتير الموردين من PDF
_NUM_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_DATE_RE = re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})")


def read_pdf_words(path):
    """يقرأ كلمات الـ PDF مع إحداثياتها (صفحة بصفحة). يحتاج مكتبة pdfplumber (أو PyMuPDF)."""
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None
    if pdfplumber:
        pages = []
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                ws = p.extract_words(x_tolerance=2, y_tolerance=2)
                pages.append([{"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"], "bottom": w["bottom"]} for w in ws])
        return pages
    try:
        import fitz
    except ImportError:
        # استخدم نفس مفسّر Python الذي يشغّل البرنامج؛ قد تكون المكتبة
        # مثبتة في Python آخر على الجهاز.
        python_exe = sys.executable or "python"
        install_cmd = f'"{python_exe}" -m pip install pdfplumber'
        raise RuntimeError(
            "تعذّر على Python الذي يشغّل البرنامج العثور على مكتبة قراءة PDF.\n\n"
            f"مفسّر Python المستخدم:\n{python_exe}\n\n"
            "إذا كانت pdfplumber مثبتة بالفعل، شغّل البرنامج من CMD بنفس المفسّر أعلاه، "
            "أو نفّذ الأمر التالي لتثبيتها لهذا المفسّر فقط:\n\n"
            f"{install_cmd}\n\n"
            "ثم أغلق البرنامج وافتحه من جديد."
        )
    pages = []
    doc = fitz.open(path)
    for p in doc:
        pages.append([{"text": w[4], "x0": w[0], "x1": w[2], "top": w[1], "bottom": w[3]} for w in p.get_text("words")])
    return pages


def _cy(w):
    return (w["top"] + w["bottom"]) / 2.0


def _cx(w):
    return (w["x0"] + w["x1"]) / 2.0


def _is_num(t):
    return bool(_NUM_RE.match(t))


def _to_num(t):
    return float(t.replace(",", ""))


def _group_lines(words, tol=3.0):
    lines = []
    for w in sorted(words, key=lambda w: (_cy(w), w["x0"])):
        if lines and abs(lines[-1]["cy"] - _cy(w)) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"cy": _cy(w), "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        ln["text"] = " ".join(w["text"] for w in ln["words"])
    return lines


def _to_iso_date(text):
    m = _DATE_RE.search(text or "")
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if mo > 12 and d <= 12:
        d, mo = mo, d
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _find_table_columns(words):
    """يحدد أعمدة الجدول من صف العناوين (الكمية / السعر / الإجمالي ...)."""
    qty = next((w for w in words if w["text"].lower() in ("quantity", "qty", "qty.")), None)
    if not qty:
        return None
    ht = qty["top"]
    near = sorted([w for w in words if abs(w["top"] - ht) < 14], key=lambda w: w["x0"])
    price = next((w for w in near if w["text"].lower() == "price" and w["x0"] > qty["x1"]), None)
    if not price:
        return None
    total = next((w for w in near if w["text"].lower() in ("total", "amount") and w["x0"] > price["x0"]), None)
    price_c = _cx(price)
    unit = next((w for w in near if w["text"].lower() == "unit" and abs(w["x1"] - price["x0"]) < 12), None)
    if unit:
        price_c = (unit["x0"] + price["x1"]) / 2.0
    hash_w = next((w for w in near if w["text"].lower() in ("#", "no#", "no", "no.") and w["x0"] < qty["x0"]), None)
    if not hash_w:
        return None
    code_w = next((w for w in near if w["text"].lower() == "code"), None)
    image_w = next((w for w in near if w["text"].lower() == "image"), None)
    items = [w for w in near if w["text"].lower() == "item"]
    col = {"header_top": ht, "qty_c": _cx(qty), "qty_x0": qty["x0"], "price_c": price_c,
           "total_c": _cx(total) if total else price_c + 45, "hash_c": _cx(hash_w), "hash_x1": hash_w["x1"]}
    if code_w:
        item_w = next((w for w in items if w["x0"] > code_w["x1"]), None)
        first_item = next((w for w in items if w["x1"] <= code_w["x0"] + 2), None)
        if item_w and first_item:
            code_c = (first_item["x0"] + code_w["x1"]) / 2.0
            col["code_hi"] = (code_c + _cx(item_w)) / 2.0
            col["has_code_col"] = True
    if not col.get("has_code_col"):
        col["has_code_col"] = False
        col["desc_lo"] = (image_w["x1"] if image_w else hash_w["x1"]) + 10
    return col


def parse_supplier_invoice(pages):
    """يحوّل كلمات الـ PDF إلى فاتورة: رقم + تاريخ + عملة + أسطر (كود، وصف، كمية، سعر) + شحن/خصم/ضريبة."""
    res = {"invoice_no": "", "date": "", "currency": "", "supplier_guess": "", "lines": [],
           "shipping": 0.0, "discount": 0.0, "tax": 0.0, "net_pdf": None, "warnings": []}
    all_text = " ".join(w["text"] for pg in pages for w in pg)
    if not all_text.strip():
        raise RuntimeError("لا يوجد نص داخل الملف (ربما هو صورة ممسوحة). الملف لازم يكون PDF فيه نص قابل للتحديد.")
    if re.search(r"\bAED\b|dirham|د\.إ|إ\.د|درهم", all_text, re.I):
        res["currency"] = "AED"
    elif re.search(r"\bSAR\b|riyal|ريال", all_text, re.I):
        res["currency"] = "SAR"
    elif re.search(r"\bUSD\b|US\$|dollar", all_text, re.I):
        res["currency"] = "USD"

    last_page, last_row_cy = None, None
    for pi, words in enumerate(pages):
        col = _find_table_columns(words)
        if not col:
            continue
        hdr = col["header_top"]
        # ---- رأس الفاتورة (الصفحة الأولى التي فيها جدول)
        if pi == 0 or not res["invoice_no"]:
            for ln in _group_lines([w for w in words if w["top"] < hdr - 5]):
                ws = ln["words"]
                for i, w in enumerate(ws):
                    t = w["text"].lower()
                    if not res["invoice_no"] and re.match(r"^invo", t):
                        for v in ws[i + 1:]:
                            if v["text"].lower().strip(":") in ("no", "no.", "no#", "#", "number", "#:", ""):
                                continue
                            if re.search(r"\d", v["text"]):
                                res["invoice_no"] = v["text"].strip(":")
                                break
                    if not res["date"] and t in ("date", "date:"):
                        res["date"] = _to_iso_date(" ".join(v["text"] for v in ws[i + 1:]))
            if not res["supplier_guess"]:
                first = _group_lines([w for w in words if w["top"] < hdr - 5])[:1]
                if first:
                    txt = first[0]["text"]
                    if len(txt) >= 6 and not re.search(r"\d", txt) and txt.upper() == txt and len(txt.split()) >= 2:
                        res["supplier_guess"] = txt

        # ---- أسطر الجدول
        zone_lo = col["qty_x0"] - 12
        body = [w for w in words if w["top"] > hdr + 10]
        rows = sorted([w for w in body if re.fullmatch(r"\d{1,3}", w["text"]) and abs(_cx(w) - col["hash_c"]) <= 14 and _cx(w) < zone_lo],
                      key=_cy)
        if not rows:
            continue
        centers = [_cy(w) for w in rows]
        if col["has_code_col"]:
            code_words = [w for w in body if col["hash_x1"] + 6 <= _cx(w) and w["x1"] <= col["code_hi"] + 2]
            desc_words = [w for w in body if w["x1"] > col["code_hi"] + 2 and _cx(w) < zone_lo]
        else:
            code_words = []
            desc_words = [w for w in body if w["x0"] >= col["desc_lo"] and _cx(w) < zone_lo]
        desc_lines = _group_lines(desc_words)
        ys = [ln["cy"] for ln in desc_lines]
        totals_top = min([w["top"] for w in body if w["text"].lower().strip(":") in ("total", "net", "shipping", "discount", "tax", "vat", "subtotal", "order")
                          and w["top"] > centers[-1] + 5], default=None)
        # حدود كل سطر: أكبر فراغ رأسي بين مركزَي سطرين متتاليين
        cuts = []
        for a, b in zip(centers, centers[1:]):
            S = [y for y in ys if a - 1 <= y <= b + 1]
            if len(S) >= 2:
                k = max(range(len(S) - 1), key=lambda i: S[i + 1] - S[i])
                cuts.append((S[k] + S[k + 1]) / 2.0)
            else:
                cuts.append((a + b) / 2.0)
        bounds = []
        for i, c in enumerate(centers):
            lo = cuts[i - 1] if i > 0 else (c - (cuts[0] - c) if cuts else c - 30)
            hi = cuts[i] if i < len(cuts) else (c + (c - cuts[-1]) if cuts else c + 30)
            if i == len(centers) - 1 and totals_top is not None:
                hi = min(hi, totals_top - 1)
            bounds.append((lo, hi))
        for (lo, hi), rw in zip(bounds, rows):
            inrow = [w for w in body if lo <= _cy(w) < hi]
            nums = {"qty": [], "price": [], "total": []}
            for w in inrow:
                if _cx(w) >= zone_lo and _is_num(w["text"]):
                    d = {"qty": abs(_cx(w) - col["qty_c"]), "price": abs(_cx(w) - col["price_c"]), "total": abs(_cx(w) - col["total_c"])}
                    k = min(d, key=d.get)
                    if d[k] <= 28:
                        nums[k].append(w)
            def first_num(k):
                ws = sorted(nums[k], key=lambda w: (_cy(w), w["x0"]))
                return _to_num(ws[0]["text"]) if ws else None
            qty, price, total = first_num("qty"), first_num("price"), first_num("total")
            if col["has_code_col"]:
                cws = sorted([w for w in code_words if lo <= _cy(w) < hi], key=lambda w: (_cy(w), w["x0"]))
                code = ""
                for w in cws:
                    code += w["text"] if (not code or code.endswith("-")) else " " + w["text"]
                code = code.replace(" ", "")
                dlines = [ln["text"] for ln in desc_lines if lo <= ln["cy"] < hi]
            else:
                dl = [ln for ln in desc_lines if lo <= ln["cy"] < hi]
                code = ""
                if dl and len(dl[0]["words"]) == 1 and re.search(r"\d", dl[0]["text"]):
                    code = dl[0]["text"]
                    dl = dl[1:]
                dlines = [ln["text"] for ln in dl]
            desc = " ".join(dlines)
            if code and desc.upper().startswith(code.upper()):
                desc = desc[len(code):].lstrip("- ")
            desc = re.sub(r"\s+", " ", desc).strip().rstrip("-").strip()
            n = int(rw["text"])
            if qty is None or price is None or qty <= 0:
                res["warnings"].append(f"السطر {n}: تعذّرت قراءة الكمية أو السعر — أضفه يدويًا")
                continue
            if total is None:
                total = round(qty * price, 2)
            res["lines"].append({"n": n, "code": code, "desc": desc, "qty": qty, "price": price, "total": total,
                                 "page": pi, "lo": lo, "hi": hi, "hdr": hdr})
        last_page, last_row_cy = pi, centers[-1]

    # ---- المجاميع (شحن / خصم / ضريبة / الصافي) بعد آخر سطر في الجدول
    if last_page is not None:
        tail = [w for w in pages[last_page] if w["top"] > (last_row_cy or 0) + 5]
        for pj in range(last_page + 1, len(pages)):
            tail += pages[pj]
        for ln in _group_lines(tail):
            toks = [w["text"].lower().strip(":") for w in ln["words"]]
            nums = [_to_num(w["text"]) for w in ln["words"] if _is_num(w["text"])]
            if not nums:
                continue
            val = nums[-1]
            if ("net" in toks and "total" in toks) or ("order" in toks and "total" in toks):
                res["net_pdf"] = val
            elif "shipping" in toks:
                res["shipping"] = val
            elif "discount" in toks:
                res["discount"] = val
            elif "tax" in toks or "vat" in toks:
                res["tax"] = val
    if not res["lines"]:
        res["warnings"].append("ما قدرت أتعرف على جدول الأصناف في هذا الملف.")
    return res


# ------------------------------------------------------------------ تخمين بيانات الصنف من وصف المورد
_MAKES_EN = {"toyota": "تويوتا", "hyundai": "هيونداي", "kia": "كيا", "nissan": "نيسان", "chevrolet": "شيفروليه", "ford": "فورد",
             "honda": "هوندا", "gmc": "جي إم سي", "lexus": "لكزس", "mazda": "مازدا", "mitsubishi": "ميتسوبيشي", "mercedes": "مرسيدس",
             "bmw": "بي إم دبليو", "suzuki": "سوزوكي", "isuzu": "ايسوزو", "jeep": "جيب", "dodge": "دودج", "geely": "جيلي",
             "changan": "شانجان", "haval": "هافال"}
_MODELS_EN = {"camry": "كامري", "corolla": "كورولا", "yaris": "يارس", "land cruiser": "لاندكروزر", "landcruiser": "لاندكروزر", "hilux": "هايلكس",
              "fortuner": "فورتشنر", "avalon": "أفالون", "prado": "برادو", "rav4": "راف فور",
              "sunny": "صني", "altima": "التيما", "maxima": "ماكسيما", "patrol": "باترول", "xterra": "اكستيرا", "kicks": "كيكس",
              "elantra": "النترا", "sonata": "سوناتا", "accent": "اكسنت", "tucson": "توسان", "santa fe": "سنتافي", "azera": "ازيرا",
              "cerato": "سيراتو", "optima": "اوبتيما", "rio": "ريو", "sportage": "سبورتاج", "sorento": "سورنتو",
              "taurus": "تورس", "explorer": "اكسبلورر", "expedition": "اكسبيديشن", "edge": "ايدج", "mustang": "موستنج",
              "malibu": "ماليبو", "caprice": "كابرس", "tahoe": "تاهو", "suburban": "سوبربان", "silverado": "سلفرادو",
              "yukon": "يوكن", "sierra": "سييرا", "accord": "اكورد", "civic": "سيفيك", "cr-v": "سي آر في"}


def guess_item_fields(code, desc):
    """تخمين نوع القطعة والشركة والموديل والسنوات من وصف المورد. المدير يراجعها ويكمّلها."""
    text = f"{code} {desc}"
    low = text.lower()
    out = {"category": "", "make": "", "model": "", "y1": "", "y2": "", "kind": "", "condition": "USED" if "USED" in text.upper() else "NEW", "origin": ""}
    if re.search(r"buttons?\s*pad", low):
        out["category"] = "أزرار ريموت"
    elif re.search(r"all in one|\bwith\s+shell\b", low):
        out["category"] = "ريموت"  # مفتاح كامل يأتي مع الغلاف
    elif re.search(r"\bshell\b|\bcover\b|\bcase\b", low):
        out["category"] = "غلاف مفتاح"
    elif re.search(r"remote|smart key|wire key|flip key|head key", low):
        out["category"] = "ريموت"
    elif re.search(r"\bchip\b|transponder", low):
        out["category"] = "شريحة"
    elif re.search(r"\bblade\b", low) or re.search(r"(^|-)b-\d", code.lower()):
        out["category"] = "نصلة"
    else:
        out["category"] = "أخرى"
    best = None
    for en, ar in _MAKES_EN.items():
        m = re.search(r"\b" + re.escape(en) + r"\b", low)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), ar)
    if best:
        out["make"] = best[1]
    for en, ar in _MODELS_EN.items():
        if re.search(r"(?<![a-z])" + re.escape(en) + r"(?![a-z])", low):
            out["model"] = ar
            break
    m = re.search(r"\b((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})\b", text)
    if m:
        out["y1"], out["y2"] = m.group(1), m.group(2)
    else:
        m = re.search(r"\b((?:19|20)\d{2})\b", desc)
        if m:
            out["y1"] = m.group(1)
    m = re.search(r"(\d(?:\+\d)?)\s*-?\s*buttons?", low)
    if m:
        out["kind"] = f"{m.group(1)} أزرار"
    gen = re.search(r"\bgenuine\b|\boriginal\b|\boem\b", low)
    aft = re.search(r"aftermarket|after market|\bcopy\b|\bchinese\b|\bchina\b", low)
    if gen and not aft:
        out["origin"] = "أصلي"
    elif aft and not gen:
        out["origin"] = "صيني"
    return out


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"العباد للمفاتيح — النسخة {APP_VERSION}")
        self.geometry("1240x760")
        self.minsize(1000, 620)
        try:
            self.state("zoomed")
        except Exception:
            pass
        self.user = None
        self.role = None
        self.perms = set()
        self.nav_buttons = {}
        self.setup_style()
        for _ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(_ev, lambda e: _on_wheel(self, e))
        self.login()

    # ------------------------------------------------------------------ المظهر
    def setup_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        self.option_add("*TCombobox*Listbox.font", (FONT, 10))
        s.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("Title.TLabel", font=(FONT, 19, "bold"), foreground=NAVY)
        s.configure("Sub.TLabel", font=(FONT, 10), foreground=MUTED)
        s.configure("TButton", padding=(12, 7), relief="flat", background="#e2e8f0", foreground=TEXT, borderwidth=0)
        s.map("TButton", background=[("active", "#cbd5e1"), ("disabled", "#f1f5f9")])
        s.configure("Accent.TButton", background=ACCENT, foreground="white", font=(FONT, 10, "bold"))
        s.map("Accent.TButton", background=[("active", ACCENT_D)])
        s.configure("Success.TButton", background=GREEN, foreground="white", font=(FONT, 10, "bold"))
        s.map("Success.TButton", background=[("active", "#15803d")])
        s.configure("Danger.TButton", background=RED, foreground="white", font=(FONT, 10, "bold"))
        s.map("Danger.TButton", background=[("active", "#b91c1c")])
        s.configure("TEntry", padding=6, fieldbackground="white", bordercolor=BORDER)
        s.configure("TCombobox", padding=5, fieldbackground="white", arrowsize=14)
        s.configure("TLabelframe", background=BG, bordercolor=BORDER)
        s.configure("TLabelframe.Label", background=BG, foreground=NAVY, font=(FONT, 10, "bold"))
        s.configure("Treeview", rowheight=(30 if self.winfo_screenheight() >= 900 else 24), font=(FONT, 10), background="white", fieldbackground="white", foreground=TEXT, bordercolor=BORDER)
        s.configure("Treeview.Heading", background=NAVY, foreground="white", font=(FONT, 10, "bold"), padding=8, relief="flat")
        s.map("Treeview.Heading", background=[("active", "#1e293b")])
        s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(18, 8), font=(FONT, 10, "bold"), background="#e2e8f0")
        s.map("TNotebook.Tab", background=[("selected", "white")])
        s.configure("TRadiobutton", background=BG)
        s.configure("TCheckbutton", background=BG)

    def can(self, key):
        return self.role == "admin" or key in self.perms

    def center(self, win, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(w, sw - 30)
        h = min(h, sh - 90)  # يترك مكانًا لشريط المهام حتى لا ينزل أسفل النافذة تحت الشاشة
        x = self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 2)
        x = max(0, min(x, sw - w - 10))
        y = max(0, min(y, sh - h - 70))
        win.geometry(f"{w}x{h}+{x}+{y}")

    def autosize(self, win, frame, w):
        win.update_idletasks()
        h = min(frame.winfo_reqheight() + 30, self.winfo_screenheight() - 120)
        self.center(win, w, h)

    def dialog_size(self, win, content, bar, w):
        """يضبط حجم النافذة على قدر الشاشة (زر الحفظ يبقى ظاهرًا دائمًا)."""
        win.update_idletasks()
        h = content.winfo_reqheight() + bar.winfo_reqheight() + 30
        h = min(h, self.winfo_screenheight() - 120)
        self.center(win, w, h)

    def scroll_area(self, parent):
        """إطار قابل للتمرير (سكرول) داخل النافذة."""
        outer, inner, _canvas = make_scrollable(parent, BG, True, pad=14)
        outer.pack(fill="both", expand=True)
        return inner

    def _old_scroll_area(self, parent):
        """إطار قابل للتمرير (سكرول) داخل النافذة."""
        outer = ttk.Frame(parent)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=14)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        canvas.pack(side="right", fill="both", expand=True)

        def wheel(e):
            if getattr(e, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

        def bind_wheel(_e=None):
            canvas.bind_all("<MouseWheel>", wheel)
            canvas.bind_all("<Button-4>", wheel)
            canvas.bind_all("<Button-5>", wheel)

        def unbind_wheel(_e=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)
        return inner

    # ------------------------------------------------------------------ دخول
    def login(self):
        self.user = None
        self.role = None
        self.perms = set()
        self.nav_buttons = {}
        for w in self.winfo_children():
            w.destroy()
        self.configure(bg=NAVY)
        self.title(f"العباد للمفاتيح — النسخة {APP_VERSION}")

        outer = tk.Frame(self, bg=NAVY)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg="white", padx=46, pady=34)
        card.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(card, text="🔑", bg="white", font=(FONT, 34)).pack()
        tk.Label(card, text="العباد للمفاتيح", bg="white", fg=NAVY, font=(FONT, 22, "bold")).pack(pady=(4, 0))
        tk.Label(card, text="نظام إدارة المخزون والمبيعات", bg="white", fg=MUTED, font=(FONT, 10)).pack()
        tk.Label(card, text=f"النسخة {APP_VERSION}", bg="white", fg=ACCENT, font=(FONT, 10, "bold")).pack(pady=(2, 16))

        tk.Label(card, text="اسم المستخدم", bg="white", fg=TEXT, font=(FONT, 10, "bold")).pack(anchor="e")
        u = ttk.Entry(card, justify="right", width=34, font=(FONT, 11))
        u.pack(pady=(4, 12))
        tk.Label(card, text="كلمة المرور", bg="white", fg=TEXT, font=(FONT, 10, "bold")).pack(anchor="e")
        p = ttk.Entry(card, show="•", justify="right", width=34, font=(FONT, 11))
        p.pack(pady=(4, 16))

        ttk.Button(card, text="دخول", style="Accent.TButton", command=lambda: self.auth(u.get().strip(), p.get())).pack(fill="x", ipady=4)
        ttk.Button(card, text="التحقق من وجود تحديث", command=self.check_for_updates).pack(fill="x", pady=(8, 0))
        if default_password_in_use():
            tk.Label(card, text="أول دخول: admin / ChangeMe123!  (غيّر كلمة المرور فورًا)", bg="white", fg=AMBER, font=(FONT, 9)).pack(pady=(14, 0))
        p.bind("<Return>", lambda e: self.auth(u.get().strip(), p.get()))
        u.bind("<Return>", lambda e: p.focus_set())
        u.focus_set()

    def _run_bg(self, work, done):
        """يشغّل عملًا طويلًا في خيط خلفي ويستدعي done(نتيجة، خطأ) داخل خيط الواجهة (آمن)."""
        box = {}

        def runner():
            try:
                box["ok"] = work()
            except Exception as e:
                box["err"] = e
            finally:
                box["done"] = True

        threading.Thread(target=runner, daemon=True).start()

        def poll():
            if not box.get("done"):
                try:
                    self.after(150, poll)
                except tk.TclError:
                    pass
                return
            done(box.get("ok"), box.get("err"))

        self.after(150, poll)

    def check_for_updates(self):
        """يبحث عن إصدار أحدث في GitHub Releases. لا يغيّر قاعدة البيانات ولا الصور."""
        if getattr(self, "_update_busy", False):
            return
        self._update_busy = True
        self.config(cursor="watch")

        def finish(rel, err):
            self._update_busy = False
            self.config(cursor="")
            if err is not None:
                if isinstance(err, urllib.error.HTTPError) and err.code in (403, 429):
                    msg = "GitHub رفض الطلب مؤقتًا (كثرة المحاولات). جرّب بعد قليل."
                else:
                    msg = "تعذر الاتصال بخادم التحديثات. تحقق من الإنترنت.\n\n" + str(err)
                messagebox.showerror("تعذر التحقق من التحديث", msg)
                return
            if not rel or not rel["tag"]:
                messagebox.showinfo("التحديثات", "لا يوجد إصدار منشور في GitHub حتى الآن.")
                return
            if not is_newer(rel["version"], APP_VERSION):
                messagebox.showinfo("التحديثات", f"أنت تستخدم أحدث إصدار ({APP_VERSION}).")
                return
            if not rel["has_asset"]:
                messagebox.showwarning("التحديثات", f"يوجد إصدار أحدث ({rel['version']}) لكن ملف {UPDATE_ASSET_NAME} غير مرفق به.")
                return
            notes = rel["notes"][:400]
            body = f"يتوفر إصدار جديد: {rel['version']}\nالإصدار الحالي: {APP_VERSION}\n"
            if notes:
                body += "\nما الجديد:\n" + notes + "\n"
            if not getattr(sys, "frozen", False):
                if messagebox.askyesno("تحديث جديد", body + "\nالتحديث التلقائي يعمل في نسخة EXE فقط.\nهل تفتح صفحة التنزيل؟"):
                    webbrowser.open(rel["page"])
                return
            if messagebox.askyesno("تحديث جديد", body + "\nهل تريد تنزيله وتثبيته الآن؟\nسيُغلق البرنامج ويُعاد فتحه، وتبقى قاعدة البيانات والصور كما هي."):
                self._install_update(rel)

        self._run_bg(fetch_latest_release, finish)

    def _install_update(self, rel):
        wait = tk.Toplevel(self)
        wait.title("تحديث")
        wait.configure(bg=BG)
        wait.transient(self)
        ttk.Label(wait, text="جاري تنزيل التحديث... لا تغلق البرنامج", padding=24).pack()
        self.center(wait, 360, 90)

        def finish(new_exe, err):
            try:
                wait.destroy()
            except tk.TclError:
                pass
            if err is not None:
                messagebox.showerror("فشل التحديث", "لم يتم تثبيت التحديث. النسخة الحالية وبياناتك لم تُحذف.\n\n" + str(err))
                return
            try:
                launch_update_installer(new_exe)
            except Exception as e:
                messagebox.showerror("فشل التحديث", "تعذر بدء التثبيت. النسخة الحالية وبياناتك لم تُحذف.\n\n" + str(e))
                return
            self.destroy()

        self._run_bg(lambda: download_update(rel["url"], rel["sha256"]), finish)

    def auth(self, u, p):
        with connect() as c:
            r = c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()

        if r and hmac.compare_digest(pw_hash(p, r["salt"])[1], r["hash"]):
            self.user = u
            self.role = r["role"]
            self.perms = set(ALL_PERMS) if self.role == "admin" else str_to_perms(r["perms"])
            self.home()
        else:
            messagebox.showerror("خطأ", "اسم المستخدم أو كلمة المرور غير صحيحة")

    # ------------------------------------------------------------------ الإطار الرئيسي
    def home(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(bg=BG)
        self.title(f"العباد للمفاتيح — النسخة {APP_VERSION}")
        self.nav_buttons = {}

        header = tk.Frame(self, bg=NAVY, height=62)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🔑  العباد للمفاتيح", bg=NAVY, fg="white", font=(FONT, 18, "bold")).pack(side="right", padx=22)
        who = ("المدير" if self.role == "admin" else "الموظف") + " — " + self.user
        tk.Label(header, text="👤  " + who, bg=NAVY, fg="#cbd5e1", font=(FONT, 11)).pack(side="left", padx=22)
        tk.Label(header, text=f"v{APP_VERSION}", bg=NAVY, fg="#64748b", font=(FONT, 10)).pack(side="left")
        self.alert_btn = None
        if self.can("shortage"):
            self.alert_btn = tk.Button(header, text="🔔 النواقص", command=self.alerts_window, bg="#475569", fg="white",
                                       activebackground="#334155", activeforeground="white", relief="flat", bd=0, font=(FONT, 10, "bold"),
                                       padx=14, pady=6, cursor="hand2")
            self.alert_btn.pack(side="left", padx=6)
        if self.role == "admin":
            tk.Button(header, text="👥  إضافة موظف / الصلاحيات", command=self.users_page, bg=ACCENT, fg="white",
                      activebackground=ACCENT_D, activeforeground="white", relief="flat", bd=0, font=(FONT, 10, "bold"),
                      padx=14, pady=6, cursor="hand2").pack(side="left", padx=6)
            tk.Button(header, text="🔄  التحقق من تحديث", command=self.check_for_updates, bg="#0f766e", fg="white",
                      activebackground="#115e59", activeforeground="white", relief="flat", bd=0, font=(FONT, 10, "bold"),
                      padx=14, pady=6, cursor="hand2").pack(side="left", padx=6)
            tk.Button(header, text="📄  Google Sheets", command=self.sync_from_settings, bg="#475569", fg="white",
                      activebackground="#334155", activeforeground="white", relief="flat", bd=0, font=(FONT, 10, "bold"),
                      padx=14, pady=6, cursor="hand2").pack(side="left", padx=6)

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)
        side = tk.Frame(main, bg=SIDEBAR, width=225)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        body_wrap, self.body, self.body_canvas = make_scrollable(main, BG, True, pad=20)
        body_wrap.pack(side="left", fill="both", expand=True)

        def foot_btn(text, cmd):
            b = tk.Button(side, text=text, command=cmd, anchor="e", bg=SIDEBAR, fg="#94a3b8", activebackground="#1f2937",
                          activeforeground="white", relief="flat", bd=0, font=(FONT, 10), padx=18, pady=8, cursor="hand2")
            b.pack(side="bottom", fill="x")

        foot_btn("🚪  تسجيل خروج", self.login)
        foot_btn("🔑  تغيير كلمة المرور", self.change_pw)

        is_admin = self.role == "admin"
        nav = [
            ("dash", "🏠  الرئيسية", self.dashboard, True),
            ("inventory", "📦  المخزون والبحث", self.inventory, True),
            ("bundles", "🎁  المنتجات المركّبة", self.bundles_page, is_admin or self.can("inv_edit")),
            ("sales", "🧾  المبيعات", self.sales, self.can("sales")),
            ("customers", "👥  العملاء والديون", self.customers, self.can("customers")),
            ("purchases", "🛒  المشتريات", self.purchases, self.can("purchases")),
            ("po", "📝  طلب شراء من المورد", self.po_page, self.can("po")),
            ("suppliers", "🚚  الموردون", self.suppliers, self.can("suppliers")),
            ("cars", "🚗  الشركات والسيارات", self.cars_page, is_admin),
            ("types", "🏷  أنواع القطع", self.item_types_page, is_admin),
            ("expenses", "💸  المصروفات", self.expenses, self.can("expenses")),
            ("bonus", "🎯  البونص والأعمال", self.bonus_page_admin if is_admin else self.bonus_page_emp, is_admin or self.can("bonus")),
            ("reports", "📊  التقارير", self.reports, self.can("reports")),
            ("users", "🔐  المستخدمون والصلاحيات", self.users_page, is_admin),
            ("settings", "⚙  الإعدادات", self.settings, is_admin),
        ]

        def hover(btn, key, entering):
            if getattr(self, "active_nav", None) != key:
                btn.configure(bg="#1f2937" if entering else SIDEBAR)

        navwrap, navinner, _nc = make_scrollable(side, SIDEBAR, False, bar=False)
        navwrap.pack(fill="both", expand=True)
        tk.Frame(navinner, bg=SIDEBAR, height=6).pack()
        for key, label, fn, allowed in nav:
            if not allowed:
                continue
            b = tk.Button(navinner, text=label, command=fn, anchor="e", bg=SIDEBAR, fg="#cbd5e1", activebackground=ACCENT,
                          activeforeground="white", relief="flat", bd=0, font=(FONT, 11), padx=18, pady=6, cursor="hand2")
            b.pack(fill="x")
            b.bind("<Enter>", lambda e, b=b, k=key: hover(b, k, True))
            b.bind("<Leave>", lambda e, b=b, k=key: hover(b, k, False))
            self.nav_buttons[key] = (b, label)

        self.active_nav = None
        self.dashboard()

        if not getattr(self, "_auto_sync_started", False):
            self._auto_sync_started = True
            self.after(1500, lambda: self.sync_inventory(False))
            self.after(60000, self._auto_sync_inventory)

        self.after(1200, self.check_stock_alerts)
        if not getattr(self, "_alert_loop_started", False):
            self._alert_loop_started = True
            self.after(60000, self._stock_alert_tick)

    def _auto_sync_inventory(self):
        try:
            self.sync_inventory(False)
        finally:
            if self.winfo_exists():
                self.after(60000, self._auto_sync_inventory)

    def set_active(self, key):
        self.active_nav = key
        for k, (b, _) in self.nav_buttons.items():
            try:
                b.configure(bg=ACCENT if k == key else SIDEBAR, fg="white" if k == key else "#cbd5e1")
            except tk.TclError:
                pass

    def refresh_badges(self):
        if not self.nav_buttons:
            return
        try:
            with connect() as c:
                inc = c.execute("SELECT COUNT(*) FROM items WHERE incomplete=1").fetchone()[0] if self.can("view_cost") else 0
                pend_bonus = c.execute("SELECT COUNT(*) FROM bonus_claims WHERE status='pending'").fetchone()[0] if self.role == "admin" else 0
                pend_pur = c.execute("SELECT COUNT(*) FROM purchases WHERE status='pending'").fetchone()[0] if self.can("purchases") else 0
                pend_po = c.execute("SELECT COUNT(*) FROM purchase_orders WHERE status='pending'").fetchone()[0] if self.role == "admin" else 0
        except Exception:
            return
        extras = {"inventory": f"⚠ {inc}" if inc else "", "bonus": f"{pend_bonus}" if pend_bonus else "", "purchases": f"{pend_pur}" if pend_pur else "", "po": f"{pend_po}" if pend_po else ""}
        for key, extra in extras.items():
            if key in self.nav_buttons:
                b, base = self.nav_buttons[key]
                try:
                    b.configure(text=base + (f"   ●{extra}" if extra else ""))
                except tk.TclError:
                    pass

    def clear(self, nav=None):
        try:
            self.body_canvas.yview_moveto(0)
        except Exception:
            pass
        for w in self.body.winfo_children():
            w.destroy()
        if nav:
            self.set_active(nav)
        self.refresh_badges()

    def page_title(self, text, sub=None):
        f = ttk.Frame(self.body)
        f.pack(fill="x", pady=(0, 10))
        ttk.Label(f, text=text, style="Title.TLabel").pack(anchor="e")
        if sub:
            ttk.Label(f, text=sub, style="Sub.TLabel").pack(anchor="e")

    def table(self, cols, heads, rows, widths=None):
        t = make_tree(self.body, cols, heads, widths)
        for row in rows:
            add_row(t, row)
        return t

    def stat_card(self, parent, title, value, color):
        f = tk.Frame(parent, bg="white", highlightbackground=BORDER, highlightthickness=1)
        tk.Frame(f, bg=color, height=5).pack(fill="x")
        tk.Label(f, text=str(value), bg="white", fg=NAVY, font=(FONT, 21, "bold")).pack(anchor="e", padx=18, pady=(14, 0))
        tk.Label(f, text=title, bg="white", fg=MUTED, font=(FONT, 10)).pack(anchor="e", padx=18, pady=(0, 14))
        return f

    def card_grid(self, cards, per_row=4):
        grid = ttk.Frame(self.body)
        grid.pack(fill="x", pady=6)
        for i in range(per_row):
            grid.columnconfigure(i, weight=1, uniform="cards")
        for i, (title, value, color) in enumerate(cards):
            self.stat_card(grid, title, value, color).grid(row=i // per_row, column=i % per_row, padx=7, pady=7, sticky="nsew")
        return grid

    # ------------------------------------------------------------------ الرئيسية
    def dashboard(self):
        self.clear("dash")
        self.page_title(f"أهلًا {self.user}", "نظرة سريعة على العمل اليوم")
        today = datetime.now().strftime("%Y-%m-%d")
        cards = []
        with connect() as c:
            items_n = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            qty_total = c.execute("SELECT COALESCE(SUM(qty),0) FROM items").fetchone()[0]
            low = c.execute("SELECT COUNT(*) FROM items WHERE qty BETWEEN 1 AND 5").fetchone()[0]
            out = c.execute("SELECT COUNT(*) FROM items WHERE COALESCE(qty,0)<=0").fetchone()[0]
            mine = c.execute("SELECT COUNT(DISTINCT invoice) FROM sales WHERE seller=? AND date LIKE ?", (self.user, today + "%")).fetchone()[0]
            cards += [("عدد الأصناف", items_n, ACCENT), ("إجمالي القطع في المخزون", qty_total, ACCENT), ("منخفضة المخزون (1-5)", low, AMBER), ("نفدت من المخزون", out, RED), ("فواتيري اليوم", mine, GREEN)]
            if self.can("reports"):
                day_total = c.execute("SELECT COALESCE(SUM(price*qty),0) FROM sales WHERE date LIKE ?", (today + "%",)).fetchone()[0]
                debts = c.execute("SELECT COALESCE((SELECT SUM(price*qty-COALESCE(paid,0)) FROM sales),0)-COALESCE((SELECT SUM(amount) FROM debt_payments),0)").fetchone()[0]
                cards += [("مبيعات اليوم", sar(day_total), GREEN), ("صافي ديون العملاء", sar(debts), RED)]
            if self.can("view_cost"):
                inc = c.execute("SELECT COUNT(*) FROM items WHERE incomplete=1").fetchone()[0]
                cards.append(("أصناف معلوماتها ناقصة ⚠", inc, AMBER))
            if self.can("purchases"):
                pp = c.execute("SELECT COUNT(*) FROM purchases WHERE status='pending'").fetchone()[0]
                cards.append(("مشتريات لم تُضف للمخزون", pp, ACCENT))
            if self.role == "admin":
                pb = c.execute("SELECT COUNT(*) FROM bonus_claims WHERE status='pending'").fetchone()[0]
                cards.append(("طلبات بونص بانتظار اعتمادك", pb, AMBER))
        self.card_grid(cards)

        actions = ttk.Frame(self.body)
        actions.pack(fill="x", pady=14)
        if self.can("sales"):
            ttk.Button(actions, text="🧾  فاتورة بيع جديدة", style="Accent.TButton", command=self.new_sale).pack(side="right", padx=6)
        if self.can("inv_add"):
            ttk.Button(actions, text="＋  إضافة صنف", style="Success.TButton", command=self.add_item).pack(side="right", padx=6)
        if self.can("po"):
            ttk.Button(actions, text="📝  طلب شراء من المورد", style="Accent.TButton", command=self.po_page).pack(side="right", padx=6)
        ttk.Button(actions, text="📦  استعراض المخزون", command=self.inventory).pack(side="right", padx=6)
        if self.role == "admin":
            ttk.Button(actions, text="👤  إضافة موظف وتحديد صلاحياته", command=lambda: self.user_dialog(None, on_done=self.users_page)).pack(side="right", padx=6)

    # ------------------------------------------- القوائم المغلقة (سيارات / أنواع / موردون)
    def _add_make(self, name):
        name = clean_name(name)
        if not name:
            raise ValueError("اكتب اسم الشركة")
        with connect() as c:
            if c.execute("SELECT 1 FROM car_makes WHERE name=? COLLATE NOCASE", (name,)).fetchone():
                raise ValueError("الشركة موجودة مسبقًا")
            c.execute("INSERT INTO car_makes(name) VALUES(?)", (name,))
        return name

    def _add_model(self, make_name, name):
        name = clean_name(name)
        if not make_name:
            raise ValueError("اختر الشركة أولًا")
        if not name:
            raise ValueError("اكتب اسم الموديل")
        with connect() as c:
            mk = c.execute("SELECT id FROM car_makes WHERE name=?", (make_name,)).fetchone()
            if not mk:
                raise ValueError("الشركة غير موجودة")
            if c.execute("SELECT 1 FROM car_models WHERE make_id=? AND name=? COLLATE NOCASE", (mk["id"], name)).fetchone():
                raise ValueError("الموديل موجود مسبقًا لهذه الشركة")
            c.execute("INSERT INTO car_models(make_id,name) VALUES(?,?)", (mk["id"], name))
        return name

    def _insert_type(self, name):
        name = clean_name(name)
        if not name:
            raise ValueError("اكتب اسم النوع")
        with connect() as c:
            if c.execute("SELECT 1 FROM item_types WHERE name=? COLLATE NOCASE", (name,)).fetchone():
                raise ValueError("النوع موجود مسبقًا")
            c.execute("INSERT INTO item_types(name) VALUES(?)", (name,))
        return name

    def _insert_supplier(self, name, phone="", notes=""):
        name = clean_name(name)
        if not name:
            raise ValueError("اسم المورد مطلوب")
        with connect() as c:
            if c.execute("SELECT 1 FROM suppliers WHERE name=? COLLATE NOCASE", (name,)).fetchone():
                raise ValueError("المورد موجود مسبقًا")
            c.execute("INSERT INTO suppliers(name,phone,notes,code) VALUES(?,?,?,?)", (name, phone, notes, next_supplier_code(c)))
        return name

    def cars_page(self):
        self.clear("cars")
        self.page_title("الشركات والسيارات", "القائمة المعتمدة التي يختار منها الموظفون عند إضافة الأصناف")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        t = self.table(("make", "model"), {"make": "الشركة", "model": "الموديل"}, [])

        def load():
            clear_tree(t)
            with connect() as c:
                rows = c.execute("""
                    SELECT k.id kid,k.name make,m.id mid,m.name model
                    FROM car_makes k LEFT JOIN car_models m ON m.make_id=k.id
                    ORDER BY k.name,m.name
                """).fetchall()
            for r in rows:
                iid = f"m{r['mid']}" if r["mid"] else f"k{r['kid']}"
                add_row(t, (r["make"], r["model"] or ""), iid=iid)

        def add_make():
            name = simpledialog.askstring("إضافة شركة", "اسم الشركة:", parent=self)
            if not name:
                return
            try:
                self._add_make(name)
            except Exception as e:
                messagebox.showerror("خطأ", str(e))
                return
            load()

        def add_model():
            with connect() as c:
                makes = [r["name"] for r in c.execute("SELECT name FROM car_makes ORDER BY name").fetchall()]
            win = tk.Toplevel(self)
            win.title("إضافة موديل")
            win.configure(bg=BG)
            win.transient(self)
            win.grab_set()
            fr = ttk.Frame(win, padding=16)
            fr.pack(fill="both", expand=True)
            ttk.Label(fr, text="الشركة").grid(row=0, column=1, padx=6, pady=6, sticky="e")
            cb = ttk.Combobox(fr, values=makes, state="readonly", width=28)
            cb.grid(row=0, column=0, pady=6)
            sel = t.selection()
            if sel:
                cb.set(t.item(sel[0], "values")[0])
            ttk.Label(fr, text="اسم الموديل").grid(row=1, column=1, padx=6, pady=6, sticky="e")
            ent = ttk.Entry(fr, width=30, justify="right")
            ent.grid(row=1, column=0, pady=6)

            def ok():
                try:
                    self._add_model(cb.get(), ent.get())
                except Exception as e:
                    messagebox.showerror("خطأ", str(e), parent=win)
                    return
                win.destroy()
                load()

            ttk.Button(fr, text="حفظ", style="Accent.TButton", command=ok).grid(row=2, column=0, pady=10)
            self.autosize(win, fr, 400)

        def delete_sel():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد الصف المراد حذفه")
                return
            iid = sel[0]
            with connect() as c:
                if iid.startswith("m"):
                    r = c.execute("SELECT m.id,m.name,k.name make FROM car_models m JOIN car_makes k ON k.id=m.make_id WHERE m.id=?", (int(iid[1:]),)).fetchone()
                    if not r:
                        return
                    used = c.execute("SELECT COUNT(*) FROM items WHERE make=? AND model=?", (r["make"], r["name"])).fetchone()[0]
                    if used:
                        messagebox.showwarning("لا يمكن الحذف", f"هذا الموديل مستخدم في {used} صنف")
                        return
                    if not messagebox.askyesno("تأكيد", f"حذف الموديل {r['name']} من {r['make']}؟"):
                        return
                    c.execute("DELETE FROM car_models WHERE id=?", (r["id"],))
                else:
                    r = c.execute("SELECT id,name FROM car_makes WHERE id=?", (int(iid[1:]),)).fetchone()
                    if not r:
                        return
                    used = c.execute("SELECT COUNT(*) FROM items WHERE make=?", (r["name"],)).fetchone()[0]
                    if used:
                        messagebox.showwarning("لا يمكن الحذف", f"هذه الشركة مستخدمة في {used} صنف")
                        return
                    if not messagebox.askyesno("تأكيد", f"حذف الشركة {r['name']}؟"):
                        return
                    c.execute("DELETE FROM car_makes WHERE id=?", (r["id"],))
            load()

        ttk.Button(row, text="＋ إضافة شركة", style="Accent.TButton", command=add_make).pack(side="right", padx=4)
        ttk.Button(row, text="＋ إضافة موديل", style="Accent.TButton", command=add_model).pack(side="right", padx=4)
        ttk.Button(row, text="حذف المحدد", style="Danger.TButton", command=delete_sel).pack(side="left", padx=4)
        ttk.Label(self.body, text="لحذف شركة: احذف موديلاتها أولًا ثم احذف صفها الفارغ. لا يمكن حذف شيء مستخدم في أصناف.", style="Muted.TLabel").pack(anchor="e")
        load()

    # --------------------------------------------------------------- المخزون
    def inventory(self):
        self.clear("inventory")
        self.page_title("المخزون والبحث", "ابحث وتحكم بالأصناف حسب صلاحياتك")
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Label(row, text="بحث سريع (رقم الصنف / رقم القطعة / السيارة)").pack(side="right", padx=5)
        q = ttk.Entry(row, width=30, justify="right")
        q.pack(side="right")
        adv = ttk.LabelFrame(self.body, text="البحث المتقدم", padding=8)
        adv.pack(fill="x", pady=8)

        show_cost = self.can("view_cost")
        show_ws = show_cost or self.can("view_wholesale")
        show_sup = self.can("suppliers")

        with connect() as c:
            types = [r["name"] for r in c.execute("SELECT name FROM item_types ORDER BY name").fetchall()]
            sups = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()] if show_sup else []

        ttk.Label(adv, text="نوع القطعة").grid(row=0, column=5, padx=4, pady=3)
        cat = ttk.Combobox(adv, values=["الكل"] + types, state="readonly", width=16)
        cat.set("الكل")
        cat.grid(row=0, column=4, padx=4)
        ttk.Label(adv, text="المورد").grid(row=0, column=3, padx=4)
        sup = ttk.Combobox(adv, values=["الكل"] + sups, state="readonly" if show_sup else "disabled", width=16)
        sup.set("الكل")
        sup.grid(row=0, column=2, padx=4)
        ttk.Label(adv, text="السيارة / الموديل").grid(row=1, column=5, padx=4, pady=3)
        carq = ttk.Entry(adv, width=18, justify="right")
        carq.grid(row=1, column=4, padx=4)
        ttk.Label(adv, text="السنة").grid(row=1, column=3, padx=4)
        yearq = ttk.Entry(adv, width=18, justify="right")
        yearq.grid(row=1, column=2, padx=4)
        ttk.Label(adv, text="المخزون").grid(row=0, column=1, padx=4)
        stock = ttk.Combobox(adv, values=["الكل", "متوفر", "منخفض (1-5)", "نفد"], state="readonly", width=15)
        stock.set("الكل")
        stock.grid(row=0, column=0, padx=4)
        inc_var = tk.IntVar(value=0)
        if show_cost:
            ttk.Checkbutton(adv, text="⚠ الأصناف ناقصة المعلومات فقط", variable=inc_var, command=lambda: load()).grid(row=1, column=1, columnspan=1, padx=4)

        cols = []
        if show_cost:
            cols.append("alert")
        cols += ["item_no", "photo", "part", "car", "years", "category", "qty", "location", "condition", "kind", "origin"]
        if show_cost:
            cols.append("cost")
        if show_ws:
            cols.append("wholesale_min")
        cols.append("retail")
        if show_cost:
            cols.append("retail_low")
        if show_sup:
            cols += ["supplier", "rep_code"]
        if self.can("shortage"):
            cols.append("min_qty")
        heads = {"min_qty": "حد التنبيه", "origin": "الأصل", "photo": "صورة", "rep": "المورد", "rep_code": "رمز عند المورد", "id": "معرّف", "alert": "تنبيه", "item_no": "رقم الصنف / الباركود", "condition": "الحالة", "part": "رقم القطعة", "car": "السيارة", "years": "السنوات",
                 "category": "نوع القطعة", "kind": "نوع المفتاح", "qty": "الكمية", "cost": "التكلفة الحقيقية", "wholesale_min": "سعر الجملة", "retail": "سعر المفرد",
                 "retail_low": "أقل بيع مفرد سابق", "supplier": "المورد", "location": "الموقع"}
        widths = {"min_qty": 90, "origin": 70, "alert": 125, "item_no": 120, "part": 120, "car": 140, "years": 90, "category": 100, "qty": 70, "location": 110, "condition": 75, "kind": 100, "cost": 110, "wholesale_min": 100, "retail": 100, "retail_low": 120, "supplier": 110, "photo": 55, "rep": 110, "rep_code": 130}
        t = make_tree(self.body, cols, heads, widths)
        count_var = tk.StringVar(value="")
        ttk.Label(self.body, textvariable=count_var, style="Muted.TLabel").pack(anchor="e")

        if self.can("inv_add"):
            ttk.Button(row, text="＋ إضافة صنف", style="Accent.TButton", command=self.add_item).pack(side="left")
        if self.can("inv_edit"):
            ttk.Button(row, text="تعديل الصنف المحدد", command=lambda: self.edit_item(t)).pack(side="left", padx=4)
        if self.role == "admin" or self.can("inv_edit"):
            ttk.Button(row, text="🧬 فحص المكرر", command=self.duplicates_window).pack(side="left", padx=4)
            ttk.Button(row, text="🖼 صور من فاتورة", command=self.import_images_only).pack(side="left", padx=4)
        if self.can("shortage"):
            ttk.Button(row, text="🔔 حد التنبيه للمحدد", command=lambda: self.set_min_qty(t)).pack(side="left", padx=4)
        if self.can("barcode"):
            ttk.Button(row, text="طباعة باركود", command=lambda: self.print_barcode(t)).pack(side="left", padx=4)
        ttk.Button(row, text="🖼 عرض الصورة", command=lambda: self.view_image(int(t.selection()[0])) if t.selection() else messagebox.showwarning("تنبيه", "حدد الصنف أولًا")).pack(side="left", padx=4)
        if self.can("po"):
            ttk.Button(row, text="📝 طلب شراء", style="Accent.TButton", command=self.po_page).pack(side="left", padx=4)
        if self.can("shortage"):
            ttk.Button(row, text="📤 النواقص ← مسؤول المشتريات", style="Success.TButton", command=lambda: self.shortage_window(sup.get() if sup.get() != "الكل" else None)).pack(side="left", padx=4)
        if self.can("view_cost") or self.can("purchases"):
            ttk.Button(row, text="📉 سجل أسعار الشراء", command=lambda: self.price_history(int(t.selection()[0]) if t.selection() else None)).pack(side="left", padx=4)

        def load():
            bm = parse_barcode(q.get())
            query = "%" + (bm[0] if bm else q.get().strip()) + "%"
            cq = "%" + carq.get().strip() + "%"
            y = yearq.get().strip()
            with connect() as c:
                rows = c.execute("""
                    SELECT i.*,
                    COALESCE(i.buy,0)+COALESCE(i.expense,0) AS cost,
                    ROUND((COALESCE(i.buy,0)+COALESCE(i.expense,0))*(1+COALESCE(i.profit,0)/100.0),2) AS wholesale_min,
                    COALESCE(i.retail,0) AS retail,
                    COALESCE((SELECT MIN(s.price) FROM sales s WHERE s.item_id=i.id AND s.kind='مفرد'),0) AS retail_low
                    FROM items i
                    WHERE (COALESCE(i.item_no,'') LIKE ?
                    OR COALESCE(i.part,'') LIKE ?
                    OR COALESCE(i.car,'') LIKE ?
                    OR COALESCE(i.kind,'') LIKE ?
                    OR COALESCE(i.notes,'') LIKE ?
                    OR COALESCE(i.rep_code,'') LIKE ?
                    OR COALESCE(i.origin,'') LIKE ?)
                    AND (?='الكل' OR COALESCE(i.category,'غير محدد')=?)
                    AND (?='الكل' OR COALESCE(i.supplier,'')=? OR EXISTS(SELECT 1 FROM purchases p WHERE p.item_id=i.id AND p.supplier=?))
                    AND COALESCE(i.car,'') LIKE ?
                    AND (?='' OR COALESCE(i.y1,'') LIKE ? OR COALESCE(i.y2,'') LIKE ?)
                    AND (?=0 OR COALESCE(i.incomplete,0)=1)
                    ORDER BY i.id DESC
                """, (query, query, query, query, query, query, query, cat.get(), cat.get(), sup.get(), sup.get(), sup.get(), cq, y, "%" + y + "%", "%" + y + "%", inc_var.get())).fetchall()

            clear_tree(t)
            shown = 0
            qty_sum = 0
            for r in rows:
                qty = r["qty"] or 0
                if stock.get() == "متوفر" and qty <= 0:
                    continue
                if stock.get() == "منخفض (1-5)" and not (1 <= qty <= 5):
                    continue
                if stock.get() == "نفد" and qty > 0:
                    continue
                values = []
                for col in cols:
                    if col == "years":
                        values.append(f"{r['y1'] or ''}-{r['y2'] or ''}")
                    elif col == "condition":
                        values.append("مستعمل" if str(r["condition"] or "NEW").upper() == "USED" else "جديد")
                    elif col == "category":
                        values.append(r["category"] or "غير محدد")
                    elif col == "min_qty":
                        values.append("" if r["min_qty"] is None else r["min_qty"])
                    elif col == "origin":
                        values.append(r["origin"] or "")
                    elif col == "alert":
                        values.append("⚠ معلومات ناقصة" if r["incomplete"] else "")
                    elif col in ("cost", "wholesale_min", "retail", "retail_low"):
                        values.append(sar(r[col]))
                    elif col == "supplier":
                        values.append(r["supplier"] or "")
                    elif col == "photo":
                        values.append("📷" if r["image"] else "")
                    elif col == "rep":
                        values.append(r["supplier"] or "")
                    elif col == "rep_code":
                        values.append(r["rep_code"] or "")
                    else:
                        values.append(r[col] if col in r.keys() else "")
                extra = []
                if r["incomplete"] and show_cost:
                    extra.append("incomplete")
                if qty <= 0:
                    extra.append("out")
                elif qty <= 5:
                    extra.append("low")
                add_row(t, values, iid=str(r["id"]), extra=extra)
                shown += 1
                qty_sum += qty
            count_var.set(f"عدد الأصناف: {shown}   |   إجمالي القطع: {qty_sum}   (الأحمر = نفد، البرتقالي = منخفض)")

        ttk.Button(adv, text="🔍 بحث", style="Accent.TButton", command=load).grid(row=1, column=0, padx=4)
        for widget in (q, carq, yearq):
            widget.bind("<Return>", lambda e: load())
        cat.bind("<<ComboboxSelected>>", lambda e: load())
        sup.bind("<<ComboboxSelected>>", lambda e: load())
        stock.bind("<<ComboboxSelected>>", lambda e: load())
        t.bind("<Double-1>", lambda e: self.view_image(int(t.selection()[0])) if t.selection() else None)
        load()

    def view_image(self, item_id):
        with connect() as c:
            r = c.execute("SELECT item_no,part,car,image FROM items WHERE id=?", (item_id,)).fetchone()
        if not r or not r["image"]:
            messagebox.showinfo("الصورة", "لا توجد صورة لهذا الصنف. أضفها من (تعديل الصنف).")
            return
        path = image_path(r["image"])
        if not os.path.exists(path):
            messagebox.showwarning("الصورة", "ملف الصورة غير موجود في مجلد item_images")
            return
        ph = load_photo(path, (720, 540))
        if not ph:
            try:
                os.startfile(path)
            except AttributeError:
                webbrowser.open(Path(path).as_uri())
            return
        win = tk.Toplevel(self)
        win.title(f"{r['item_no']} — {r['part']}")
        win.configure(bg=BG)
        lbl = ttk.Label(win, image=ph)
        lbl.image = ph
        lbl.pack(padx=14, pady=14)
        ttk.Label(win, text=f"{r['part']} — {r['car'] or ''}", font=(FONT, 12, "bold")).pack(pady=(0, 6))
        ttk.Button(win, text="فتح الصورة الأصلية", command=lambda: webbrowser.open(Path(path).as_uri())).pack(pady=(0, 12))

    # ----------------------------------------------------- نافذة إضافة / تعديل صنف
    def item_dialog(self, row=None, prefill=None, on_saved=None):
        editing = row is not None
        is_admin = self.role == "admin"
        privileged = self.can("view_cost")

        with connect() as c:
            makes = [r["name"] for r in c.execute("SELECT name FROM car_makes ORDER BY name").fetchall()]
            types = [r["name"] for r in c.execute("SELECT name FROM item_types ORDER BY name").fetchall()]

        win = tk.Toplevel(self)
        win.title("تعديل الصنف" if editing else "إضافة صنف")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        frame = self.scroll_area(win)
        frame.columnconfigure(1, weight=1)
        counter = [0]

        def line(label, widget, plus=None):
            i = counter[0]
            ttk.Label(frame, text=label).grid(row=i, column=2, sticky="e", padx=5, pady=3)
            widget.grid(row=i, column=1, sticky="ew", padx=5, pady=3)
            if plus:
                ttk.Button(frame, text="+", width=3, command=plus).grid(row=i, column=0, padx=2)
            counter[0] += 1

        def entry(default=""):
            e = ttk.Entry(frame, justify="right", width=36)
            e.insert(0, "" if default is None else str(default))
            return e

        def val(key, default=""):
            src = row if editing else prefill
            if src is None:
                return default
            try:
                v = src[key]
            except (KeyError, IndexError):
                return default
            return default if v is None else v

        if editing and not (val("make") and val("model")) and val("car"):
            ttk.Label(frame, text=f"السيارة الحالية (إدخال قديم): {val('car')} — اختر من القائمة لاستبدالها", foreground=AMBER).grid(row=counter[0], column=0, columnspan=3, sticky="e", pady=3)
            counter[0] += 1

        if not privileged:
            ttk.Label(frame, text="التكلفة وسعر الجملة والأرباح يحددها المدير لاحقًا — سيظهر الصنف عنده بعلامة (معلومات ناقصة)", foreground=MUTED).grid(row=counter[0], column=0, columnspan=3, sticky="e", pady=3)
            counter[0] += 1

        item_no = entry(val("item_no"))
        line("رقم الصنف (اتركه فارغًا للتوليد)", item_no)
        part = entry(val("part"))
        line("رقم القطعة", part)

        make_cb = ttk.Combobox(frame, values=makes, state="readonly", justify="right")
        model_cb = ttk.Combobox(frame, values=[], state="readonly", justify="right")
        cat_list = list(types)
        cur_cat = val("category", "")
        if cur_cat and cur_cat not in cat_list:
            cat_list.append(cur_cat)
        cat_cb = ttk.Combobox(frame, values=cat_list, state="readonly", justify="right")

        def load_models(select=None):
            with connect() as c:
                mk = c.execute("SELECT id FROM car_makes WHERE name=?", (make_cb.get(),)).fetchone()
                models = [r["name"] for r in c.execute("SELECT name FROM car_models WHERE make_id=? ORDER BY name", (mk["id"],)).fetchall()] if mk else []
            model_cb.configure(values=models)
            model_cb.set(select if select in models else "")

        def refresh_makes(select=None):
            with connect() as c:
                names = [r["name"] for r in c.execute("SELECT name FROM car_makes ORDER BY name").fetchall()]
            make_cb.configure(values=names)
            if select:
                make_cb.set(select)
                load_models()

        def plus_make():
            name = simpledialog.askstring("إضافة شركة", "اسم الشركة:", parent=win)
            if not name:
                return
            try:
                name = self._add_make(name)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            refresh_makes(name)

        def plus_model():
            if not make_cb.get():
                messagebox.showwarning("تنبيه", "اختر الشركة أولًا", parent=win)
                return
            name = simpledialog.askstring("إضافة موديل", f"اسم الموديل (للشركة {make_cb.get()}):", parent=win)
            if not name:
                return
            try:
                name = self._add_model(make_cb.get(), name)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            load_models(name)

        def plus_type():
            name = simpledialog.askstring("إضافة نوع قطعة", "اسم النوع:", parent=win)
            if not name:
                return
            try:
                name = self._insert_type(name)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            with connect() as c:
                names = [r["name"] for r in c.execute("SELECT name FROM item_types ORDER BY name").fetchall()]
            cat_cb.configure(values=names)
            cat_cb.set(name)

        line("الشركة", make_cb, plus_make if is_admin else None)
        line("الموديل", model_cb, plus_model if is_admin else None)
        make_cb.bind("<<ComboboxSelected>>", lambda e: load_models())

        if val("make") in makes:
            make_cb.set(val("make"))
            load_models(val("model"))

        y1 = entry(val("y1"))
        line("من سنة", y1)
        y2 = entry(val("y2"))
        line("إلى سنة", y2)

        line("نوع القطعة", cat_cb, plus_type if is_admin else None)
        if cur_cat:
            cat_cb.set(cur_cat)
        elif "ريموت" in cat_list:
            cat_cb.set("ريموت")

        kind = entry(val("kind"))
        line("نوع المفتاح", kind)

        origin_cb = ttk.Combobox(frame, values=["أصلي", "صيني"], state="readonly", justify="right")
        if val("origin"):
            origin_cb.set(val("origin"))
        line("الأصل (أصلي / صيني)", origin_cb)

        min_qty_e = None
        if self.can("shortage"):
            min_qty_e = entry(val("min_qty", ""))
            line("حد تنبيه النواقص (فارغ = بدون تنبيه، 0 = عند النفاد)", min_qty_e)

        rep_code = entry(val("rep_code"))
        line("رمز المنتج عند المورد (رقم أو اسم في نظامه)", rep_code)

        img = {"src": (val("image_src") or None), "remove": False, "current": val("image")}
        img_box = ttk.Frame(frame)
        img_lbl = ttk.Label(img_box, text="لا توجد صورة", style="Muted.TLabel")
        img_lbl.pack(side="right", padx=6)

        def refresh_preview():
            path = img["src"] or (image_path(img["current"]) if img["current"] and not img["remove"] else "")
            img_lbl.image = None
            if not path or not os.path.exists(path):
                img_lbl.configure(image="", text="لا توجد صورة")
                return
            ph = load_photo(path, (110, 110))
            if ph:
                img_lbl.configure(image=ph, text="")
                img_lbl.image = ph
            else:
                img_lbl.configure(image="", text="تم اختيار الصورة ✔ (المعاينة داخل البرنامج تحتاج مكتبة Pillow)")

        def pick_img():
            f = filedialog.askopenfilename(parent=win, title="اختر صورة المنتج",
                                           filetypes=[("صور", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("كل الملفات", "*.*")])
            if f:
                img["src"] = f
                img["remove"] = False
                refresh_preview()

        def clear_img():
            img["src"] = None
            img["remove"] = True
            refresh_preview()

        ttk.Button(img_box, text="🗑", width=3, command=clear_img).pack(side="left", padx=2)
        ttk.Button(img_box, text="📷 اختيار صورة", command=pick_img).pack(side="left", padx=2)
        line("صورة المنتج", img_box)
        refresh_preview()

        qty = entry(val("qty", 1))
        line("الكمية", qty)

        buy = expense = profit = None
        calc_var = tk.StringVar(value="")
        if privileged:
            buy = entry(val("buy", 0))
            line("سعر الشراء (للوحدة)", buy)
            ep = val("expense_pct", None)
            if ep in (None, ""):
                ep = round(num(val("expense", 0)) / num(val("buy", 0)) * 100, 2) if num(val("buy", 0)) > 0 else 0
            expense = entry(ep)
            line("المصاريف % (نسبة من سعر الشراء)", expense)
            profit = entry(val("profit", 0))
            line("الربح % للجملة (نسبة من التكلفة الأساسية)", profit)
            ttk.Label(frame, textvariable=calc_var, foreground=GREEN, font=(FONT, 10, "bold")).grid(row=counter[0], column=0, columnspan=3, sticky="e", pady=3)
            counter[0] += 1

            def refresh_calc(*_):
                base = num(buy.get()) * (1 + num(expense.get()) / 100.0)
                calc_var.set(f"التكلفة الأساسية: {sar(base)}   |   سعر الجملة: {sar(base * (1 + num(profit.get()) / 100.0))}")

            for w_ in (buy, expense, profit):
                w_.bind("<KeyRelease>", refresh_calc)
            refresh_calc()

        retail = entry(val("retail", 0) if editing else "0")
        line("سعر الأفراد", retail)
        location = entry(val("location"))
        line("الموقع", location)
        cond = ttk.Combobox(frame, values=["جديد", "مستعمل"], state="readonly", justify="right")
        cond.set("مستعمل" if str(val("condition", "NEW")).upper() == "USED" else "جديد")
        line("الحالة", cond)
        notes = entry(val("notes"))
        line("ملاحظات", notes)

        def save():
            d = {
                "item_no": item_no.get().strip(), "part": part.get().strip(),
                "make": make_cb.get().strip(), "model": model_cb.get().strip(),
                "legacy_car": val("car") if editing else "",
                "y1": y1.get().strip(), "y2": y2.get().strip(),
                "category": cat_cb.get().strip(), "kind": kind.get().strip(),
                "rep_code": rep_code.get().strip(),
                "origin": origin_cb.get().strip(),
                "min_qty": (min_qty_e.get().strip() if min_qty_e is not None else None),
                "image_src": img["src"], "image_remove": img["remove"],
                "qty": qty.get().strip(),
                "buy": buy.get().strip() if buy else "0",
                "expense": expense.get().strip() if expense else "0",
                "profit": profit.get().strip() if profit else "0",
                "retail": retail.get().strip(),
                "location": location.get().strip(),
                "condition": "USED" if cond.get() == "مستعمل" else "NEW",
                "notes": notes.get().strip(),
            }
            if not editing and not d["origin"]:
                messagebox.showerror("خطأ", "اختر الأصل: أصلي أو صيني", parent=win)
                return
            if not editing and not val("_skip_dup"):
                cand = {k: d[k] for k in ("part", "rep_code", "make", "model", "category", "kind", "y1", "y2", "origin", "condition")}
                cand["img_hash"] = image_dhash(img["src"]) if img["src"] else None
                with connect() as c_:
                    sims = find_similar_items(c_, cand)
                if sims and self._similar_dialog(win, sims, f"{d['part']} — {d['make']} {d['model']}", mode="add", left=self._form_compare_data(d, img["src"])) is None:
                    return
            new_id = None
            try:
                if editing:
                    self._update_item(row["id"], d)
                else:
                    new_id = self._save_item(d)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            win.destroy()
            if on_saved and new_id:
                on_saved(new_id)
                return
            if not editing:
                messagebox.showinfo("تم", "تمت إضافة الصنف بنجاح")
            self.inventory()

        ttk.Button(bar, text="💾  حفظ الصنف", style="Accent.TButton", command=save).pack(ipadx=30, ipady=3)
        self.dialog_size(win, frame, bar, 620)

    def add_item(self):
        if not self.can("inv_add"):
            return
        self.item_dialog()

    def _save_item(self, d):
        if not d["part"].strip() or not d["qty"].strip():
            raise ValueError("تحقق من رقم القطعة والكمية")
        if not d["make"] or not d["model"]:
            raise ValueError("اختر الشركة والموديل من القائمة")
        if not d["category"]:
            raise ValueError("اختر نوع القطعة")
        qty = int(num(d["qty"]))
        if qty < 0:
            raise ValueError("الكمية لا يمكن أن تكون سالبة")
        state = "USED" if d["condition"].strip().upper() in ("USED", "مستعمل") else "NEW"
        car = f"{d['make']} {d['model']}"
        privileged = self.can("view_cost")
        if privileged:
            buy = num(d["buy"])
            profit = num(d["profit"])
            expense = round(buy * num(d["expense"]) / 100.0, 4)  # المصاريف تُدخل كنسبة % من سعر الشراء
        else:
            buy = expense = profit = 0
        incomplete = 0 if (privileged and buy > 0) else 1
        with connect() as c:
            item_no = d["item_no"].strip() or next_item_no(c, state)
            if c.execute("SELECT 1 FROM items WHERE item_no=?", (item_no,)).fetchone():
                raise ValueError("رقم الصنف موجود مسبقًا")
            duplicate = c.execute(
                "SELECT item_no,condition FROM items WHERE part=? AND UPPER(COALESCE(condition,'NEW'))=? LIMIT 1",
                (d["part"].strip(), state)
            ).fetchone()
            if duplicate:
                raise ValueError(f"رقم القطعة موجود مسبقًا بنفس الحالة. رقم الصنف: {duplicate['item_no']}")
            image_name = store_image(d.get("image_src"))
            cur = c.execute("""
                INSERT INTO items(item_no,part,car,make,model,y1,y2,category,kind,supplier,rep_name,rep_code,qty,buy,expense,profit,retail,location,condition,notes,incomplete,image)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                item_no, d["part"].strip(), car, d["make"], d["model"], d["y1"], d["y2"],
                d["category"], d["kind"], d.get("supplier", ""), d.get("rep_name", ""), d.get("rep_code", ""), qty, buy, expense,
                profit, num(d["retail"]), d["location"], state, d["notes"], incomplete, image_name
            ))
            c.execute("UPDATE items SET origin=? WHERE id=?", (d.get("origin", ""), cur.lastrowid))
            if d.get("min_qty") is not None:
                mq = str(d["min_qty"]).strip()
                c.execute("UPDATE items SET min_qty=? WHERE id=?", (None if mq == "" else max(0, int(num(mq))), cur.lastrowid))
            return cur.lastrowid

    def edit_item(self, table):
        if not self.can("inv_edit"):
            return
        selected = table.selection()
        if not selected:
            messagebox.showwarning("تنبيه", "حدد الصنف أولًا")
            return
        item_id = int(selected[0])  # iid = معرّف الصنف
        with connect() as c:
            r = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not r:
            return
        self.item_dialog(r)

    def _update_item(self, item_id, d):
        if not d["part"].strip():
            raise ValueError("رقم القطعة مطلوب")
        if not d["category"]:
            raise ValueError("اختر نوع القطعة")
        qty = int(num(d["qty"]))
        if qty < 0:
            raise ValueError("الكمية لا يمكن أن تكون سالبة")
        state = "USED" if d["condition"].strip().upper() in ("USED", "مستعمل") else "NEW"

        if d["make"] and d["model"]:
            make, model, car = d["make"], d["model"], f"{d['make']} {d['model']}"
        elif d["make"] or d["model"]:
            raise ValueError("اختر الشركة والموديل معًا")
        elif d.get("legacy_car"):
            make, model, car = "", "", d["legacy_car"]  # صنف قديم لم يتغير
        else:
            raise ValueError("اختر الشركة والموديل من القائمة")

        with connect() as c:
            item_no = d["item_no"].strip() or next_item_no(c, state)
            if c.execute("SELECT 1 FROM items WHERE item_no=? AND id<>?", (item_no, item_id)).fetchone():
                raise ValueError("رقم الصنف موجود مسبقًا")
            if c.execute("SELECT 1 FROM items WHERE part=? AND UPPER(COALESCE(condition,'NEW'))=? AND id<>?", (d["part"].strip(), state, item_id)).fetchone():
                raise ValueError("رقم القطعة موجود مسبقًا لصنف بنفس الحالة")
            base = (item_no, d["part"].strip(), car, make, model, d["y1"], d["y2"], d["category"], d["kind"],
                    d.get("rep_name", ""), d.get("rep_code", ""),
                    qty, num(d["retail"]), d["location"], state, d["notes"])
            if self.can("view_cost"):
                buy = num(d["buy"])
                c.execute("""
                    UPDATE items SET item_no=?,part=?,car=?,make=?,model=?,y1=?,y2=?,category=?,kind=?,rep_name=?,rep_code=?,qty=?,retail=?,location=?,condition=?,notes=?,
                    buy=?,expense=?,profit=?,incomplete=?
                    WHERE id=?
                """, base + (buy, round(buy * num(d["expense"]) / 100.0, 4), num(d["profit"]), 0 if buy > 0 else 1, item_id))
            else:
                c.execute("""
                    UPDATE items SET item_no=?,part=?,car=?,make=?,model=?,y1=?,y2=?,category=?,kind=?,rep_name=?,rep_code=?,qty=?,retail=?,location=?,condition=?,notes=?
                    WHERE id=?
                """, base + (item_id,))
            c.execute("UPDATE items SET origin=? WHERE id=?", (d.get("origin", ""), item_id))
            if d.get("min_qty") is not None:
                mq = str(d["min_qty"]).strip()
                c.execute("UPDATE items SET min_qty=? WHERE id=?", (None if mq == "" else max(0, int(num(mq))), item_id))
            old_img = c.execute("SELECT image FROM items WHERE id=?", (item_id,)).fetchone()["image"]
            if d.get("image_src"):
                c.execute("UPDATE items SET image=? WHERE id=?", (store_image(d["image_src"]), item_id))
                delete_image(old_img)
            elif d.get("image_remove") and old_img:
                c.execute("UPDATE items SET image='' WHERE id=?", (item_id,))
                delete_image(old_img)

    def print_barcode(self, table):
        """طباعة الباركود من المخزون: حدد صنفًا أو أكثر، واكتب عدد الملصقات لكل صنف."""
        selected = table.selection()
        if not selected:
            messagebox.showwarning("تنبيه", "حدد صنفًا أو أكثر أولًا (اضغط Ctrl للتحديد المتعدد)")
            return
        none_opt = "(بدون رمز مورد)"
        items = []
        with connect() as c:
            for iid in selected:
                r = c.execute("SELECT id,item_no,part,supplier,qty,category,make,model,car,kind,origin,retail FROM items WHERE id=?", (int(iid),)).fetchone()
                if not r:
                    continue
                names = [x["supplier"] for x in c.execute("SELECT DISTINCT supplier FROM purchases WHERE item_id=? AND COALESCE(supplier,'')<>''", (r["id"],)).fetchall()]
                names += [x["supplier"] for x in c.execute("SELECT supplier FROM item_supplier_codes WHERE item_id=?", (r["id"],)).fetchall() if x["supplier"] and x["supplier"] not in names]
                if r["supplier"] and r["supplier"] not in names:
                    names.append(r["supplier"])
                items.append((r, names))
        if not items:
            return
        win = tk.Toplevel(self)
        win.title("🖨 طباعة الباركود")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        frame = self.scroll_area(win)
        frame.columnconfigure(2, weight=1)
        ttk.Label(frame, text="اكتب عدد الملصقات لكل صنف (0 = لا تطبع هذا الصنف)", style="Sub.TLabel").grid(row=0, column=0, columnspan=3, sticky="e", pady=(0, 8))
        for col, txt in ((2, "الصنف (النوع + الشركة + الموديل + المفتاح + الأصل)"), (1, "مورد الملصق"), (0, "العدد")):
            ttk.Label(frame, text=txt, font=(FONT, 10, "bold")).grid(row=1, column=col, sticky="e", padx=6, pady=(0, 4))
        rows = []
        for i, (r, names) in enumerate(items, start=2):
            ttk.Label(frame, text=f"{r['item_no']}  |  {barcode_label_name(r) or r['part']}  |  متوفر {r['qty'] or 0}", anchor="e", justify="right").grid(row=i, column=2, sticky="e", padx=6, pady=4)
            cb = ttk.Combobox(frame, values=(names + [none_opt]) if names else [none_opt], state="readonly" if names else "disabled", width=22)
            cb.set(r["supplier"] if r["supplier"] in names else (names[0] if names else none_opt))
            cb.grid(row=i, column=1, padx=6)
            sp = ttk.Spinbox(frame, from_=0, to=500, width=6, justify="center")
            sp.set(1)
            sp.grid(row=i, column=0, padx=6)
            rows.append((r, cb, sp))

        def fill(mode):
            for r, _cb, sp in rows:
                sp.set(max(1, int(r["qty"] or 0)) if mode == "qty" else 1)

        def do_print():
            entries, total = [], 0
            with connect() as c:
                for r, cb, sp in rows:
                    n = max(0, min(int(num(sp.get())), 500))
                    if n <= 0:
                        continue
                    sup = cb.get()
                    code = ""
                    if sup and sup != none_opt:
                        sc = c.execute("SELECT code FROM suppliers WHERE name=?", (sup,)).fetchone()
                        code = (sc["code"] if sc else "") or ""
                    entries.append((r["item_no"], barcode_label_name(r) or r["part"], n, code, r["part"] or "", r["retail"]))
                    total += n
            if not entries:
                messagebox.showwarning("تنبيه", "اكتب عددًا أكبر من صفر لصنف واحد على الأقل", parent=win)
                return
            if total > 300 and not messagebox.askyesno("تأكيد", f"سيتم طباعة {total} ملصق. متابعة؟", parent=win):
                return
            win.destroy()
            self._print_labels(entries)

        ttk.Button(bar, text="🖨  طباعة", style="Success.TButton", command=do_print).pack(side="right", padx=6, ipadx=20, ipady=3)
        ttk.Button(bar, text="العدد = الكمية المتوفرة", command=lambda: fill("qty")).pack(side="left", padx=4)
        ttk.Button(bar, text="العدد = 1", command=lambda: fill("one")).pack(side="left", padx=4)
        self.dialog_size(win, frame, bar, 900)

    def _print_labels(self, entries):
        path = os.path.join(tempfile.gettempdir(), "alabbad_barcode.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(make_labels_html(entries))
        webbrowser.open(Path(path).as_uri())

    def choose_from(self, title, text, options):
        """نافذة صغيرة لاختيار خيار من قائمة؛ ترجع الخيار أو None."""
        result = {"v": None}
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        fr = ttk.Frame(dlg, padding=16)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=text).pack(anchor="e", pady=(0, 8))
        cb = ttk.Combobox(fr, values=options, state="readonly", width=40, justify="right")
        cb.current(0)
        cb.pack(pady=6)

        def ok():
            result["v"] = cb.get()
            dlg.destroy()

        ttk.Button(fr, text="موافق", style="Accent.TButton", command=ok).pack(pady=10)
        self.autosize(dlg, fr, 460)
        dlg.wait_window()
        return result["v"]

    def pick_item(self, parent, title="اختر الصنف", initial=""):
        """نافذة بحث لاختيار صنف موجود؛ ترجع رقم الصنف أو None."""
        result = {"id": None}
        dlg = tk.Toplevel(parent)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.transient(parent)
        dlg.grab_set()
        self.center(dlg, 820, 540)
        fr = ttk.Frame(dlg, padding=12)
        fr.pack(fill="both", expand=True)
        top = ttk.Frame(fr)
        top.pack(fill="x")
        ttk.Label(top, text="بحث (رقم الصنف / القطعة / السيارة / رمز المورد)").pack(side="right", padx=4)
        q = ttk.Entry(top, width=30, justify="right")
        q.pack(side="right", padx=4)
        q.insert(0, initial)
        t = make_tree(fr, ("item_no", "name", "part", "qty"), {"item_no": "رقم الصنف", "name": "الاسم", "part": "رقم القطعة", "qty": "المتوفر"},
                      {"name": 360}, height=10)

        def load(*_):
            term = "%" + q.get().strip() + "%"
            with connect() as c:
                rows = c.execute("""SELECT * FROM items WHERE item_no LIKE ? OR part LIKE ? OR car LIKE ? OR COALESCE(rep_code,'') LIKE ?
                                    ORDER BY item_no LIMIT 200""", (term, term, term, term)).fetchall()
            clear_tree(t)
            for r in rows:
                add_row(t, (r["item_no"], item_display_name(r), r["part"], r["qty"] or 0), iid=str(r["id"]))

        def ok(*_):
            sel = t.selection()
            if sel:
                result["id"] = int(sel[0])
                dlg.destroy()

        ttk.Button(fr, text="اختيار", style="Accent.TButton", command=ok).pack(pady=8)
        t.bind("<Double-1>", ok)
        q.bind("<KeyRelease>", load)
        load()
        dlg.wait_window()
        return result["id"]

    def _supplier_code(self, item_id, supplier):
        """رقم المنتج عند هذا المورد: من جدول الربط، وإلا الرمز العام للصنف."""
        with connect() as c:
            m = c.execute("SELECT code FROM item_supplier_codes WHERE item_id=? AND supplier=?", (item_id, supplier)).fetchone()
            if m and m["code"]:
                return m["code"]
            r = c.execute("SELECT rep_code FROM items WHERE id=?", (item_id,)).fetchone()
        return (r["rep_code"] if r else "") or ""

    def _save_supplier_code(self, c, item_id, supplier, code):
        code = clean_name(code)
        if not code or not supplier:
            return
        c.execute("""INSERT INTO item_supplier_codes(item_id,supplier,code) VALUES(?,?,?)
                     ON CONFLICT(item_id,supplier) DO UPDATE SET code=excluded.code""", (item_id, supplier, code))

    def _match_supplier_line(self, c, supplier, code):
        code = (code or "").strip().upper()
        if not code:
            return None
        if supplier:
            r = c.execute("SELECT item_id FROM item_supplier_codes WHERE supplier=? AND UPPER(code)=?", (supplier, code)).fetchone()
            if r:
                return r["item_id"]
        r = c.execute("SELECT id FROM items WHERE UPPER(COALESCE(rep_code,''))=? OR UPPER(COALESCE(part,''))=? OR UPPER(COALESCE(item_no,''))=? ORDER BY id LIMIT 1",
                      (code, code, code)).fetchone()
        if r:
            return r["id"]
        r = c.execute("SELECT item_id FROM item_aliases WHERE UPPER(code)=? ORDER BY (supplier=?) DESC LIMIT 1", (code, supplier or "")).fetchone()
        return r["item_id"] if r else None

    # --------------------------------------------------------------- المبيعات
    def sales(self):
        if not self.can("sales"):
            return
        self.clear("sales")
        self.page_title("المبيعات", "الفواتير الصادرة" + ("" if self.can("sales_all") else " (فواتيرك فقط)"))
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="بحث برقم الفاتورة أو اسم العميل أو رقم الجوال").pack(side="right", padx=4)
        q = ttk.Entry(row, width=28, justify="right")
        q.pack(side="right")
        ttk.Button(row, text="＋ فاتورة جديدة", style="Accent.TButton", command=self.new_sale).pack(side="left", padx=4)
        cols = ("id", "invoice", "date", "customer", "phone", "type", "total", "paid", "remaining")
        heads = {"id": "رقم", "invoice": "رقم الفاتورة", "date": "التاريخ", "customer": "العميل", "phone": "الجوال", "type": "الدفع", "total": "الإجمالي", "paid": "المدفوع", "remaining": "المتبقي"}
        t = make_tree(self.body, cols, heads, {"id": 60, "invoice": 150, "date": 150})
        if self.can("whatsapp"):
            ttk.Button(row, text="إرسال واتساب", command=lambda: self._wa_selected(t)).pack(side="left", padx=4)
        own = "" if self.can("sales_all") else self.user

        def load():
            term = "%" + q.get().strip() + "%"
            with connect() as c:
                rows = c.execute("""
                    SELECT invoice,MIN(id) id,MAX(date) date,MAX(customer) customer,
                    MAX(customer_phone) phone,MAX(payment_type) ptype,SUM(price*qty) total,COALESCE(SUM(paid),0) paid,
                    SUM(price*qty)-COALESCE(SUM(paid),0) remaining
                    FROM sales
                    WHERE (CAST(invoice AS TEXT) LIKE ? OR customer LIKE ? OR customer_phone LIKE ?)
                    AND (?='' OR seller=?)
                    GROUP BY invoice ORDER BY MIN(id) DESC
                """, (term, term, term, own, own)).fetchall()
            clear_tree(t)
            for r in rows:
                add_row(t, (r["id"], r["invoice"], r["date"], r["customer"], r["phone"], r["ptype"] or "", sar(r["total"]), sar(r["paid"]), sar(r["remaining"])), iid=str(r["invoice"]))

        ttk.Button(row, text="🔍 بحث", command=load).pack(side="left")
        q.bind("<Return>", lambda e: load())
        t.bind("<Double-1>", lambda e: self.show_invoice(t))
        load()

    def _wa_selected(self, table):
        sel = table.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "حدد الفاتورة أولًا")
            return
        self.send_invoice_whatsapp(sel[0])

    # ------------------------------------------------------------- واتساب
    def invoice_text(self, invoice_no):
        with connect() as c:
            rows = c.execute("""
                SELECT s.*,i.item_no,i.part,i.car
                FROM sales s LEFT JOIN items i ON i.id=s.item_id
                WHERE s.invoice=? ORDER BY s.id
            """, (invoice_no,)).fetchall()
        if not rows:
            return "", ""
        total = sum(r["qty"] * r["price"] for r in rows)
        paid = sum(num(r["paid"]) for r in rows)
        first = rows[0]
        ptype = first["payment_type"] or "كاش"
        date_txt = str(first["date"] or "")[:16]
        RLM = "\u200f"  # علامة اتجاه لليمين: تمنع اختلاط الأسطر العربية مع الأرقام
        sep = "━━━━━━━━━━━━━━"
        out = []

        def add(text=""):
            out.append(RLM + text if text else "")

        add("*🔑 العباد للمفاتيح*")
        add(sep)
        add(f"🧾 رقم الفاتورة: {invoice_no}")
        add(f"📅 التاريخ: {date_txt}")
        if first["customer"] and first["customer"] != "عميل نقدي":
            add(f"👤 العميل: {first['customer']}")
        add(sep)
        add("*الأصناف*")
        add()
        entries, seen = [], {}
        for r in rows:
            g = r["bundle_group"]
            if g:
                if g in seen:
                    seen[g]["total"] += r["qty"] * r["price"]
                    continue
                e_ = {"bundle": True, "name": r["bundle_name"], "qty": r["bundle_qty"] or 1, "total": r["qty"] * r["price"]}
                seen[g] = e_
                entries.append(e_)
            else:
                entries.append({"bundle": False, "r": r})
        for i, e_ in enumerate(entries, start=1):
            add(f"🔹 الصنف رقم {i}")
            if e_["bundle"]:
                add(f"   المنتج: 🎁 {e_['name']}")
                add(f"   الكمية: {e_['qty']}")
                add(f"   سعر الوحدة: {sar(e_['total'] / e_['qty'])}")
                add(f"   الإجمالي: {sar(e_['total'])}")
            else:
                r = e_["r"]
                add(f"   رقم القطعة: {r['part'] or '-'}")
                if r["car"]:
                    add(f"   السيارة: {r['car']}")
                add(f"   الكمية: {r['qty']}")
                add(f"   سعر الوحدة: {sar(r['price'])}")
                add(f"   الإجمالي: {sar(r['qty'] * r['price'])}")
            add()
        add(sep)
        add(f"💰 *الإجمالي: {sar(total)}*")
        add(f"💳 طريقة الدفع: {ptype}")
        add(f"✅ المدفوع: {sar(paid)}")
        if total - paid > 0.001:
            add(f"⏳ المتبقي: {sar(total - paid)}")
        add(sep)
        add("شكرًا لتعاملكم معنا 🙏")
        return "\n".join(out), (first["customer_phone"] or "")

    def send_invoice_whatsapp(self, invoice_no, parent=None):
        if not self.can("whatsapp"):
            return
        text, phone = self.invoice_text(invoice_no)
        if not text:
            messagebox.showwarning("تنبيه", "الفاتورة غير موجودة", parent=parent or self)
            return
        if not phone:
            phone = simpledialog.askstring("واتساب", "رقم جوال العميل:", parent=parent or self) or ""
        phone = normalize_phone(phone)
        if len(phone) < 9:
            messagebox.showwarning("تنبيه", "رقم الجوال غير صحيح", parent=parent or self)
            return
        webbrowser.open("https://wa.me/" + phone + "?text=" + urllib.parse.quote(text))

    # ------------------------------------------------------------- فاتورة جديدة
    def new_sale(self):
        if not self.can("sales"):
            return
        self.clear("sales")
        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Button(head, text="← رجوع", command=self.sales).pack(side="left")
        ttk.Label(head, text="فاتورة بيع جديدة", style="Title.TLabel").pack(side="right")
        # شريط سفلي ثابت (الإجمالي + الدفع + زر الإصدار) يبقى ظاهرًا دائمًا مهما صغرت الشاشة
        bottom = ttk.Frame(self.body)
        bottom.pack(side="bottom", fill="x")

        customer_frame = ttk.LabelFrame(self.body, text="بيانات العميل", padding=8)
        customer_frame.pack(fill="x", pady=5)
        ttk.Label(customer_frame, text="اسم العميل").grid(row=0, column=3, padx=4)
        customer = ttk.Entry(customer_frame, width=24, justify="right")
        customer.grid(row=0, column=2, padx=4)
        ttk.Label(customer_frame, text="رقم الجوال").grid(row=0, column=1, padx=4)
        phone = ttk.Entry(customer_frame, width=18, justify="right")
        phone.grid(row=0, column=0, padx=4)

        # اقتراحات العملاء: اكتب جزءًا من الاسم أو الرقم فتظهر الخيارات من قاعدة البيانات
        sug = tk.Listbox(customer_frame, height=5, font=(FONT, 10), activestyle="dotbox", exportselection=False)
        sug.grid(row=1, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 0))
        sug.grid_remove()
        sug_rows = []

        def hide_sug(_e=None):
            sug.grid_remove()

        def show_sug(e=None):
            if e is not None and getattr(e, "keysym", "") in ("Down", "Up", "Return", "Escape", "Tab"):
                return
            w = e.widget if e is not None else customer
            with connect() as c_:
                rows_ = customer_suggestions(c_, w.get())
            sug_rows[:] = rows_
            sug.delete(0, "end")
            if not rows_:
                sug.grid_remove()
                return
            for r_ in rows_:
                debt_txt = f"   |   عليه {sar(r_['debt'])}" if (r_["debt"] or 0) > 0.005 else ""
                sug.insert("end", f"{r_['name']}   |   {r_['phone'] or 'بدون جوال'}{debt_txt}")
            sug.grid()

        def pick_sug(_e=None):
            sel = sug.curselection()
            if not sel:
                return
            r_ = sug_rows[sel[0]]
            customer.delete(0, "end")
            customer.insert(0, r_["name"])
            phone.delete(0, "end")
            phone.insert(0, r_["phone"] or "")
            sug.grid_remove()
            item_sel.focus_set()

        def to_list(_e=None):
            if sug.winfo_ismapped() and sug.size():
                sug.focus_set()
                sug.selection_clear(0, "end")
                sug.selection_set(0)
                sug.activate(0)
                return "break"

        for ent_ in (customer, phone):
            ent_.bind("<KeyRelease>", show_sug)
            ent_.bind("<Down>", to_list)
            ent_.bind("<Escape>", hide_sug)
        sug.bind("<ButtonRelease-1>", pick_sug)
        sug.bind("<Return>", pick_sug)
        sug.bind("<Escape>", hide_sug)

        item_frame = ttk.LabelFrame(self.body, text="إضافة الأصناف", padding=8)
        item_frame.pack(fill="x", pady=5)
        with connect() as c:
            items = c.execute("SELECT id,item_no,part,car,qty,retail,buy,expense,profit,condition,origin FROM items WHERE qty>0 ORDER BY item_no").fetchall()
        item_map = {}
        options = []
        for r in items:
            label = f"{r['item_no']} | {r['part']} | {r['car']} | {'مستعمل' if r['condition'] == 'USED' else 'جديد'}{(' | ' + r['origin']) if r['origin'] else ''} | المتوفر {r['qty']}"
            options.append(label)
            item_map[label] = r
        with connect() as c:  # المنتجات المركّبة تظهر في نفس القائمة
            for b in c.execute("SELECT * FROM bundles WHERE COALESCE(active,1)=1 ORDER BY code").fetchall():
                comps = bundle_components(c, b["id"])
                avail = bundle_available(comps)
                if avail <= 0:
                    continue
                label = f"{b['code']} | 🎁 {b['name']} | مركّب | المتوفر {avail}"
                options.append(label)
                item_map[label] = {"id": f"B{b['id']}", "bundle_id": b["id"], "item_no": b["code"], "part": b["name"], "car": "منتج مركّب",
                                   "qty": avail, "retail": num(b["retail"]),
                                   "buy": sum(num(x["buy"]) * x["comp_qty"] for x in comps),
                                   "expense": sum(num(x["expense"]) * x["comp_qty"] for x in comps),
                                   "profit": 0, "condition": "NEW", "origin": "", "w_min": bundle_wholesale(comps)}
        ttk.Label(item_frame, text="الصنف").grid(row=0, column=5, padx=4)
        item_sel = ttk.Combobox(item_frame, values=options, width=46, state="readonly")
        item_sel.grid(row=0, column=4, padx=4)
        ttk.Label(item_frame, text="الكمية").grid(row=0, column=3, padx=4)
        qty = ttk.Entry(item_frame, width=8, justify="right")
        qty.insert(0, "1")
        qty.grid(row=0, column=2, padx=4)
        ttk.Label(item_frame, text="نوع البيع").grid(row=0, column=1, padx=4)
        kinds = ["مفرد", "جملة"] if self.can("sell_wholesale") else ["مفرد"]
        kind = ttk.Combobox(item_frame, values=kinds, state="readonly", width=10)
        kind.set("مفرد")
        kind.grid(row=0, column=0, padx=4)
        ttk.Label(item_frame, text="سعر الوحدة").grid(row=1, column=5, padx=4, pady=4)
        price = ttk.Entry(item_frame, width=12, justify="right")
        price.grid(row=1, column=4, padx=4)
        ttk.Label(item_frame, text="باركود").grid(row=1, column=3, padx=4)
        scan_e = ttk.Entry(item_frame, width=22, justify="right")
        scan_e.grid(row=1, column=2, padx=4)

        def scan(_e=None):
            bm = parse_barcode(scan_e.get())
            code = bm[0] if bm else scan_e.get().strip().upper()
            with connect() as c_:
                al_ = c_.execute("SELECT i.item_no FROM item_aliases a JOIN items i ON i.id=a.item_id WHERE UPPER(a.code)=? LIMIT 1", (code,)).fetchone()
            for want in [code] + ([(al_["item_no"] or "").upper()] if al_ else []):
                for label, r_ in item_map.items():
                    if (r_["item_no"] or "").upper() == want:
                        item_sel.set(label)
                        select_item()
                        scan_e.delete(0, "end")
                        qty.focus_set()
                        return
            messagebox.showwarning("تنبيه", "الباركود غير موجود، أو الصنف نافد من المخزون")

        scan_e.bind("<Return>", scan)

        invoice_items = []
        invoice_frame = ttk.LabelFrame(self.body, text="أصناف الفاتورة", padding=8)
        invoice_frame.pack(fill="both", expand=True, pady=5)
        cols = ("item_no", "part", "condition", "qty", "kind", "price", "total")
        heads = {"item_no": "رقم الصنف", "part": "رقم القطعة", "condition": "الحالة", "qty": "الكمية", "kind": "نوع البيع", "price": "سعر الوحدة", "total": "الإجمالي"}
        tree = make_tree(invoice_frame, cols, heads, height=4)
        total_var = tk.StringVar(value="الإجمالي: 0.00 ر.س")
        ttk.Label(bottom, textvariable=total_var, font=(FONT, 15, "bold"), foreground=NAVY).pack(anchor="e", pady=2)

        pay_type = tk.StringVar(value="كاش")

        def invoice_total():
            return sum(x["qty"] * x["price"] for x in invoice_items)

        def refresh_paid():
            # في الكاش: المدفوع = الإجمالي دائمًا ولا يُعدّل
            if pay_type.get() == "كاش":
                paid.configure(state="normal")
                paid.delete(0, "end")
                paid.insert(0, f"{invoice_total():.2f}")
                paid.configure(state="disabled")

        def on_pay_change():
            if pay_type.get() == "دين":
                paid.configure(state="normal")
                paid.delete(0, "end")
                paid.insert(0, "0")
            else:
                refresh_paid()

        def update_total():
            total_var.set("الإجمالي: " + sar(invoice_total()))
            refresh_paid()

        def min_price_of(r, k):
            if isinstance(r, dict) and r.get("bundle_id"):
                return num(r["w_min"]) if k == "جملة" else num(r["retail"])
            return wholesale_price(r["buy"], r["expense"], r["profit"]) if k == "جملة" else num(r["retail"])

        def select_item(*_):
            r = item_map.get(item_sel.get())
            if not r:
                return
            price.delete(0, "end")
            price.insert(0, str(min_price_of(r, kind.get())))

        item_sel.bind("<<ComboboxSelected>>", select_item)
        kind.bind("<<ComboboxSelected>>", select_item)

        def add_line():
            r = item_map.get(item_sel.get())
            if not r:
                messagebox.showwarning("تنبيه", "اختر الصنف أولًا")
                return
            qn = int(num(qty.get()))
            pn = num(price.get())
            if qn <= 0:
                messagebox.showwarning("تنبيه", "الكمية يجب أن تكون أكبر من صفر")
                return
            already = sum(x["qty"] for x in invoice_items if x["item"]["id"] == r["id"])
            if already + qn > int(r["qty"]):
                messagebox.showwarning("تنبيه", "الكمية المطلوبة أكبر من المتوفر")
                return
            if pn <= 0:
                messagebox.showwarning("تنبيه", "أدخل سعرًا صحيحًا")
                return
            if pn < min_price_of(r, kind.get()) and not self.can("below_price"):
                messagebox.showwarning("السعر منخفض", "السعر أقل من الحد المسموح. اطلب موافقة المدير.")
                return
            invoice_items.append({"item": r, "qty": qn, "price": pn, "kind": kind.get()})
            add_row(tree, (r["item_no"], r["part"], ("مركّب" if (isinstance(r, dict) and r.get("bundle_id")) else ("مستعمل" if r["condition"] == "USED" else "جديد")), qn, kind.get(), sar(pn), sar(qn * pn)))
            sug.grid_remove()
            update_total()

        def remove_line():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد السطر المراد حذفه")
                return
            idx = tree.index(sel[0])
            tree.delete(sel[0])
            invoice_items.pop(idx)
            update_total()

        ttk.Button(item_frame, text="＋ إضافة للفاتورة", style="Accent.TButton", command=add_line).grid(row=1, column=0, padx=4)
        ttk.Button(item_frame, text="حذف السطر المحدد", command=remove_line).grid(row=1, column=1, padx=4)

        payment_frame = ttk.LabelFrame(bottom, text="الدفع", padding=8)
        payment_frame.pack(fill="x", pady=4)
        ttk.Label(payment_frame, text="طريقة الدفع").grid(row=0, column=5, padx=4)
        ttk.Radiobutton(payment_frame, text="كاش", variable=pay_type, value="كاش", command=on_pay_change).grid(row=0, column=4, padx=4)
        ttk.Radiobutton(payment_frame, text="دين", variable=pay_type, value="دين", command=on_pay_change).grid(row=0, column=3, padx=4)
        ttk.Label(payment_frame, text="المدفوع الآن").grid(row=0, column=2, padx=4)
        paid = ttk.Entry(payment_frame, width=14, justify="right")
        paid.grid(row=0, column=1, padx=4)
        ttk.Label(payment_frame, text="(في الدين: اكتب المدفوع إن وُجد، أو اتركه 0)", style="Muted.TLabel").grid(row=0, column=0, padx=4)
        on_pay_change()

        def save_invoice():
            if not invoice_items:
                messagebox.showwarning("تنبيه", "أضف صنفًا واحدًا على الأقل")
                return
            customer_name = customer.get().strip()
            customer_phone = normalize_phone(phone.get())
            if customer_phone and len(customer_phone) < 9:
                messagebox.showwarning("تنبيه", "رقم الجوال غير صحيح")
                return
            total = invoice_total()
            ptype = pay_type.get()

            if ptype == "كاش":
                paid_now = total
            else:
                paid_now = num(paid.get())
                if not (customer_name or customer_phone):
                    messagebox.showwarning("تنبيه", "فاتورة الدين تحتاج اسم العميل أو رقم جواله")
                    return
                if paid_now < 0 or paid_now >= total - 0.001:
                    messagebox.showwarning("تنبيه", "في الدين لازم يكون المدفوع أقل من إجمالي الفاتورة. إذا دفع كامل المبلغ اختر كاش")
                    return

            for x in invoice_items:
                r = x["item"]
                mp = min_price_of(r, x["kind"])
                if x["price"] < mp:
                    if not self.can("below_price"):
                        messagebox.showwarning("السعر منخفض", "لا يمكن إصدار الفاتورة بسعر أقل من الحد المسموح. الفاتورة ما زالت مفتوحة.")
                        return
                    if not messagebox.askyesno("تأكيد السعر", f"السعر {sar(x['price'])} أقل من الحد {sar(mp)}. هل تريد المتابعة؟"):
                        return
            if not messagebox.askyesno("تأكيد الفاتورة", f"طريقة الدفع: {ptype}\nإجمالي الفاتورة: {sar(total)}\nالمدفوع: {sar(paid_now)}\nالمتبقي: {sar(total - paid_now)}\nهل تريد إصدار الفاتورة؟"):
                return
            invoice_no = datetime.now().strftime("INV%y%m%d%H%M%S")
            with connect() as c:
                cust = None
                if customer_phone:
                    cust = c.execute("SELECT id FROM customers WHERE phone=?", (customer_phone,)).fetchone()
                if not cust and customer_name:
                    cust = c.execute("SELECT id FROM customers WHERE name=? COLLATE NOCASE ORDER BY id LIMIT 1", (customer_name,)).fetchone()
                if not cust and (customer_name or customer_phone):
                    cur = c.execute("INSERT INTO customers(name,phone,created_at) VALUES(?,?,?)", (customer_name or "عميل نقدي", customer_phone, now_str()))
                    customer_id = cur.lastrowid
                else:
                    customer_id = cust["id"] if cust else None
                    if cust and customer_phone:
                        c.execute("UPDATE customers SET phone=? WHERE id=? AND (phone IS NULL OR phone='')", (customer_phone, customer_id))
                rows_out = expand_invoice_lines(c, invoice_items, invoice_no)
                remaining_paid = paid_now
                for ro in rows_out:
                    line_total = ro["qty"] * ro["price"]
                    if ptype == "كاش":
                        line_paid = line_total
                    else:
                        line_paid = min(line_total, remaining_paid)
                        remaining_paid -= line_paid
                    c.execute("""
                        INSERT INTO sales(invoice,date,customer,item_id,qty,price,kind,paid,approved_by,seller,customer_phone,customer_id,payment_type,bundle_name,bundle_qty,bundle_group)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        invoice_no, now_str(),
                        customer_name or "عميل نقدي", ro["item_id"], ro["qty"], ro["price"], ro["kind"],
                        line_paid, self.user if self.role == "admin" else "", self.user,
                        customer_phone, customer_id, ptype,
                        ro["bundle_name"], ro["bundle_qty"], ro["bundle_group"]
                    ))
                    c.execute("UPDATE items SET qty=qty-? WHERE id=?", (ro["qty"], ro["item_id"]))

            if self.can("whatsapp") and messagebox.askyesno("واتساب", f"تم إصدار الفاتورة رقم {invoice_no}\n\nهل تريد إرسالها للعميل عبر واتساب؟"):
                self.send_invoice_whatsapp(invoice_no)
            elif not self.can("whatsapp"):
                messagebox.showinfo("تم", f"تم إصدار الفاتورة رقم {invoice_no}")
            self.check_stock_alerts()
            self.sales()

        ttk.Button(bottom, text="✔ إصدار الفاتورة", style="Success.TButton", command=lambda: try_save(save_invoice)).pack(pady=6, ipadx=30, ipady=4)

    def show_invoice(self, table):
        selected = table.selection()
        if not selected:
            return
        invoice_no = table.item(selected[0], "values")[1]
        with connect() as c:
            rows = c.execute("""
                SELECT s.*,i.item_no,i.part,i.car,i.condition
                FROM sales s LEFT JOIN items i ON i.id=s.item_id
                WHERE s.invoice=? ORDER BY s.id
            """, (invoice_no,)).fetchall()
        win = tk.Toplevel(self)
        win.title("تفاصيل الفاتورة " + str(invoice_no))
        win.configure(bg=BG)
        win.geometry("880x500")
        ttk.Label(win, text=f"فاتورة رقم {invoice_no}", style="Title.TLabel").pack(pady=8)
        if rows:
            first = rows[0]
            ttk.Label(win, text=f"العميل: {first['customer']}    الجوال: {first['customer_phone'] or ''}    الدفع: {first['payment_type'] or ''}").pack()
        cols = ("item_no", "part", "car", "qty", "kind", "price", "total")
        heads = {"item_no": "رقم الصنف", "part": "رقم القطعة", "car": "السيارة", "qty": "الكمية", "kind": "البيع", "price": "السعر", "total": "الإجمالي"}
        t = make_tree(win, cols, heads)
        total = 0
        paid = sum(num(r["paid"]) for r in rows)
        for r in rows:
            line_total = r["qty"] * r["price"]
            total += line_total
            add_row(t, (r["item_no"], r["part"], (r["car"] or "") + (f"  ← ضمن 🎁 {r['bundle_name']}" if r["bundle_name"] else ""), r["qty"], r["kind"], sar(r["price"]), sar(line_total)))
        ttk.Label(win, text=f"الإجمالي: {sar(total)}    المدفوع: {sar(paid)}    المتبقي: {sar(total - paid)}", font=(FONT, 12, "bold")).pack(pady=4)
        if self.can("whatsapp"):
            ttk.Button(win, text="إرسال واتساب", style="Success.TButton", command=lambda: self.send_invoice_whatsapp(invoice_no, parent=win)).pack(pady=8)

    # ---------------------------------------------------------- العملاء والديون
    def customers(self):
        if not self.can("customers"):
            return
        self.clear("customers")
        self.page_title("العملاء والديون", "متابعة الفواتير والمبالغ المتبقية")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="بحث باسم العميل أو رقم الجوال").pack(side="right", padx=4)
        q = ttk.Entry(row, width=30, justify="right")
        q.pack(side="right")
        cols = ("id", "name", "phone", "invoices", "total", "paid", "later", "remaining", "status")
        heads = {"id": "رقم", "name": "اسم العميل", "phone": "رقم الجوال", "invoices": "عدد الفواتير", "total": "إجمالي الفواتير", "paid": "المدفوع بالفواتير", "later": "تحصيل لاحق", "remaining": "المتبقي عليه", "status": "حالة التحصيل"}
        t = make_tree(self.body, cols, heads, {"id": 60})

        def status(r):
            total = num(r["total"])
            paid = num(r["paid"]) + num(r["later"])
            if total <= 0 or paid >= total - 0.001:
                return "🟢 مكتمل"
            if paid <= 0:
                return "🔴 لم يدفع"
            return "🟠 جزئي"

        def refresh(*_):
            term = "%" + q.get().strip() + "%"
            with connect() as c:
                rows = c.execute("""
                    SELECT cu.id,cu.name,cu.phone,
                    COUNT(DISTINCT s.invoice) invoices,
                    COALESCE(SUM(s.price*s.qty),0) total,
                    COALESCE(SUM(s.paid),0) paid,
                    COALESCE((SELECT SUM(dp.amount) FROM debt_payments dp WHERE dp.customer_id=cu.id),0) later,
                    COALESCE(SUM(s.price*s.qty),0)-COALESCE(SUM(s.paid),0)
                    -COALESCE((SELECT SUM(dp.amount) FROM debt_payments dp WHERE dp.customer_id=cu.id),0) remaining
                    FROM customers cu
                    LEFT JOIN sales s ON s.customer_id=cu.id
                    WHERE cu.name LIKE ? OR cu.phone LIKE ?
                    GROUP BY cu.id ORDER BY remaining DESC
                """, (term, term)).fetchall()
            clear_tree(t)
            for r in rows:
                add_row(t, (r["id"], r["name"], r["phone"], r["invoices"], sar(r["total"]), sar(r["paid"]), sar(r["later"]), sar(max(0, r["remaining"])), status(r)), iid=str(r["id"]))

        def show_customer_invoices():
            selected = t.selection()
            if not selected:
                return
            customer_id = int(selected[0])
            vals = t.item(selected[0], "values")
            with connect() as c:
                rows = c.execute("""
                    SELECT invoice,MIN(date) date,MAX(customer) customer,
                    MAX(customer_phone) phone,SUM(price*qty) total,COALESCE(SUM(paid),0) paid
                    FROM sales WHERE customer_id=? GROUP BY invoice ORDER BY MIN(id) DESC
                """, (customer_id,)).fetchall()
            win = tk.Toplevel(self)
            win.title("فواتير العميل " + str(vals[1]))
            win.configure(bg=BG)
            win.geometry("880x480")
            ttk.Label(win, text=f"فواتير العميل: {vals[1]} — {vals[2]}", style="Title.TLabel").pack(pady=8)
            fcols = ("invoice", "date", "total", "paid", "remaining")
            fheads = {"invoice": "رقم الفاتورة", "date": "التاريخ", "total": "الإجمالي", "paid": "المدفوع", "remaining": "المتبقي"}
            ft = make_tree(win, fcols, fheads, {"invoice": 170, "date": 160})
            for r in rows:
                add_row(ft, (r["invoice"], r["date"], sar(r["total"]), sar(r["paid"]), sar(r["total"] - r["paid"])))

            def invoice_detail(event=None):
                sel = ft.selection()
                if not sel:
                    return
                inv = ft.item(sel[0], "values")[0]
                with connect() as c:
                    items = c.execute("""
                        SELECT s.*,i.item_no,i.part,i.car
                        FROM sales s LEFT JOIN items i ON i.id=s.item_id
                        WHERE s.invoice=? ORDER BY s.id
                    """, (inv,)).fetchall()
                detail = tk.Toplevel(win)
                detail.title("تفاصيل الفاتورة " + str(inv))
                detail.configure(bg=BG)
                detail.geometry("820x440")
                ttk.Label(detail, text=f"فاتورة رقم {inv}", style="Title.TLabel").pack(pady=8)
                cols2 = ("item_no", "part", "car", "qty", "price", "total")
                heads2 = {"item_no": "رقم الصنف", "part": "رقم القطعة", "car": "السيارة", "qty": "الكمية", "price": "سعر الوحدة", "total": "الإجمالي"}
                it = make_tree(detail, cols2, heads2)
                for r in items:
                    add_row(it, (r["item_no"], r["part"], r["car"], r["qty"], sar(r["price"]), sar(r["qty"] * r["price"])))
                if self.can("whatsapp"):
                    ttk.Button(detail, text="إرسال واتساب", style="Success.TButton", command=lambda: self.send_invoice_whatsapp(inv, parent=detail)).pack(pady=6)

            ft.bind("<Double-1>", invoice_detail)

        def add_payment():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد العميل أولًا")
                return
            customer_id = int(sel[0])
            name = t.item(sel[0], "values")[1]
            self.form(f"تسجيل دفعة من {name}", [
                ("amount", "المبلغ المدفوع", "0"),
                ("notes", "ملاحظات", "")
            ], lambda d: self._save_debt_payment(customer_id, d), on_done=refresh)

        ttk.Button(row, text="🔍 بحث", command=refresh).pack(side="left", padx=4)
        if self.can("debt_pay"):
            ttk.Button(row, text="＋ تسجيل دفعة", style="Success.TButton", command=add_payment).pack(side="left", padx=4)
        ttk.Button(row, text="فواتير العميل", command=show_customer_invoices).pack(side="left", padx=4)
        q.bind("<KeyRelease>", refresh)
        q.bind("<Return>", lambda e: refresh())
        t.bind("<Double-1>", lambda e: show_customer_invoices())
        refresh()

    def _save_debt_payment(self, customer_id, d):
        amount = num(d["amount"])
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        with connect() as c:
            debt = c.execute("SELECT COALESCE(SUM(price*qty),0)-COALESCE(SUM(paid),0) FROM sales WHERE customer_id=?", (customer_id,)).fetchone()[0]
            later = c.execute("SELECT COALESCE(SUM(amount),0) FROM debt_payments WHERE customer_id=?", (customer_id,)).fetchone()[0]
            remaining = debt - later
            if amount > remaining + 0.001:
                raise ValueError(f"المبلغ أكبر من المتبقي على العميل ({sar(max(0, remaining))})")
            c.execute("INSERT INTO debt_payments(customer_id,date,amount,notes,seller) VALUES(?,?,?,?,?)",
                      (customer_id, now_str(), amount, d["notes"], self.user))

    # --------------------------------------------------------------- المشتريات
    def purchases(self):
        if not self.can("purchases"):
            return
        self.clear("purchases")
        self.page_title("المشتريات", "فواتير الشراء من الموردين — سجّل الفاتورة، وعند استلام البضاعة أضفها للمخزون")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        frow = ttk.Frame(self.body)
        frow.pack(fill="x")
        with connect() as c:
            type_vals = ["الكل"] + [r["name"] for r in c.execute("SELECT name FROM item_types ORDER BY name").fetchall()]
            sup_vals = ["الكل"] + [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
        ttk.Label(frow, text="نوع القطعة").pack(side="right", padx=4)
        cat_f = ttk.Combobox(frow, values=type_vals, state="readonly", width=16)
        cat_f.set("الكل")
        cat_f.pack(side="right", padx=4)
        ttk.Label(frow, text="المورد").pack(side="right", padx=4)
        sup_f = ttk.Combobox(frow, values=sup_vals, state="readonly", width=20)
        sup_f.set("الكل")
        sup_f.pack(side="right", padx=4)
        ttk.Label(frow, text="الحالة").pack(side="right", padx=4)
        st_f = ttk.Combobox(frow, values=["الكل", "معلّقة (لم تُضف للمخزون)", "مستلمة"], state="readonly", width=24)
        st_f.set("الكل")
        st_f.pack(side="right", padx=4)

        cols = ("id", "batch", "date", "item", "category", "supplier", "qty", "buy", "expense", "landed", "status")
        heads = {"id": "رقم", "batch": "رقم الفاتورة", "date": "التاريخ", "item": "الصنف", "category": "نوع القطعة", "supplier": "المورد", "qty": "الكمية", "buy": "سعر الوحدة", "expense": "المصاريف", "landed": "التكلفة النهائية", "status": "الحالة"}
        t = make_tree(self.body, cols, heads, {"id": 55, "batch": 140, "item": 220, "date": 130, "category": 100, "status": 170})
        t.configure(selectmode="extended")

        def load(*_):
            sql = "SELECT p.*,i.item_no,i.part,i.category FROM purchases p LEFT JOIN items i ON i.id=p.item_id WHERE 1=1"
            params = []
            if cat_f.get() != "الكل":
                sql += " AND i.category=?"
                params.append(cat_f.get())
            if sup_f.get() != "الكل":
                sql += " AND p.supplier=?"
                params.append(sup_f.get())
            if st_f.get().startswith("معلّقة"):
                sql += " AND p.status='pending'"
            elif st_f.get() == "مستلمة":
                sql += " AND COALESCE(p.status,'received')='received'"
            sql += " ORDER BY (p.status='pending') DESC,p.id DESC LIMIT 500"
            with connect() as c:
                rows = c.execute(sql, params).fetchall()
            clear_tree(t)
            for r in rows:
                pending = (r["status"] or "received") == "pending"
                add_row(t, (r["id"], r["batch"], str(r["date"] or "")[:16], f"{r['item_no'] or ''} | {r['part'] or ''}", r["category"] or "", r["supplier"], r["qty"],
                            sar(num(r["buy"])), sar(num(r["expense"])), sar(num(r["landed"])),
                            "⏳ لم تُضف للمخزون" if pending else "✅ أُضيفت للمخزون"),
                        iid=str(r["id"]), extra=("low",) if pending else ())
            self.refresh_badges()

        for w_ in (cat_f, sup_f, st_f):
            w_.bind("<<ComboboxSelected>>", load)

        def receive(ids):
            if not ids:
                messagebox.showwarning("تنبيه", "حدد فاتورة شراء معلّقة أولًا")
                return
            if not messagebox.askyesno("تأكيد", f"سيتم إضافة {len(ids)} سطر إلى المخزون وتحديث التكلفة بالمتوسط المرجّح. متابعة؟"):
                return
            try:
                n, changes = self._receive_purchases(ids)
            except Exception as e:
                messagebox.showerror("خطأ", str(e))
                return
            load()
            msg = f"تمت إضافة {n} سطر للمخزون."
            if changes:
                msg += "\n\nتحديث التكلفة (متوسط مرجّح):\n" + "\n".join(changes[:10]) + ("\n..." if len(changes) > 10 else "")
            messagebox.showinfo("تم", msg)

        def all_pending():
            with connect() as c:
                return [r[0] for r in c.execute("SELECT id FROM purchases WHERE status='pending'").fetchall()]

        def print_selected():
            entries = []
            with connect() as c:
                for iid in t.selection():
                    p_ = c.execute("SELECT p.qty,p.supplier,i.item_no,i.part,i.category,i.make,i.model,i.car,i.kind,i.origin FROM purchases p LEFT JOIN items i ON i.id=p.item_id WHERE p.id=?", (int(iid),)).fetchone()
                    if p_ and p_["item_no"]:
                        sc = c.execute("SELECT code FROM suppliers WHERE name=?", (p_["supplier"],)).fetchone()
                        entries.append((p_["item_no"], barcode_label_name(p_) or p_["part"], max(int(p_["qty"] or 0), 1), (sc["code"] if sc else "") or ""))
            if not entries:
                messagebox.showwarning("تنبيه", "حدد سطرًا أو أكثر من المشتريات أولًا")
                return
            total = sum(e[2] for e in entries)
            if messagebox.askyesno("طباعة الباركود", f"سيتم طباعة {total} ملصق (ملصق لكل قطعة) برمز المورد على الباركود. متابعة؟"):
                self._print_labels(entries)

        def delete_sel():
            ids = self._invoice_pending_ids(t.selection())
            if not ids:
                messagebox.showwarning("تنبيه", "حدد فاتورة شراء معلّقة لحذفها (المضافة للمخزون لا تُحذف)")
                return
            if not messagebox.askyesno("تأكيد", f"حذف {len(ids)} سطر معلّق؟"):
                return
            with connect() as c:
                for i in ids:
                    c.execute("DELETE FROM purchases WHERE id=? AND status='pending'", (i,))
            load()

        ttk.Button(row, text="📄 استيراد فاتورة PDF", style="Accent.TButton", command=lambda: self.import_pdf_invoice(load)).pack(side="right", padx=4)
        if self.role == "admin" or self.can("inv_edit"):
            ttk.Button(row, text="🖼 صور فقط من فاتورة", command=self.import_images_only).pack(side="right", padx=4)
        ttk.Button(row, text="＋ فاتورة شراء جديدة", style="Accent.TButton", command=lambda: self.new_purchase(load)).pack(side="right", padx=4)
        ttk.Button(row, text="🖨 باركود المحدد", command=lambda: print_selected()).pack(side="right", padx=4)
        ttk.Button(row, text="✔ إضافة الفاتورة المحددة للمخزون", style="Success.TButton", command=lambda: receive(self._invoice_pending_ids(t.selection()))).pack(side="right", padx=4)
        ttk.Button(row, text="إضافة كل المعلّقة", command=lambda: receive(all_pending())).pack(side="right", padx=4)
        ttk.Button(row, text="🔍 سجل أسعار الصنف", command=lambda: self.price_history(None)).pack(side="right", padx=4)
        ttk.Button(row, text="حذف الفاتورة المعلّقة", style="Danger.TButton", command=delete_sel).pack(side="left", padx=4)
        load()

    def _invoice_pending_ids(self, selected):
        """كل الأسطر المعلّقة التي تتبع نفس الفاتورة (رقم الفاتورة + المورد) للصفوف المحددة."""
        ids = set()
        with connect() as c:
            for iid in selected:
                r = c.execute("SELECT id,batch,supplier,status FROM purchases WHERE id=?", (int(iid),)).fetchone()
                if not r:
                    continue
                if r["batch"]:
                    for x in c.execute("SELECT id FROM purchases WHERE batch=? AND supplier=? AND status='pending'", (r["batch"], r["supplier"])).fetchall():
                        ids.add(x[0])
                elif r["status"] == "pending":
                    ids.add(r["id"])
        return sorted(ids)

    def _receive_purchases(self, ids):
        """يضيف الأسطر للمخزون، ويحسب التكلفة بالمتوسط المرجّح بدل استبدال التكلفة القديمة."""
        n = 0
        changes = []
        with connect() as c:
            for pid in ids:
                p = c.execute("SELECT * FROM purchases WHERE id=? AND status='pending'", (pid,)).fetchone()
                if not p:
                    continue
                it = c.execute("SELECT id,part,qty,buy,expense,incomplete FROM items WHERE id=?", (p["item_id"],)).fetchone()
                if not it:
                    raise ValueError(f"الصنف المرتبط بعملية الشراء رقم {pid} غير موجود")
                q1 = max(int(p["qty"] or 0), 1)
                b1 = num(p["buy"])
                e1 = num(p["expense"]) / q1
                q0 = max(int(it["qty"] or 0), 0)
                b0 = num(it["buy"])
                e0 = num(it["expense"])
                # إذا كانت تكلفة المخزون القديم غير معروفة (صنف ناقص) أو لا يوجد مخزون: نأخذ التكلفة الجديدة كاملة
                unknown = bool(it["incomplete"]) or (b0 + e0) <= 0 or q0 <= 0
                if unknown:
                    nb, ne = b1, e1
                else:
                    tot = q0 + q1
                    nb = (q0 * b0 + q1 * b1) / tot
                    ne = (q0 * e0 + q1 * e1) / tot
                c.execute("""
                    UPDATE items SET qty=COALESCE(qty,0)+?, buy=?, expense=?,
                    supplier=COALESCE(NULLIF(supplier,''),?),
                    incomplete=CASE WHEN ?>0 THEN 0 ELSE incomplete END
                    WHERE id=?
                """, (q1, round(nb, 4), round(ne, 4), p["supplier"], b1, p["item_id"]))
                c.execute("UPDATE purchases SET status='received', received_at=? WHERE id=?", (now_str(), pid))
                n += 1
                old_cost, new_cost = b0 + e0, nb + ne
                if unknown:
                    changes.append(f"{it['part']}: تكلفة جديدة {sar(new_cost)}")
                elif abs(old_cost - new_cost) > 0.004:
                    changes.append(f"{it['part']}: {sar(old_cost)} ← {sar(new_cost)}  (سعر الشراء الجديد {sar(b1 + e1)})")
        return n, changes

    def new_purchase(self, on_done=None):
        with connect() as c:
            items = c.execute("SELECT id,item_no,part,car,qty FROM items ORDER BY item_no").fetchall()
            sups = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
        if not items:
            messagebox.showwarning("تنبيه", "أضف أصنافًا أولًا")
            return
        can_add_sup = self.role == "admin" or self.can("suppliers")
        if not sups and not can_add_sup:
            messagebox.showwarning("تنبيه", "لا يوجد موردون. اطلب من المدير إضافة المورد أولًا")
            return
        imap = {f"{r['item_no']} | {r['part']} | {r['car'] or ''} | المتوفر {r['qty']}": r["id"] for r in items}

        win = tk.Toplevel(self)
        win.title("فاتورة شراء جديدة")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)

        head = ttk.LabelFrame(body, text="بيانات الفاتورة", padding=10)
        head.pack(fill="x")
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text="المورد (إجباري)").grid(row=0, column=2, sticky="e", padx=6, pady=4)
        sup_cb = ttk.Combobox(head, values=sups, state="readonly", justify="right")
        sup_cb.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        def plus_sup():
            name = simpledialog.askstring("إضافة مورد", "اسم المورد:", parent=win)
            if not name:
                return
            try:
                name = self._insert_supplier(name)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            with connect() as c:
                names = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
            sup_cb.configure(values=names)
            sup_cb.set(name)

        if can_add_sup:
            ttk.Button(head, text="+", width=3, command=plus_sup).grid(row=0, column=0, padx=2)
        ttk.Label(head, text="رقم فاتورة المورد (اتركه فارغًا ليتولد تلقائيًا)").grid(row=1, column=2, sticky="e", padx=6, pady=4)
        batch = ttk.Entry(head, justify="right")
        batch.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(head, text="تاريخ الفاتورة (YYYY-MM-DD)").grid(row=2, column=2, sticky="e", padx=6, pady=4)
        date_e = ttk.Entry(head, justify="right")
        date_e.insert(0, datetime.now().strftime("%Y-%m-%d"))
        date_e.grid(row=2, column=1, sticky="ew", padx=6, pady=4)

        lf = ttk.LabelFrame(body, text="أصناف الفاتورة", padding=10)
        lf.pack(fill="both", expand=True, pady=8)
        f1 = ttk.Frame(lf)
        f1.pack(fill="x")
        ttk.Label(f1, text="بحث عن صنف").pack(side="right", padx=4)
        flt = ttk.Entry(f1, width=20, justify="right")
        flt.pack(side="right", padx=4)
        ttk.Label(f1, text="الصنف").pack(side="right", padx=4)
        item_cb = ttk.Combobox(f1, values=list(imap), state="readonly", width=50)
        item_cb.pack(side="right", padx=4)
        f2 = ttk.Frame(lf)
        f2.pack(fill="x", pady=6)
        ttk.Label(f2, text="الكمية").pack(side="right", padx=4)
        qty = ttk.Entry(f2, width=8, justify="right")
        qty.insert(0, "1")
        qty.pack(side="right", padx=4)
        ttk.Label(f2, text="سعر شراء الوحدة").pack(side="right", padx=4)
        price = ttk.Entry(f2, width=12, justify="right")
        price.pack(side="right", padx=4)
        ttk.Label(f2, text="مصاريف السطر (شحن/جمارك)").pack(side="right", padx=4)
        exp_e = ttk.Entry(f2, width=10, justify="right")
        exp_e.insert(0, "0")
        exp_e.pack(side="right", padx=4)
        ttk.Label(f2, text="رمزه عند المورد").pack(side="right", padx=4)
        code_e = ttk.Entry(f2, width=14, justify="right")
        code_e.pack(side="right", padx=4)

        lines = []
        tree = make_tree(lf, ("item", "qty", "price", "exp", "total"),
                         {"item": "الصنف", "qty": "الكمية", "price": "سعر الوحدة", "exp": "المصاريف", "total": "إجمالي السطر"},
                         {"item": 330}, height=5)
        total_var = tk.StringVar(value="إجمالي الفاتورة: 0.00 ر.س")
        ttk.Label(lf, textvariable=total_var, font=(FONT, 13, "bold"), foreground=NAVY).pack(anchor="e")

        def apply_filter(_e=None):
            term = flt.get().strip().lower()
            vals = [k for k in imap if term in k.lower()][:200]
            item_cb.configure(values=vals)
            if len(vals) == 1:
                item_cb.set(vals[0])

        def refresh_total():
            total_var.set("إجمالي الفاتورة: " + sar(sum(x["qty"] * x["price"] + x["exp"] for x in lines)))

        def add_line():
            if not item_cb.get() or item_cb.get() not in imap:
                messagebox.showwarning("تنبيه", "اختر الصنف أولًا", parent=win)
                return
            q_ = int(num(qty.get()))
            pr = num(price.get())
            ex = num(exp_e.get())
            if q_ <= 0:
                messagebox.showwarning("تنبيه", "الكمية يجب أن تكون أكبر من صفر", parent=win)
                return
            if pr <= 0:
                messagebox.showwarning("تنبيه", "اكتب سعر الشراء", parent=win)
                return
            if ex < 0:
                messagebox.showwarning("تنبيه", "المصاريف لا تكون سالبة", parent=win)
                return
            lines.append({"id": imap[item_cb.get()], "label": item_cb.get(), "qty": q_, "price": pr, "exp": ex, "code": code_e.get().strip()})
            add_row(tree, (item_cb.get(), q_, sar(pr), sar(ex), sar(q_ * pr + ex)))
            price.delete(0, "end")
            code_e.delete(0, "end")
            exp_e.delete(0, "end")
            exp_e.insert(0, "0")
            qty.delete(0, "end")
            qty.insert(0, "1")
            refresh_total()

        def remove_line():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد السطر المراد حذفه", parent=win)
                return
            idx = tree.index(sel[0])
            tree.delete(sel[0])
            lines.pop(idx)
            refresh_total()

        flt.bind("<KeyRelease>", apply_filter)
        ttk.Button(f2, text="＋ إضافة السطر", style="Accent.TButton", command=lambda: add_line()).pack(side="left", padx=4)
        ttk.Button(f2, text="حذف المحدد", command=lambda: remove_line()).pack(side="left", padx=4)

        def save():
            try:
                sup = sup_cb.get().strip()
                if not sup:
                    raise ValueError("اسم المورد إجباري — اختره من القائمة")
                if not lines:
                    raise ValueError("أضف صنفًا واحدًا على الأقل للفاتورة")
                d = (date_e.get().strip() or datetime.now().strftime("%Y-%m-%d"))
                try:
                    d = datetime.strptime(d, "%Y-%m-%d").strftime("%Y-%m-%d")
                except ValueError:
                    raise ValueError("التاريخ غير صحيح. اكتبه بالشكل 2026-10-15")
                inv = batch.get().strip() or datetime.now().strftime("PUR%y%m%d%H%M%S")
                with connect() as c:
                    if c.execute("SELECT 1 FROM purchases WHERE batch=? AND supplier=? LIMIT 1", (inv, sup)).fetchone():
                        raise ValueError("رقم الفاتورة مسجل مسبقًا لنفس المورد")
                    stamp = f"{d} {datetime.now().strftime('%H:%M:%S')}"
                    for ln in lines:
                        c.execute("""
                            INSERT INTO purchases(batch,date,item_id,supplier,qty,buy,expense,landed,status)
                            VALUES(?,?,?,?,?,?,?,?,'pending')
                        """, (inv, stamp, ln["id"], sup, ln["qty"], ln["price"], ln["exp"], ln["price"] + ln["exp"] / ln["qty"]))
                        self._save_supplier_code(c, ln["id"], sup, ln.get("code", ""))
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            win.destroy()
            if on_done:
                on_done()
            messagebox.showinfo("تم", f"تم تسجيل فاتورة الشراء رقم {inv} ({len(lines)} صنف).\nعند استلام البضاعة حدد الفاتورة واضغط (إضافة الفاتورة المحددة للمخزون).")

        ttk.Button(bar, text="💾  حفظ فاتورة الشراء", style="Accent.TButton", command=save).pack(ipadx=30, ipady=3)
        self.dialog_size(win, body, bar, 920)

    # ------------------------------------------------- سجل أسعار الشراء ومقارنة الموردين
    def price_history_data(self, item_id, d1="", d2=""):
        with connect() as c:
            rows = c.execute("""
                SELECT * FROM purchases WHERE item_id=?
                AND (?='' OR substr(date,1,10)>=?) AND (?='' OR substr(date,1,10)<=?)
                ORDER BY date DESC,id DESC
            """, (item_id, d1, d1, d2, d2)).fetchall()
        out = []
        for r in rows:
            q = max(int(r["qty"] or 0), 1)
            landed = num(r["landed"]) or (num(r["buy"]) + num(r["expense"]) / q)
            out.append({"date": str(r["date"] or "")[:10], "supplier": r["supplier"] or "", "batch": r["batch"] or "",
                        "qty": int(r["qty"] or 0), "buy": num(r["buy"]), "exp": num(r["expense"]) / q, "landed": landed,
                        "status": r["status"] or "received"})
        best = min(out, key=lambda x: x["landed"]) if out else None  # الأحدث عند التساوي لأن الترتيب تنازلي
        by = {}
        for x in out:
            by.setdefault(x["supplier"], []).append(x)
        summary = []
        for sup, lst in by.items():
            tq = sum(x["qty"] for x in lst)
            avg = sum(x["landed"] * x["qty"] for x in lst) / tq if tq else sum(x["landed"] for x in lst) / len(lst)
            summary.append({"supplier": sup, "times": len(lst), "min": min(x["landed"] for x in lst), "avg": avg, "last": lst[0]["landed"]})
        summary.sort(key=lambda z: z["min"])
        return out, best, summary

    def price_history(self, item_id=None):
        if not (self.can("purchases") or self.can("view_cost")):
            return
        win = tk.Toplevel(self)
        win.title("سجل أسعار الشراء ومقارنة الموردين")
        win.configure(bg=BG)
        self.center(win, 1020, 760)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="سجل أسعار الشراء ومقارنة الموردين", style="Title.TLabel").pack(anchor="e")

        top = ttk.LabelFrame(body, text="الصنف والفترة", padding=10)
        top.pack(fill="x", pady=8)
        state = {"map": {}}
        ttk.Label(top, text="بحث (رقم الصنف / القطعة / السيارة)").grid(row=0, column=4, sticky="e", padx=6, pady=4)
        q = ttk.Entry(top, width=26, justify="right")
        q.grid(row=0, column=3, padx=6, pady=4)
        ttk.Label(top, text="الصنف").grid(row=1, column=4, sticky="e", padx=6, pady=4)
        item_cb = ttk.Combobox(top, values=[], state="readonly", width=62)
        item_cb.grid(row=1, column=0, columnspan=4, sticky="ew", padx=6, pady=4)
        ttk.Label(top, text="الفترة").grid(row=2, column=4, sticky="e", padx=6, pady=4)
        period = ttk.Combobox(top, values=["الكل", "آخر 30 يوم", "آخر 90 يوم", "آخر 6 أشهر", "آخر سنة", "فترة محددة"], state="readonly", width=16)
        period.set("الكل")
        period.grid(row=2, column=3, padx=6, pady=4)
        ttk.Label(top, text="من").grid(row=2, column=2, sticky="e")
        from_e = ttk.Entry(top, width=13, justify="center")
        from_e.grid(row=2, column=1, padx=4)
        ttk.Label(top, text="إلى").grid(row=3, column=2, sticky="e")
        to_e = ttk.Entry(top, width=13, justify="center")
        to_e.grid(row=3, column=1, padx=4)
        ttk.Label(top, text="(YYYY-MM-DD)", style="Muted.TLabel").grid(row=2, column=0)

        info_var = tk.StringVar(value="")
        best_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=info_var, style="Muted.TLabel").pack(anchor="e")
        ttk.Label(body, textvariable=best_var, font=(FONT, 13, "bold"), foreground=GREEN).pack(anchor="e", pady=4)
        ttk.Label(body, text="حسب المورد (الأرخص أولًا)", font=(FONT, 11, "bold")).pack(anchor="e")
        sum_t = make_tree(body, ("supplier", "times", "min", "avg", "last"),
                          {"supplier": "المورد", "times": "عدد المرات", "min": "أقل تكلفة نهائية", "avg": "متوسط التكلفة (حسب الكمية)", "last": "آخر تكلفة"},
                          {"supplier": 240, "avg": 190}, height=4)
        ttk.Label(body, text="كل عمليات الشراء", font=(FONT, 11, "bold")).pack(anchor="e")
        hist_t = make_tree(body, ("date", "supplier", "batch", "qty", "buy", "exp", "landed", "status"),
                           {"date": "التاريخ", "supplier": "المورد", "batch": "رقم الفاتورة", "qty": "الكمية", "buy": "سعر الوحدة", "exp": "مصاريف/وحدة", "landed": "التكلفة النهائية", "status": "الحالة"},
                           {"supplier": 180, "batch": 140}, height=6)

        def show(*_):
            clear_tree(sum_t)
            clear_tree(hist_t)
            iid = state["map"].get(item_cb.get())
            if not iid:
                return
            d1, d2 = from_e.get().strip(), to_e.get().strip()
            for dv in (d1, d2):
                if dv:
                    try:
                        datetime.strptime(dv, "%Y-%m-%d")
                    except ValueError:
                        messagebox.showwarning("تنبيه", "التاريخ لازم يكون بالشكل 2026-10-15", parent=win)
                        return
            with connect() as c:
                it = c.execute("SELECT qty,buy,expense FROM items WHERE id=?", (iid,)).fetchone()
            info_var.set(f"المتوفر الآن: {it['qty'] or 0} قطعة   |   التكلفة الحالية في المخزون (متوسط مرجّح): {sar(num(it['buy']) + num(it['expense']))}")
            rows, best, summary = self.price_history_data(iid, d1, d2)
            if not best:
                best_var.set("لا توجد مشتريات مسجلة لهذا الصنف في هذه الفترة")
                return
            best_var.set(f"🏆 أقل تكلفة نهائية: {sar(best['landed'])} — من المورد {best['supplier']} بتاريخ {best['date']}")
            for i, sm in enumerate(summary):
                add_row(sum_t, (sm["supplier"], sm["times"], sar(sm["min"]), sar(sm["avg"]), sar(sm["last"])), extra=("best",) if i == 0 else ())
            for x in rows:
                add_row(hist_t, (x["date"], x["supplier"], x["batch"], x["qty"], sar(x["buy"]), sar(x["exp"]), sar(x["landed"]),
                                 "⏳ معلّقة" if x["status"] == "pending" else "✅ مستلمة"),
                        extra=("best",) if abs(x["landed"] - best["landed"]) < 0.005 else ())

        def find(*_):
            term = "%" + q.get().strip() + "%"
            with connect() as c:
                rows = c.execute("SELECT id,item_no,part,car FROM items WHERE item_no LIKE ? OR part LIKE ? OR car LIKE ? ORDER BY item_no LIMIT 100", (term, term, term)).fetchall()
            state["map"] = {f"{r['item_no']} | {r['part']} | {r['car'] or ''}": r["id"] for r in rows}
            item_cb.configure(values=list(state["map"]))
            if state["map"]:
                item_cb.current(0)
                show()
            else:
                item_cb.set("")
                clear_tree(sum_t)
                clear_tree(hist_t)
                info_var.set("")
                best_var.set("لا توجد أصناف مطابقة")

        def set_period(*_):
            p = period.get()
            days = {"آخر 30 يوم": 30, "آخر 90 يوم": 90, "آخر 6 أشهر": 182, "آخر سنة": 365}.get(p)
            if p == "الكل":
                from_e.delete(0, "end")
                to_e.delete(0, "end")
            elif days:
                today = datetime.now()
                from_e.delete(0, "end")
                from_e.insert(0, (today - timedelta(days=days)).strftime("%Y-%m-%d"))
                to_e.delete(0, "end")
                to_e.insert(0, today.strftime("%Y-%m-%d"))
            show()

        ttk.Button(top, text="🔍 بحث", style="Accent.TButton", command=find).grid(row=0, column=2, padx=6)
        ttk.Button(top, text="عرض", command=show).grid(row=3, column=3, padx=6)
        q.bind("<Return>", find)
        item_cb.bind("<<ComboboxSelected>>", show)
        period.bind("<<ComboboxSelected>>", set_period)
        if item_id:
            with connect() as c:
                r = c.execute("SELECT item_no FROM items WHERE id=?", (item_id,)).fetchone()
            if r:
                q.insert(0, r["item_no"])
                find()

    # ---------------------------------------------------------------- الموردون
    def suppliers(self):
        if not self.can("suppliers"):
            return
        self.clear("suppliers")
        self.page_title("الموردون", "رقم واتساب المورد يُستخدم لإرسال طلبات الشراء إليه")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        cols = ("id", "name", "code", "phone", "items", "notes")
        t = make_tree(self.body, cols, {"id": "رقم", "name": "اسم المورد", "code": "رمز الباركود", "phone": "رقم الواتساب", "items": "عدد أصنافه", "notes": "ملاحظات"},
                      {"id": 55, "name": 240, "code": 110, "phone": 160, "notes": 300})

        def load():
            with connect() as c:
                rows = c.execute("SELECT s.*,(SELECT COUNT(*) FROM items i WHERE i.supplier=s.name) n FROM suppliers s ORDER BY s.name").fetchall()
            clear_tree(t)
            for r in rows:
                add_row(t, (r["id"], r["name"], r["code"] or "", r["phone"] or "", r["n"], r["notes"] or ""), iid=str(r["id"]),
                        extra=() if normalize_phone(r["phone"]) else ("low",))

        def save_edit(sid, d):
            if d["phone"] and len(normalize_phone(d["phone"])) < 9:
                raise ValueError("رقم الجوال غير صحيح (مثال 0501234567)")
            code = re.sub(r"[^A-Za-z0-9]", "", d["code"]).upper()
            if not code:
                raise ValueError("رمز المورد مطلوب (حروف وأرقام إنجليزية، مثل S01 أو TOY)")
            if len(code) > 8:
                raise ValueError("رمز المورد طويل: 8 أحرف كحد أقصى")
            with connect() as c:
                if c.execute("SELECT 1 FROM suppliers WHERE UPPER(code)=? AND id<>?", (code, sid)).fetchone():
                    raise ValueError("هذا الرمز مستخدم لمورد آخر")
                c.execute("UPDATE suppliers SET phone=?,notes=?,code=? WHERE id=?", (d["phone"], d["notes"], code, sid))

        def edit():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد المورد أولًا")
                return
            sid = int(sel[0])
            with connect() as c:
                r = c.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
            self.form(f"تعديل المورد {r['name']}", [("code", "رمز المورد على الباركود (حروف/أرقام إنجليزية)", r["code"] or ""), ("phone", "رقم واتساب المورد", r["phone"] or ""), ("notes", "ملاحظات", r["notes"] or "")],
                      lambda d: save_edit(sid, d), on_done=load)

        ttk.Button(row, text="＋ إضافة مورد", style="Accent.TButton", command=self.add_supplier).pack(side="right", padx=4)
        ttk.Button(row, text="✎ تعديل الرمز / رقم الواتساب / الملاحظات", command=edit).pack(side="right", padx=4)
        ttk.Label(self.body, text="الموردون المظللون بالأصفر ما لهم رقم واتساب — أضفه ليصلهم طلب الشراء مباشرة.", style="Muted.TLabel").pack(anchor="e")
        t.bind("<Double-1>", lambda e: edit())
        load()

    def add_supplier(self):
        self.form("إضافة مورد", [
            ("name", "اسم المورد", ""),
            ("phone", "رقم الجوال", ""),
            ("notes", "ملاحظات", "")
        ], self._save_supplier, on_done=self.suppliers)

    def _save_supplier(self, d):
        self._insert_supplier(d["name"], d["phone"], d["notes"])

    # ------------------------------------------------------------- أنواع القطع
    def item_types_page(self):
        self.clear("types")
        self.page_title("أنواع القطع", "القائمة التي يختار منها الموظفون نوع القطعة")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        name = ttk.Entry(row, width=28, justify="right")
        name.pack(side="right", padx=4)
        ttk.Button(row, text="＋ إضافة نوع", style="Accent.TButton", command=lambda: self._add_type(name.get())).pack(side="right")
        with connect() as c:
            rows = c.execute("SELECT * FROM item_types ORDER BY name").fetchall()
        self.table(("id", "name"), {"id": "رقم", "name": "نوع القطعة"}, [tuple(r) for r in rows])

    def _add_type(self, name):
        try:
            self._insert_type(name)
        except Exception as e:
            messagebox.showwarning("تنبيه", str(e))
            return
        self.item_types_page()

    # ---------------------------------------------------------------- المصروفات
    def expenses(self):
        if not self.can("expenses"):
            return
        self.clear("expenses")
        self.page_title("المصروفات", "تسجيل ومتابعة مصروفات المحل")
        ttk.Button(self.body, text="＋ تسجيل مصروف", style="Accent.TButton", command=lambda: self.form("تسجيل مصروف", [
            ("category", "نوع المصروف", ""),
            ("amount", "المبلغ", "0"),
            ("notes", "ملاحظات", "")
        ], self._save_expense, on_done=self.expenses)).pack(anchor="w", pady=6)
        with connect() as c:
            rows = c.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 100").fetchall()
        self.table(("id", "date", "category", "amount", "notes"), {"id": "رقم", "date": "التاريخ", "category": "النوع", "amount": "المبلغ", "notes": "ملاحظات"},
                   [(r["id"], r["date"], r["category"], sar(num(r["amount"])), r["notes"]) for r in rows])

    def _save_expense(self, d):
        amount = num(d["amount"])
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        with connect() as c:
            c.execute("INSERT INTO expenses(date,category,amount,notes) VALUES(?,?,?,?)", (now_str(), d["category"], amount, d["notes"]))

    # ------------------------------------------------------------ نموذج عام
    def form(self, title, fields, callback, on_done=None, height=None):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)
        entries = {}
        for idx, (key, label, default) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=idx, column=1, sticky="e", padx=6, pady=6)
            ent = ttk.Entry(frame, width=34, justify="right")
            ent.grid(row=idx, column=0, sticky="ew", padx=6, pady=6)
            ent.insert(0, default)
            entries[key] = ent

        def save():
            data = {key: ent.get().strip() for key, ent in entries.items()}
            try:
                callback(data)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            win.destroy()
            if on_done:
                on_done()

        ttk.Button(frame, text="حفظ", style="Accent.TButton", command=save).grid(row=len(fields), column=0, pady=12)
        frame.columnconfigure(0, weight=1)
        self.autosize(win, frame, 500)

    # ---------------------------------------------------------- البونص: الموظف
    def bonus_page_emp(self):
        if not self.can("bonus"):
            return
        self.clear("bonus")
        self.page_title("تسجيل الأعمال", "اكتب كم مرة نفّذت كل عمل، وسيصل للمدير للاعتماد وحساب المبلغ")
        with connect() as c:
            jobs = c.execute("SELECT id,name FROM job_types WHERE active=1 ORDER BY id").fetchall()

        frm = ttk.LabelFrame(self.body, text="طلب جديد", padding=14)
        frm.pack(fill="x", pady=6)
        frm.columnconfigure(0, weight=1)
        ttk.Label(frm, text="تاريخ العمل (YYYY-MM-DD)").grid(row=0, column=1, sticky="e", padx=8, pady=5)
        d_ent = ttk.Entry(frm, width=16, justify="center")
        d_ent.insert(0, datetime.now().strftime("%Y-%m-%d"))
        d_ent.grid(row=0, column=0, sticky="w", pady=5)

        spins = {}
        if not jobs:
            ttk.Label(frm, text="المدير لم يحدد أنواع الأعمال بعد.", style="Muted.TLabel").grid(row=1, column=0, columnspan=2)
        for i, j in enumerate(jobs, start=1):
            ttk.Label(frm, text=j["name"], font=(FONT, 11)).grid(row=i, column=1, sticky="e", padx=8, pady=5)
            sp = ttk.Spinbox(frm, from_=0, to=999, width=8, justify="center")
            sp.set(0)
            sp.grid(row=i, column=0, sticky="w", pady=5)
            spins[j["id"]] = (j["name"], sp)
        n_row = len(jobs) + 1
        ttk.Label(frm, text="ملاحظة (اختياري)").grid(row=n_row, column=1, sticky="e", padx=8, pady=5)
        note = ttk.Entry(frm, width=50, justify="right")
        note.grid(row=n_row, column=0, sticky="w", pady=5)

        def submit():
            try:
                wd = datetime.strptime(d_ent.get().strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("تنبيه", "التاريخ غير صحيح. اكتبه بالشكل 2026-10-14")
                return
            lines = []
            for jid, (name, sp) in spins.items():
                n = int(num(sp.get()))
                if n > 0:
                    lines.append((jid, name, n))
            if not lines:
                messagebox.showwarning("تنبيه", "اكتب عددًا لعمل واحد على الأقل")
                return
            if not messagebox.askyesno("تأكيد", "إرسال الطلب للمدير للاعتماد؟"):
                return
            with connect() as c:
                cur = c.execute("INSERT INTO bonus_claims(employee,work_date,created_at,status,note) VALUES(?,?,?,'pending',?)",
                                (self.user, wd, now_str(), note.get().strip()))
                for jid, name, n in lines:
                    c.execute("INSERT INTO bonus_lines(claim_id,job_id,job_name,cnt) VALUES(?,?,?,?)", (cur.lastrowid, jid, name, n))
            messagebox.showinfo("تم", "تم إرسال الطلب للمدير")
            self.bonus_page_emp()

        if jobs:
            ttk.Button(frm, text="إرسال للمدير", style="Accent.TButton", command=submit).grid(row=n_row + 1, column=0, sticky="w", pady=10)

        ttk.Label(self.body, text="طلباتي السابقة", font=(FONT, 12, "bold")).pack(anchor="e", pady=(10, 0))
        with connect() as c:
            claims = c.execute("SELECT * FROM bonus_claims WHERE employee=? ORDER BY id DESC LIMIT 100", (self.user,)).fetchall()
            data = []
            for cl in claims:
                ls = c.execute("SELECT job_name,cnt FROM bonus_lines WHERE claim_id=? ORDER BY id", (cl["id"],)).fetchall()
                details = "، ".join(f"{l['job_name']} × {l['cnt']}" for l in ls)
                data.append((cl["id"], cl["work_date"], details, STATUS_AR.get(cl["status"], cl["status"]), cl["decision_note"] or ""))
        self.table(("id", "date", "details", "status", "note"), {"id": "رقم", "date": "تاريخ العمل", "details": "الأعمال", "status": "الحالة", "note": "ملاحظة المدير"}, data,
                   {"id": 60, "details": 420, "status": 170, "note": 200})

    # ---------------------------------------------------------- البونص: المدير
    def _claim_lines(self, c, claim):
        lines = c.execute("""
            SELECT l.*, j.rate AS cur_rate FROM bonus_lines l LEFT JOIN job_types j ON j.id=l.job_id
            WHERE l.claim_id=? ORDER BY l.id
        """, (claim["id"],)).fetchall()
        out = []
        for l in lines:
            if claim["status"] == "approved":
                rate = num(l["rate"])
            else:
                rate = num(l["cur_rate"]) if l["cur_rate"] is not None else num(l["rate"])
            out.append((l["job_name"], l["cnt"], rate, rate * l["cnt"]))
        return out

    def _decide_claim(self, claim_id, approve, note=""):
        with connect() as c:
            cl = c.execute("SELECT * FROM bonus_claims WHERE id=?", (claim_id,)).fetchone()
            if not cl or cl["status"] != "pending":
                raise ValueError("هذا الطلب تم البت فيه مسبقًا")
            total = 0
            if approve:
                for l in c.execute("SELECT l.id,l.cnt,j.rate FROM bonus_lines l LEFT JOIN job_types j ON j.id=l.job_id WHERE l.claim_id=?", (claim_id,)).fetchall():
                    rate = num(l["rate"])
                    amount = rate * l["cnt"]
                    total += amount
                    c.execute("UPDATE bonus_lines SET rate=?, amount=? WHERE id=?", (rate, amount, l["id"]))
            c.execute("UPDATE bonus_claims SET status=?,total=?,decided_by=?,decided_at=?,decision_note=? WHERE id=?",
                      ("approved" if approve else "rejected", total, self.user, now_str(), note, claim_id))

    def bonus_page_admin(self):
        if self.role != "admin":
            return
        self.clear("bonus")
        self.page_title("البونص والأعمال", "حدّد قيمة كل عمل، واعتمد طلبات الموظفين")
        nb = ttk.Notebook(self.body)
        nb.pack(fill="both", expand=True)
        tab1 = ttk.Frame(nb, padding=10)
        tab2 = ttk.Frame(nb, padding=10)
        tab3 = ttk.Frame(nb, padding=10)
        nb.add(tab1, text="طلبات الموظفين")
        nb.add(tab2, text="قيم الأعمال")
        nb.add(tab3, text="ملخص الشهر")

        # ---------- الطلبات
        bar = ttk.Frame(tab1)
        bar.pack(fill="x")
        ttk.Label(bar, text="الحالة").pack(side="right", padx=4)
        status_cb = ttk.Combobox(bar, values=["بانتظار الاعتماد", "معتمد", "مرفوض", "الكل"], state="readonly", width=18)
        status_cb.set("بانتظار الاعتماد")
        status_cb.pack(side="right", padx=4)
        t1 = make_tree(tab1, ("id", "employee", "date", "details", "total", "status"),
                       {"id": "رقم", "employee": "الموظف", "date": "تاريخ العمل", "details": "الأعمال", "total": "المبلغ المستحق", "status": "الحالة"},
                       {"id": 55, "details": 380, "status": 150, "total": 130})
        t1.configure(selectmode="extended")
        smap = {"بانتظار الاعتماد": "pending", "معتمد": "approved", "مرفوض": "rejected"}

        def load1(*_):
            st = smap.get(status_cb.get())
            with connect() as c:
                if st:
                    claims = c.execute("SELECT * FROM bonus_claims WHERE status=? ORDER BY id DESC LIMIT 300", (st,)).fetchall()
                else:
                    claims = c.execute("SELECT * FROM bonus_claims ORDER BY id DESC LIMIT 300").fetchall()
                clear_tree(t1)
                for cl in claims:
                    lines = self._claim_lines(c, cl)
                    total = sum(x[3] for x in lines)
                    zero = any(x[2] == 0 for x in lines) and cl["status"] == "pending"
                    details = "، ".join(f"{x[0]} × {x[1]}" for x in lines)
                    add_row(t1, (cl["id"], cl["employee"], cl["work_date"], details, sar(total) + (" ⚠" if zero else ""), STATUS_AR.get(cl["status"], cl["status"])),
                            iid=str(cl["id"]))
            self.refresh_badges()

        def approve():
            ids = [int(i) for i in t1.selection()]
            if not ids:
                messagebox.showwarning("تنبيه", "حدد طلبًا أولًا")
                return
            zero = False
            with connect() as c:
                for i in ids:
                    cl = c.execute("SELECT * FROM bonus_claims WHERE id=?", (i,)).fetchone()
                    if cl and cl["status"] == "pending" and any(x[2] == 0 for x in self._claim_lines(c, cl)):
                        zero = True
            if zero and not messagebox.askyesno("تنبيه", "بعض الأعمال قيمتها 0 (لم تحدد لها مبلغًا في تبويب قيم الأعمال).\nالاعتماد سيحسبها صفر. هل تريد المتابعة؟"):
                return
            n = 0
            for i in ids:
                try:
                    self._decide_claim(i, True)
                    n += 1
                except ValueError:
                    pass
            load1()
            load3()
            messagebox.showinfo("تم", f"تم اعتماد {n} طلب")

        def reject():
            ids = [int(i) for i in t1.selection()]
            if not ids:
                messagebox.showwarning("تنبيه", "حدد طلبًا أولًا")
                return
            reason = simpledialog.askstring("رفض", "سبب الرفض (اختياري):", parent=self) or ""
            n = 0
            for i in ids:
                try:
                    self._decide_claim(i, False, reason)
                    n += 1
                except ValueError:
                    pass
            load1()
            load3()
            messagebox.showinfo("تم", f"تم رفض {n} طلب")

        def details():
            sel = t1.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد طلبًا أولًا")
                return
            cid = int(sel[0])
            with connect() as c:
                cl = c.execute("SELECT * FROM bonus_claims WHERE id=?", (cid,)).fetchone()
                lines = self._claim_lines(c, cl)
            win = tk.Toplevel(self)
            win.title(f"تفاصيل الطلب {cid}")
            win.configure(bg=BG)
            win.geometry("700x440")
            ttk.Label(win, text=f"طلب {cl['employee']} — {cl['work_date']}", style="Title.TLabel").pack(pady=8)
            if cl["note"]:
                ttk.Label(win, text="ملاحظة الموظف: " + cl["note"]).pack()
            tt = make_tree(win, ("job", "cnt", "rate", "amount"), {"job": "العمل", "cnt": "العدد", "rate": "قيمة الواحد", "amount": "المبلغ"}, {"job": 260})
            for x in lines:
                add_row(tt, (x[0], x[1], sar(x[2]), sar(x[3])))
            ttk.Label(win, text="الإجمالي: " + sar(sum(x[3] for x in lines)), font=(FONT, 14, "bold"), foreground=NAVY).pack(pady=6)
            ttk.Label(win, text="الحالة: " + STATUS_AR.get(cl["status"], cl["status"])).pack()

        ttk.Button(bar, text="✔ اعتماد المحدد", style="Success.TButton", command=approve).pack(side="left", padx=4)
        ttk.Button(bar, text="✖ رفض المحدد", style="Danger.TButton", command=reject).pack(side="left", padx=4)
        ttk.Button(bar, text="التفاصيل", command=details).pack(side="left", padx=4)
        status_cb.bind("<<ComboboxSelected>>", load1)
        t1.bind("<Double-1>", lambda e: details())

        # ---------- قيم الأعمال
        bar2 = ttk.Frame(tab2)
        bar2.pack(fill="x")
        ttk.Label(tab2, text="الموظف يرى أسماء الأعمال فقط ويكتب العدد — القيم والمبالغ تظهر لك وحدك.", style="Muted.TLabel").pack(anchor="e")
        t2 = make_tree(tab2, ("id", "name", "rate", "active"), {"id": "رقم", "name": "العمل", "rate": "القيمة (للمرة الواحدة)", "active": "الحالة"}, {"id": 55, "name": 340, "rate": 180})

        def load2():
            with connect() as c:
                rows = c.execute("SELECT * FROM job_types ORDER BY id").fetchall()
            clear_tree(t2)
            for r in rows:
                add_row(t2, (r["id"], r["name"], sar(num(r["rate"])), "فعّال" if r["active"] else "موقوف"), iid=str(r["id"]), extra=() if num(r["rate"]) > 0 else ("low",))

        def add_job():
            name = simpledialog.askstring("إضافة عمل", "اسم العمل (مثال: برمجة سيارة داخل العمل):", parent=self)
            name = clean_name(name)
            if not name:
                return
            rate = simpledialog.askfloat("قيمة العمل", "القيمة للمرة الواحدة (ر.س):", parent=self, minvalue=0)
            if rate is None:
                return
            with connect() as c:
                if c.execute("SELECT 1 FROM job_types WHERE name=? COLLATE NOCASE", (name,)).fetchone():
                    messagebox.showwarning("تنبيه", "العمل موجود مسبقًا")
                    return
                c.execute("INSERT INTO job_types(name,rate,active) VALUES(?,?,1)", (name, rate))
            load2()

        def edit_rate():
            sel = t2.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد العمل أولًا")
                return
            jid = int(sel[0])
            with connect() as c:
                r = c.execute("SELECT * FROM job_types WHERE id=?", (jid,)).fetchone()
            rate = simpledialog.askfloat("تعديل القيمة", f"قيمة «{r['name']}» للمرة الواحدة (ر.س):", parent=self, minvalue=0, initialvalue=num(r["rate"]))
            if rate is None:
                return
            with connect() as c:
                c.execute("UPDATE job_types SET rate=? WHERE id=?", (rate, jid))
            load2()
            load1()

        def toggle_job():
            sel = t2.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد العمل أولًا")
                return
            with connect() as c:
                c.execute("UPDATE job_types SET active=1-COALESCE(active,1) WHERE id=?", (int(sel[0]),))
            load2()

        ttk.Button(bar2, text="＋ إضافة عمل", style="Accent.TButton", command=add_job).pack(side="right", padx=4)
        ttk.Button(bar2, text="تعديل القيمة", command=edit_rate).pack(side="right", padx=4)
        ttk.Button(bar2, text="تفعيل / إيقاف", command=toggle_job).pack(side="right", padx=4)

        # ---------- ملخص الشهر
        bar3 = ttk.Frame(tab3)
        bar3.pack(fill="x")
        ttk.Label(bar3, text="الشهر (YYYY-MM)").pack(side="right", padx=4)
        month = ttk.Entry(bar3, width=12, justify="center")
        month.insert(0, datetime.now().strftime("%Y-%m"))
        month.pack(side="right", padx=4)
        t3 = make_tree(tab3, ("employee", "ap", "tot", "pe"), {"employee": "الموظف", "ap": "طلبات معتمدة", "tot": "إجمالي البونص المعتمد", "pe": "طلبات معلّقة"}, {"employee": 200, "tot": 200})
        total_var = tk.StringVar(value="")
        ttk.Label(tab3, textvariable=total_var, font=(FONT, 13, "bold"), foreground=NAVY).pack(anchor="e")

        def load3(*_):
            m = month.get().strip() + "%"
            with connect() as c:
                rows = c.execute("""
                    SELECT employee,
                    SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) ap,
                    COALESCE(SUM(CASE WHEN status='approved' THEN total END),0) tot,
                    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) pe
                    FROM bonus_claims WHERE work_date LIKE ? GROUP BY employee ORDER BY tot DESC
                """, (m,)).fetchall()
            clear_tree(t3)
            grand = 0
            for r in rows:
                grand += r["tot"]
                add_row(t3, (r["employee"], r["ap"], sar(r["tot"]), r["pe"]))
            total_var.set("إجمالي البونص المعتمد للشهر: " + sar(grand))

        ttk.Button(bar3, text="عرض", style="Accent.TButton", command=load3).pack(side="right", padx=4)
        month.bind("<Return>", load3)

        load1()
        load2()
        load3()

    # ---------------------------------------------------------- المستخدمون والصلاحيات
    def users_page(self):
        if self.role != "admin":
            return
        self.clear("users")
        self.page_title("المستخدمون والصلاحيات", "حدّد لكل موظف ماذا يرى وماذا يستطيع أن يفعل")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        t = make_tree(self.body, ("username", "role", "perms"), {"username": "اسم المستخدم", "role": "الدور", "perms": "الصلاحيات"}, {"username": 160, "role": 100, "perms": 700})

        def load():
            with connect() as c:
                rows = c.execute("SELECT * FROM users ORDER BY role,username").fetchall()
            clear_tree(t)
            for r in rows:
                if r["role"] == "admin":
                    summary = "كل الصلاحيات"
                else:
                    ps = str_to_perms(r["perms"])
                    summary = "، ".join(PERM_LABELS[k] for k, _, _ in PERMS if k in ps) or "لا يوجد"
                add_row(t, (r["username"], "مدير" if r["role"] == "admin" else "موظف", summary), iid=r["username"])

        def edit():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد مستخدمًا أولًا")
                return
            self.user_dialog(sel[0], on_done=load)

        def delete():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد مستخدمًا أولًا")
                return
            name = sel[0]
            if name == self.user:
                messagebox.showwarning("تنبيه", "لا يمكنك حذف حسابك")
                return
            if not messagebox.askyesno("تأكيد", f"حذف المستخدم {name}؟"):
                return
            with connect() as c:
                r = c.execute("SELECT role FROM users WHERE username=?", (name,)).fetchone()
                if r and r["role"] == "admin" and c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
                    messagebox.showwarning("تنبيه", "لازم يبقى مدير واحد على الأقل")
                    return
                c.execute("DELETE FROM users WHERE username=?", (name,))
            load()

        ttk.Button(row, text="＋ إضافة مستخدم", style="Accent.TButton", command=lambda: self.user_dialog(None, on_done=load)).pack(side="right", padx=4)
        ttk.Button(row, text="تعديل (صلاحيات / كلمة مرور)", command=edit).pack(side="right", padx=4)
        ttk.Button(row, text="حذف", style="Danger.TButton", command=delete).pack(side="left", padx=4)
        t.bind("<Double-1>", lambda e: edit())
        load()

    def user_dialog(self, username=None, on_done=None):
        editing = username is not None
        row = None
        if editing:
            with connect() as c:
                row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row:
                return
        win = tk.Toplevel(self)
        win.title("تعديل مستخدم" if editing else "إضافة مستخدم")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        frame = self.scroll_area(win)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="اسم المستخدم").grid(row=0, column=1, sticky="e", padx=6, pady=5)
        u = ttk.Entry(frame, width=32, justify="right")
        u.grid(row=0, column=0, sticky="ew", pady=5)
        if editing:
            u.insert(0, username)
            u.configure(state="disabled")
        ttk.Label(frame, text="كلمة المرور" + (" (اتركها فارغة بدون تغيير)" if editing else "")).grid(row=1, column=1, sticky="e", padx=6, pady=5)
        p = ttk.Entry(frame, width=32, show="•", justify="right")
        p.grid(row=1, column=0, sticky="ew", pady=5)
        ttk.Label(frame, text="الدور").grid(row=2, column=1, sticky="e", padx=6, pady=5)
        role_cb = ttk.Combobox(frame, values=["موظف", "مدير"], state="readonly")
        role_cb.set("مدير" if editing and row["role"] == "admin" else "موظف")
        role_cb.grid(row=2, column=0, sticky="ew", pady=5)

        box = ttk.LabelFrame(frame, text="صلاحيات الموظف (المدير يملك كل الصلاحيات)", padding=10)
        box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)
        current = str_to_perms(row["perms"]) if editing else set(DEFAULT_PERMS)
        vars_ = {}
        checks = []
        for i, (k, label, _) in enumerate(PERMS):
            v = tk.BooleanVar(value=k in current)
            vars_[k] = v
            cb = ttk.Checkbutton(box, text=label, variable=v)
            cb.grid(row=i // 2, column=i % 2, sticky="e", padx=14, pady=3)
            checks.append(cb)
        box.columnconfigure(0, weight=1)
        box.columnconfigure(1, weight=1)

        def toggle(*_):
            for cb in checks:
                cb.state(["disabled"] if role_cb.get() == "مدير" else ["!disabled"])

        role_cb.bind("<<ComboboxSelected>>", toggle)
        toggle()

        def save():
            name = username if editing else u.get().strip()
            pw = p.get()
            role = "admin" if role_cb.get() == "مدير" else "employee"
            perms = perms_to_str({k for k, v in vars_.items() if v.get()})
            try:
                if not name:
                    raise ValueError("اسم المستخدم مطلوب")
                with connect() as c:
                    if editing:
                        if name == self.user and role != "admin":
                            raise ValueError("لا يمكنك إزالة صلاحية المدير عن حسابك")
                        if row["role"] == "admin" and role != "admin" and c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
                            raise ValueError("لازم يبقى مدير واحد على الأقل")
                        if pw:
                            s, h = pw_hash(pw)
                            c.execute("UPDATE users SET salt=?,hash=?,role=?,perms=? WHERE username=?", (s, h, role, perms, name))
                        else:
                            c.execute("UPDATE users SET role=?,perms=? WHERE username=?", (role, perms, name))
                    else:
                        if not pw:
                            raise ValueError("كلمة المرور مطلوبة")
                        if len(pw) < 4:
                            raise ValueError("كلمة المرور قصيرة (4 أحرف على الأقل)")
                        if c.execute("SELECT 1 FROM users WHERE username=?", (name,)).fetchone():
                            raise ValueError("اسم المستخدم موجود مسبقًا")
                        s, h = pw_hash(pw)
                        c.execute("INSERT INTO users(username,salt,hash,role,perms) VALUES(?,?,?,?,?)", (name, s, h, role, perms))
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            win.destroy()
            if on_done:
                on_done()

        ttk.Button(bar, text="💾  حفظ المستخدم", style="Accent.TButton", command=save).pack(ipadx=30, ipady=3)
        self.dialog_size(win, frame, bar, 680)

    # ----------------------------------------------------------------- الإعدادات
    def settings(self):
        if self.role != "admin":
            return
        self.clear("settings")
        self.page_title("الإعدادات", "النسخ الاحتياطي والمزامنة وحسابك")
        ttk.Label(self.body, text=f"النسخة: {APP_VERSION}   |   ملف قاعدة البيانات المستخدم: {DB}", style="Muted.TLabel").pack(anchor="e")
        box = ttk.Frame(self.body)
        box.pack(anchor="e", pady=6)
        ttk.Button(box, text="🔐  إدارة المستخدمين والصلاحيات", command=self.users_page).pack(fill="x", pady=5, ipadx=20)
        ttk.Button(box, text="🔑  تغيير كلمة المرور", command=self.change_pw).pack(fill="x", pady=5)
        ttk.Button(box, text="💾  نسخة احتياطية", command=self.backup).pack(fill="x", pady=5)
        ttk.Button(box, text="📄  إعداد Google Sheets", command=self.sync_from_settings).pack(fill="x", pady=5)
        ttk.Button(box, text="🔄  التحقق من وجود تحديث", style="Accent.TButton", command=self.check_for_updates).pack(fill="x", pady=5)
        ttk.Button(box, text="📞  مسؤول المشتريات (واتساب النواقص)", command=self.purchasing_dialog).pack(fill="x", pady=5)
        ttk.Button(box, text="👤  جوال المدير لاستلام طلبات الموظفين", command=self.manager_phone_dialog).pack(fill="x", pady=5)
        ttk.Button(box, text="🗂  نسخة كاملة (قاعدة البيانات + الصور)", command=self.backup_full).pack(fill="x", pady=5)
        ttk.Label(self.body, text="رابط Google Apps Script ورمز المزامنة يُحفظان محليًا", style="Muted.TLabel").pack(anchor="e", pady=4)
        last_sync = setting("sheets_last_sync")
        last_err = setting("sheets_last_error")
        if last_sync:
            ttk.Label(self.body, text="آخر مزامنة ناجحة: " + last_sync).pack(anchor="e")
        if last_err:
            ttk.Label(self.body, text="آخر خطأ مزامنة: " + last_err, foreground=RED).pack(anchor="e")

    # ------------------------------------------------------------- نواقص المخزون
    # ------------------------------------------------------------- تنبيهات النواقص (تلقائية)
    def _update_alert_button(self, n):
        b = getattr(self, "alert_btn", None)
        if b is None:
            return
        try:
            b.configure(text=f"🔔 النواقص ({n})" if n else "🔔 النواقص", bg=RED if n else "#475569",
                        activebackground="#b91c1c" if n else "#334155")
        except tk.TclError:
            pass

    def check_stock_alerts(self):
        """يفحص النواقص؛ إذا وصل صنف جديد إلى حد التنبيه يظهر إشعار لمسؤول المشتريات (ولمن عنده الصلاحية)."""
        if not self.user or not self.can("shortage"):
            return
        try:
            with connect() as c:
                low, new = stock_alert_state(c, self.user)
        except Exception:
            return
        self._update_alert_button(len(low))
        if not new:
            return
        if getattr(self, "_alert_popup_open", False):
            return
        if self._alerts_blocked():
            # أنت داخل نافذة (إضافة صنف / استيراد فاتورة...): لا نقاطعك، نعيد المحاولة بعد قليل
            if not getattr(self, "_alert_retry", False):
                self._alert_retry = True
                self.after(8000, self._alert_retry_now)
            return
        try:
            with connect() as c:
                mark_alerts_notified(c, [r["id"] for r in new], self.user)
        except Exception:
            return
        self._show_alert_popup(new, len(low))

    def _alerts_blocked(self):
        """هل توجد نافذة تحجز الإدخال (حوار مفتوح) أو استيراد فاتورة جارٍ؟"""
        try:
            if self.grab_current() is not None:
                return True
        except tk.TclError:
            pass
        return getattr(self, "_alert_block", 0) > 0

    def _alert_retry_now(self):
        self._alert_retry = False
        try:
            self.check_stock_alerts()
        except Exception:
            pass

    def _stock_alert_tick(self):
        try:
            self.check_stock_alerts()
        except Exception:
            pass
        try:
            self.after(60000, self._stock_alert_tick)
        except tk.TclError:
            pass

    def _alert_tree(self, parent, height=None):
        t = make_tree(parent, ("item_no", "name", "qty", "min", "supplier"),
                      {"item_no": "رقم الصنف", "name": "الصنف", "qty": "المتوفر", "min": "حد التنبيه", "supplier": "المورد"},
                      {"name": 330, "supplier": 150}, height=height)
        return t

    def _alert_fill(self, t, rows):
        clear_tree(t)
        for r in rows:
            q_ = r["qty"] or 0
            add_row(t, (r["item_no"], item_display_name(r), q_, r["min_qty"], r["supplier"] or ""), iid=str(r["id"]),
                    extra=("out",) if q_ <= 0 else ("low",))

    def _show_alert_popup(self, new_rows, total_low):
        self._alert_popup_open = True
        win = tk.Toplevel(self)
        win.title("🔔 تنبيه نواقص المخزون")
        win.configure(bg=BG)
        win.transient(self)
        win.lift()

        def close():
            self._alert_popup_open = False
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close)
        fr = ttk.Frame(win, padding=16)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text=f"وصل {len(new_rows)} صنف إلى حد التنبيه", style="Title.TLabel").pack(anchor="e")
        ttk.Label(fr, text=f"إجمالي النواقص الحالية: {total_low}", style="Sub.TLabel").pack(anchor="e", pady=(0, 8))
        t = self._alert_tree(fr, height=min(max(len(new_rows), 3), 8))
        self._alert_fill(t, new_rows)
        btns = ttk.Frame(fr)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="📤 إرسال واتساب لمسؤول المشتريات", style="Success.TButton",
                   command=lambda: self._send_shortage_whatsapp([r["id"] for r in new_rows], win)).pack(side="right", padx=4)
        ttk.Button(btns, text="عرض كل النواقص", command=lambda: (close(), self.alerts_window())).pack(side="right", padx=4)
        ttk.Button(btns, text="إغلاق", command=close).pack(side="left", padx=4)
        self.autosize(win, fr, 780)
        try:
            self.bell()
        except tk.TclError:
            pass

    def alerts_window(self):
        if not self.can("shortage"):
            return
        win = tk.Toplevel(self)
        win.title("نواقص المخزون (حسب حد التنبيه)")
        win.configure(bg=BG)
        self.center(win, 1000, 620)
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="الأصناف التي وصلت حد التنبيه", style="Title.TLabel").pack(anchor="e")
        ttk.Label(body, text="حدد صفوفًا لإرسالها فقط، أو اتركها بدون تحديد لإرسال الكل. حد التنبيه يُحدَّد لكل صنف من (تعديل الصنف) أو من زر (حد التنبيه للمحدد) في المخزون.",
                  style="Sub.TLabel", wraplength=900, justify="right").pack(anchor="e")
        t = self._alert_tree(body)
        t.configure(selectmode="extended")

        def load():
            with connect() as c:
                rows = low_stock_rows(c)
            self._alert_fill(t, rows)
            self._update_alert_button(len(rows))

        def ids():
            sel = t.selection()
            return [int(i) for i in (sel or t.get_children())]

        def copy_text():
            if not ids():
                return
            self.clipboard_clear()
            self.clipboard_append(self.shortage_message(ids()))
            messagebox.showinfo("تم", "تم نسخ القائمة. الصقها في أي محادثة (Ctrl+V).", parent=win)

        ttk.Button(bar, text="📤 إرسال واتساب لمسؤول المشتريات", style="Success.TButton",
                   command=lambda: self._send_shortage_whatsapp(ids(), win)).pack(side="right", padx=4)
        ttk.Button(bar, text="📋 نسخ النص", command=copy_text).pack(side="right", padx=4)
        ttk.Button(bar, text="📝 طلب شراء من المورد", command=lambda: (win.destroy(), self.po_page())).pack(side="right", padx=4)
        ttk.Button(bar, text="🔄 تحديث", command=load).pack(side="left", padx=4)
        load()

    def _send_shortage_whatsapp(self, item_ids, parent=None):
        item_ids = list(item_ids)
        if not item_ids:
            messagebox.showwarning("تنبيه", "لا توجد أصناف لإرسالها", parent=parent or self)
            return
        text = self.shortage_message(item_ids)
        phone = normalize_phone(setting("purchasing_phone"))
        if len(phone) < 9:
            ph = simpledialog.askstring("مسؤول المشتريات", "رقم واتساب مسؤول المشتريات:", parent=parent or self) or ""
            phone = normalize_phone(ph)
            if len(phone) < 9:
                messagebox.showwarning("تنبيه", "رقم الجوال غير صحيح", parent=parent or self)
                return
            if self.role == "admin":
                setsetting("purchasing_phone", phone)
        self._open_whatsapp(phone, text, parent)

    def set_min_qty(self, table):
        sel = table.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "حدد صنفًا أو أكثر أولًا")
            return
        s = simpledialog.askstring("حد التنبيه",
                                   f"حد التنبيه للأصناف المحددة ({len(sel)}):\n"
                                   "• يُنبَّه مسؤول المشتريات عندما تصل الكمية لهذا الرقم أو أقل\n"
                                   "• 0 = عند النفاد فقط\n"
                                   "• اتركه فارغًا لإلغاء التنبيه", parent=self)
        if s is None:
            return
        s = s.strip()
        if s != "" and not re.fullmatch(r"\d+", s):
            messagebox.showwarning("تنبيه", "اكتب رقمًا صحيحًا (مثل 5) أو اتركه فارغًا")
            return
        val_ = None if s == "" else int(s)
        with connect() as c:
            for iid in sel:
                c.execute("UPDATE items SET min_qty=? WHERE id=?", (val_, int(iid)))
        self.inventory()
        self.check_stock_alerts()

    # ------------------------------------------------------------- المنتجات المركّبة
    def bundles_page(self):
        if not (self.role == "admin" or self.can("inv_edit")):
            return
        self.clear("bundles")
        self.page_title("المنتجات المركّبة", "منتج يتكوّن من صنفين أو أكثر؛ عند بيعه يُخصم كل صنف من المخزون تلقائيًا")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=6)
        t = make_tree(self.body, ("code", "name", "parts", "price", "avail"),
                      {"code": "الرمز", "name": "اسم المنتج", "parts": "مكوّناته", "price": "سعر البيع", "avail": "المتوفر للبيع"},
                      {"name": 220, "parts": 440, "avail": 110})

        def load():
            clear_tree(t)
            with connect() as c:
                for b in c.execute("SELECT * FROM bundles WHERE COALESCE(active,1)=1 ORDER BY id DESC").fetchall():
                    comps = bundle_components(c, b["id"])
                    parts = " + ".join(x["part"] + (f" ×{x['comp_qty']}" if x["comp_qty"] != 1 else "") for x in comps)
                    av = bundle_available(comps)
                    add_row(t, (b["code"], b["name"], parts, sar(num(b["retail"])), av), iid=str(b["id"]), extra=("out",) if av <= 0 else ())

        def sel_id():
            s = t.selection()
            if not s:
                messagebox.showwarning("تنبيه", "حدد منتجًا مركّبًا أولًا")
                return None
            return int(s[0])

        def edit():
            i = sel_id()
            if i:
                self.bundle_dialog(i, on_done=load)

        def delete():
            i = sel_id()
            if i and messagebox.askyesno("تأكيد", "حذف هذا المنتج المركّب؟ (الفواتير السابقة لا تتأثر، والأصناف نفسها لا تُحذف)"):
                with connect() as c:
                    c.execute("UPDATE bundles SET active=0 WHERE id=?", (i,))
                load()

        ttk.Button(row, text="＋ منتج مركّب جديد", style="Accent.TButton", command=lambda: self.bundle_dialog(None, on_done=load)).pack(side="right", padx=4)
        ttk.Button(row, text="✎ تعديل", command=edit).pack(side="right", padx=4)
        ttk.Button(row, text="حذف", style="Danger.TButton", command=delete).pack(side="left", padx=4)
        t.bind("<Double-1>", lambda e: edit())
        load()

    def bundle_dialog(self, bundle_id=None, on_done=None):
        editing = bundle_id is not None
        name0, price0, comps = "", "", []
        if editing:
            with connect() as c:
                b = c.execute("SELECT * FROM bundles WHERE id=?", (bundle_id,)).fetchone()
                if not b:
                    return
                name0, price0 = b["name"], b["retail"]
                comps = [{"item_id": x["item_id"], "label": f"{x['item_no']} | {x['part']}", "qty": x["comp_qty"]} for x in bundle_components(c, bundle_id)]
        win = tk.Toplevel(self)
        win.title("تعديل منتج مركّب" if editing else "منتج مركّب جديد")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="اسم المنتج المركّب").grid(row=0, column=1, sticky="e", padx=6, pady=5)
        name_e = ttk.Entry(top, justify="right")
        name_e.grid(row=0, column=0, sticky="ew", pady=5)
        name_e.insert(0, name0)
        ttk.Label(top, text="سعر البيع (للمفرد)").grid(row=1, column=1, sticky="e", padx=6, pady=5)
        price_e = ttk.Entry(top, justify="right")
        price_e.grid(row=1, column=0, sticky="ew", pady=5)
        price_e.insert(0, "" if price0 == "" else str(price0))
        ttk.Label(body, text="الأصناف داخل المنتج (صنفان على الأقل)", font=(FONT, 11, "bold")).pack(anchor="e", pady=(10, 0))
        tree = make_tree(body, ("item", "qty"), {"item": "الصنف", "qty": "الكمية داخل المنتج"}, {"item": 400}, height=6)

        def redraw():
            clear_tree(tree)
            for i, x in enumerate(comps):
                add_row(tree, (x["label"], x["qty"]), iid=str(i))

        def add_comp():
            item_id = self.pick_item(win, "اختر صنفًا للمنتج المركّب")
            if not item_id:
                return
            qn = simpledialog.askinteger("الكمية", "كم قطعة من هذا الصنف داخل المنتج؟", parent=win, minvalue=1, maxvalue=1000, initialvalue=1)
            if not qn:
                return
            with connect() as c:
                r = c.execute("SELECT item_no,part FROM items WHERE id=?", (item_id,)).fetchone()
            for x in comps:
                if x["item_id"] == item_id:
                    x["qty"] += qn
                    break
            else:
                comps.append({"item_id": item_id, "label": f"{r['item_no']} | {r['part']}", "qty": qn})
            redraw()

        def remove_comp():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد الصنف المراد حذفه", parent=win)
                return
            comps.pop(int(sel[0]))
            redraw()

        btn_row = ttk.Frame(body)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="＋ إضافة صنف", style="Accent.TButton", command=add_comp).pack(side="right", padx=4)
        ttk.Button(btn_row, text="حذف المحدد", command=remove_comp).pack(side="right", padx=4)

        def save():
            name = clean_name(name_e.get())
            price = num(price_e.get())
            try:
                if not name:
                    raise ValueError("اكتب اسم المنتج المركّب")
                if price <= 0:
                    raise ValueError("اكتب سعر البيع")
                if len(comps) < 2:
                    raise ValueError("المنتج المركّب لازم يحتوي صنفين على الأقل")
                with connect() as c:
                    if c.execute("SELECT 1 FROM bundles WHERE name=? COLLATE NOCASE AND COALESCE(active,1)=1 AND id<>?", (name, bundle_id or 0)).fetchone():
                        raise ValueError("يوجد منتج مركّب بنفس الاسم")
                    if editing:
                        c.execute("UPDATE bundles SET name=?,retail=? WHERE id=?", (name, price, bundle_id))
                        c.execute("DELETE FROM bundle_items WHERE bundle_id=?", (bundle_id,))
                        bid = bundle_id
                    else:
                        bid = c.execute("INSERT INTO bundles(code,name,retail,active) VALUES(?,?,?,1)", (next_bundle_code(c), name, price)).lastrowid
                    for x in comps:
                        c.execute("INSERT INTO bundle_items(bundle_id,item_id,qty) VALUES(?,?,?)", (bid, x["item_id"], x["qty"]))
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            win.destroy()
            if on_done:
                on_done()

        ttk.Button(bar, text="💾  حفظ المنتج المركّب", style="Accent.TButton", command=save).pack(ipadx=30, ipady=3)
        redraw()
        self.dialog_size(win, body, bar, 700)

    def shortage_message(self, item_ids, need=None):
        need = need or {}
        ids = [int(i) for i in item_ids]
        if not ids:
            return ""
        with connect() as c:
            marks = ",".join("?" * len(ids))
            rows = c.execute(f"SELECT * FROM items WHERE id IN ({marks}) ORDER BY COALESCE(NULLIF(supplier,''),'~'), item_no", ids).fetchall()
        RLM = "\u200f"
        sep = "━━━━━━━━━━━━━━"
        out = []

        def add(text=""):
            out.append(RLM + text if text else "")

        add("*🔑 العباد للمفاتيح*")
        add("📦 *طلب شراء — نواقص المخزون*")
        add(f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d')}")
        officer = setting("purchasing_name")
        if officer:
            add(f"👤 إلى: {officer}")
        add(f"عدد الأصناف: {len(rows)}")
        current = object()
        for r in rows:
            rep_name = r["supplier"] or ""
            if rep_name != current:
                current = rep_name
                add()
                add(sep)
                add(f"🏭 *المورد: {rep_name}*" if rep_name else "🏭 *بدون مورد محدد*")
                add(sep)
            add(f"🔹 رقم القطعة: {r['part'] or '-'}")
            desc = " — ".join(x for x in (r["category"], r["car"]) if x)
            if desc:
                add(f"   الوصف: {desc}")
            if r["rep_code"]:
                add(f"   🏷 رمز المنتج عند المورد: {r['rep_code']}")
            add(f"   المتوفر الآن: {r['qty'] or 0}")
            n = need.get(str(r["id"]))
            if n:
                add(f"   المطلوب: {n}")
            add()
        add("شكرًا 🙏")
        return "\n".join(out)

    def shortage_window(self, rep=None):
        if not self.can("shortage"):
            return
        win = tk.Toplevel(self)
        win.title("نواقص المخزون وإرسالها لمسؤول المشتريات")
        win.configure(bg=BG)
        self.center(win, 1120, 720)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="نواقص المخزون", style="Title.TLabel").pack(anchor="e")
        ttk.Label(body, text="اختر المورد لتجمع نواقصه برموز منتجاته عنده. حدّد صفوفًا معينة لإرسالها فقط، أو اتركها بدون تحديد لإرسال الكل.", style="Sub.TLabel").pack(anchor="e")

        with connect() as c:
            reps = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
        top = ttk.LabelFrame(body, text="التصفية", padding=10)
        top.pack(fill="x", pady=8)
        ttk.Label(top, text="المورد").grid(row=0, column=5, padx=6)
        rep_cb = ttk.Combobox(top, values=["الكل", "بدون مورد"] + reps, state="readonly", width=24)
        rep_cb.set(rep if rep in reps else "الكل")
        rep_cb.grid(row=0, column=4, padx=6)
        ttk.Label(top, text="الكمية أقل من أو تساوي").grid(row=0, column=3, padx=6)
        thr = ttk.Entry(top, width=6, justify="center")
        thr.insert(0, "0")
        thr.grid(row=0, column=2, padx=6)
        ttk.Label(top, text="(0 = النافد فقط، 5 = النافد والمنخفض)", style="Muted.TLabel").grid(row=0, column=1, padx=6)

        officer_var = tk.StringVar(value="")
        count_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=officer_var, style="Muted.TLabel").pack(anchor="e")
        cols = ("item_no", "part", "car", "category", "qty", "need", "rep", "rep_code")
        t = make_tree(body, cols, {"item_no": "رقم الصنف", "part": "رقم القطعة", "car": "السيارة", "category": "النوع", "qty": "المتوفر",
                                   "need": "المطلوب", "rep": "المورد", "rep_code": "رمز المنتج عند المورد"},
                      {"car": 160, "rep": 150, "rep_code": 190, "item_no": 120})
        t.configure(selectmode="extended")
        ttk.Label(body, textvariable=count_var, style="Muted.TLabel").pack(anchor="e")
        need = {}

        def refresh_officer():
            name, phone = setting("purchasing_name"), setting("purchasing_phone")
            officer_var.set(f"مسؤول المشتريات: {name or 'غير محدد'}   |   واتساب: {phone or 'لم يُحدد رقمه بعد'}")

        def load(*_):
            try:
                limit = int(num(thr.get()))
            except Exception:
                limit = 0
            sql = "SELECT * FROM items WHERE COALESCE(qty,0)<=?"
            params = [limit]
            if rep_cb.get() == "بدون مورد":
                sql += " AND COALESCE(supplier,'')=''"
            elif rep_cb.get() != "الكل":
                sql += " AND supplier=?"
                params.append(rep_cb.get())
            sql += " ORDER BY COALESCE(NULLIF(supplier,''),'~'), item_no"
            with connect() as c:
                rows = c.execute(sql, params).fetchall()
            clear_tree(t)
            for r in rows:
                q_ = r["qty"] or 0
                add_row(t, (r["item_no"], r["part"], r["car"], r["category"], q_, need.get(str(r["id"]), ""), r["supplier"] or "", r["rep_code"] or ""),
                        iid=str(r["id"]), extra=("out",) if q_ <= 0 else ("low",))
            count_var.set(f"عدد الأصناف: {len(rows)}   (انقر مرتين على صنف لتحديد الكمية المطلوبة منه)")

        def current_ids():
            sel = t.selection()
            return list(sel) if sel else list(t.get_children())

        def set_need(_e=None):
            sel = t.selection()
            if not sel:
                return
            n = simpledialog.askinteger("الكمية المطلوبة", "كم تريد أن تطلب من هذا الصنف؟ (0 لإلغاء)", parent=win, minvalue=0, maxvalue=100000)
            if n is None:
                return
            if n:
                need[sel[0]] = n
            else:
                need.pop(sel[0], None)
            load()

        def copy_text():
            ids = current_ids()
            if not ids:
                messagebox.showwarning("تنبيه", "لا توجد أصناف", parent=win)
                return
            self.clipboard_clear()
            self.clipboard_append(self.shortage_message(ids, need))
            messagebox.showinfo("تم", "تم نسخ القائمة. الصقها في أي محادثة (Ctrl+V).", parent=win)

        def send():
            ids = current_ids()
            if not ids:
                messagebox.showwarning("تنبيه", "لا توجد أصناف لإرسالها", parent=win)
                return
            text = self.shortage_message(ids, need)
            phone = normalize_phone(setting("purchasing_phone"))
            if len(phone) < 9:
                ph = simpledialog.askstring("مسؤول المشتريات", "رقم واتساب مسؤول المشتريات:", parent=win) or ""
                phone = normalize_phone(ph)
                if len(phone) < 9:
                    messagebox.showwarning("تنبيه", "رقم الجوال غير صحيح", parent=win)
                    return
                if self.role == "admin":
                    setsetting("purchasing_phone", phone)
                    refresh_officer()
            enc = urllib.parse.quote(text)
            if len(enc) > 1900:
                # رابط واتساب له حد للطول: نسخ القائمة ونفتح المحادثة فقط
                self.clipboard_clear()
                self.clipboard_append(text)
                webbrowser.open("https://wa.me/" + phone)
                messagebox.showinfo("تم نسخ القائمة", "القائمة طويلة على رابط واتساب، فنسختها لك.\nالصقها في المحادثة (Ctrl+V) ثم أرسلها.", parent=win)
            else:
                webbrowser.open("https://wa.me/" + phone + "?text=" + enc)

        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="📤 إرسال واتساب لمسؤول المشتريات", style="Success.TButton", command=send).pack(side="right", padx=4)
        ttk.Button(bar, text="📋 نسخ النص", command=copy_text).pack(side="right", padx=4)
        ttk.Button(bar, text="✎ تحديد الكمية المطلوبة", command=set_need).pack(side="right", padx=4)
        if self.role == "admin":
            ttk.Button(bar, text="⚙ مسؤول المشتريات", command=lambda: self.purchasing_dialog(refresh_officer)).pack(side="left", padx=4)
        ttk.Button(top, text="🔄 تحديث", style="Accent.TButton", command=load).grid(row=0, column=0, padx=6)
        rep_cb.bind("<<ComboboxSelected>>", load)
        thr.bind("<Return>", load)
        t.bind("<Double-1>", set_need)
        refresh_officer()
        load()

    def purchasing_dialog(self, on_done=None):
        def save(d):
            phone = normalize_phone(d["phone"])
            if d["phone"] and len(phone) < 9:
                raise ValueError("رقم الجوال غير صحيح")
            setsetting("purchasing_name", d["name"])
            setsetting("purchasing_phone", phone)

        self.form("مسؤول المشتريات", [
            ("name", "اسم مسؤول المشتريات", setting("purchasing_name")),
            ("phone", "رقم واتساب (مثال 0501234567)", setting("purchasing_phone")),
        ], save, on_done=on_done)

    def backup_full(self):
        dest = filedialog.asksaveasfilename(defaultextension=".zip", initialfile="نسخة_كاملة_العباد.zip", filetypes=[("Zip", "*.zip")])
        if not dest:
            return
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(DB, "alabbad_keys_new.db")
            if os.path.isdir(IMG_DIR):
                for f in os.listdir(IMG_DIR):
                    z.write(os.path.join(IMG_DIR, f), "alabbad_item_images_new/" + f)
        messagebox.showinfo("تم", "تم حفظ نسخة كاملة (قاعدة البيانات + صور المنتجات)")

    # ------------------------------------------------------------- طلبات الشراء من الموردين
    def _open_whatsapp(self, phone, text, parent=None):
        enc = urllib.parse.quote(text)
        if len(enc) > 1900:
            # رابط واتساب له حد للطول: ننسخ النص ونفتح المحادثة فقط
            self.clipboard_clear()
            self.clipboard_append(text)
            webbrowser.open("https://wa.me/" + phone)
            messagebox.showinfo("تم نسخ الطلب", "الطلب طويل على رابط واتساب، فنسخته لك.\nالصقه في المحادثة (Ctrl+V) ثم أرسله.", parent=parent or self)
        else:
            webbrowser.open("https://wa.me/" + phone + "?text=" + enc)

    def _save_po(self, rep_name, lines, note, status):
        with connect() as c:
            today = datetime.now().strftime("%y%m%d")
            n = c.execute("SELECT COUNT(*) FROM purchase_orders WHERE po_no LIKE ?", (f"PO{today}-%",)).fetchone()[0] + 1
            po_no = f"PO{today}-{n:03d}"
            while c.execute("SELECT 1 FROM purchase_orders WHERE po_no=?", (po_no,)).fetchone():
                n += 1
                po_no = f"PO{today}-{n:03d}"
            cur = c.execute("INSERT INTO purchase_orders(po_no,created_at,created_by,rep_name,note,status) VALUES(?,?,?,?,?,?)",
                            (po_no, now_str(), self.user, rep_name, note, status))
            for ln in lines:
                c.execute("INSERT INTO po_lines(po_id,item_id,name,part,rep_code,qty) VALUES(?,?,?,?,?,?)",
                          (cur.lastrowid, ln["id"], ln["name"], ln["part"], ln["code"], ln["qty"]))
            return cur.lastrowid, po_no

    def po_message(self, po_id, to_manager=False):
        """رسالة قصيرة: سطر (اسم المنتج + رقمه عند المورد) وتحته الكمية."""
        with connect() as c:
            po = c.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
            lines = c.execute("""
                SELECT l.*, i.category AS cat, i.model AS mdl, i.car AS car_name
                FROM po_lines l LEFT JOIN items i ON i.id=l.item_id
                WHERE l.po_id=? ORDER BY l.id
            """, (po_id,)).fetchall()
        if not po:
            return ""
        RLM = "\u200f"  # يمنع اختلاط الأرقام مع الكلام العربي
        out = []

        def add(text=""):
            out.append(RLM + text if text else "")

        if to_manager:
            add(f"طلب شراء من {po['created_by']} — المورد: {po['rep_name']}")
            add("للمراجعة ثم الإرسال للمورد")
        else:
            add("السلام عليكم")
        add()
        for l in lines:
            short = " ".join(x for x in (l["cat"], l["mdl"] or l["car_name"]) if x) or (l["name"] or "")
            ident = l["rep_code"] or l["part"] or ""
            add(f"({short}) {ident}".strip())
            add(f"الكمية: {l['qty']}")
            add()
        if po["note"]:
            add(f"ملاحظة: {po['note']}")
        return "\n".join(out).rstrip()

    def _supplier_phone_for_send(self, rep_name):
        """رقم المورد للإرسال المباشر؛ إذا لم يكن مسجلًا يُطلب من المدير ويُحفظ."""
        with connect() as c:
            r = c.execute("SELECT phone FROM suppliers WHERE name=?", (rep_name,)).fetchone()
        phone = normalize_phone(r["phone"] if r else "")
        if len(phone) >= 9:
            return phone
        ph = simpledialog.askstring("جوال المورد", f"رقم واتساب المورد {rep_name}:", parent=self) or ""
        phone = normalize_phone(ph)
        if len(phone) < 9:
            messagebox.showwarning("تنبيه", "رقم الجوال غير صحيح")
            return ""
        with connect() as c:
            c.execute("UPDATE suppliers SET phone=? WHERE name=?", (phone, rep_name))
        return phone

    def po_page(self):
        if not self.can("po"):
            return
        self.clear("po")
        is_admin = self.role == "admin"
        self.page_title("طلب شراء من المورد", "اختر المورد ← أضف الأصناف والكميات ← أصدر الطلب وأرسله واتساب")
        nb = ttk.Notebook(self.body)
        nb.pack(fill="both", expand=True)
        tab1 = ttk.Frame(nb, padding=10)
        tab2 = ttk.Frame(nb, padding=10)
        nb.add(tab1, text="＋ طلب شراء جديد")
        nb.add(tab2, text="الطلبات السابقة")

        # ---------- الشريط السفلي الثابت (ملاحظات + زر الإصدار) يبقى ظاهرًا دائمًا
        bar = ttk.Frame(tab1)
        bar.pack(side="bottom", fill="x", pady=(6, 0))
        nrow = ttk.Frame(bar)
        nrow.pack(fill="x")
        ttk.Label(nrow, text="ملاحظات (اختياري)").pack(side="right", padx=4)
        note = ttk.Entry(nrow, width=60, justify="right")
        note.pack(side="right", padx=4)
        total_var = tk.StringVar(value="عدد الأصناف: 0   |   إجمالي الكمية: 0")
        ttk.Label(bar, textvariable=total_var, font=(FONT, 12, "bold"), foreground=NAVY).pack(anchor="e", pady=2)
        brow = ttk.Frame(bar)
        brow.pack(fill="x", pady=4)
        issue_text = "📤  إصدار طلب الشراء وإرساله للمورد (واتساب)" if is_admin else "📤  إصدار الطلب وإرساله لجوال المدير (واتساب)"
        ttk.Button(brow, text=issue_text, style="Success.TButton", command=lambda: issue()).pack(side="right", ipadx=16, ipady=5)
        if is_admin:
            ttk.Button(brow, text="⚙ جوال المدير لاستلام طلبات الموظفين", command=lambda: self.manager_phone_dialog(refresh_dest)).pack(side="left")

        with connect() as c:
            reps = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
        top = ttk.Frame(tab1)
        top.pack(fill="x")
        ttk.Label(top, text="المورد").pack(side="right", padx=4)
        rep_cb = ttk.Combobox(top, values=reps, state="readonly", width=26)
        rep_cb.pack(side="right", padx=4)
        all_var = tk.IntVar(value=0)
        ttk.Checkbutton(top, text="إظهار كل الأصناف (حتى من موردين آخرين)", variable=all_var, command=lambda: load_items()).pack(side="right", padx=12)
        ttk.Label(top, text="بحث").pack(side="right", padx=4)
        flt = ttk.Entry(top, width=18, justify="right")
        flt.pack(side="right", padx=4)

        with connect() as c:
            type_vals = ["الكل"] + [r["name"] for r in c.execute("SELECT name FROM item_types ORDER BY name").fetchall()]
            make_vals = ["الكل"] + [r["name"] for r in c.execute("SELECT name FROM car_makes ORDER BY name").fetchall()]
        top2 = ttk.Frame(tab1)
        top2.pack(fill="x", pady=4)
        ttk.Label(top2, text="نوع القطعة").pack(side="right", padx=4)
        cat_f = ttk.Combobox(top2, values=type_vals, state="readonly", width=16)
        cat_f.set("الكل")
        cat_f.pack(side="right", padx=4)
        ttk.Label(top2, text="نوع السيارة (الشركة)").pack(side="right", padx=4)
        make_f = ttk.Combobox(top2, values=make_vals, state="readonly", width=16)
        make_f.set("الكل")
        make_f.pack(side="right", padx=4)
        ttk.Label(top2, text="الموديل").pack(side="right", padx=4)
        model_f = ttk.Combobox(top2, values=["الكل"], state="readonly", width=16)
        model_f.set("الكل")
        model_f.pack(side="right", padx=4)
        dest_var = tk.StringVar(value="")
        ttk.Label(tab1, textvariable=dest_var, style="Muted.TLabel").pack(anchor="e", pady=2)
        if not reps:
            ttk.Label(tab1, text="لا يوجد موردون مسجّلون. أضفهم من صفحة (الموردون) أولًا.", foreground=AMBER).pack(anchor="e")

        ttk.Label(tab1, text="أصناف المورد — انقر مرتين على الصنف لتحديد الكمية وإضافته للطلب", font=(FONT, 11, "bold")).pack(anchor="e")
        av = make_tree(tab1, ("item_no", "name", "part", "code", "qty"),
                       {"item_no": "رقم الصنف", "name": "اسم المنتج", "part": "رقم القطعة", "code": "رقم المنتج عند المورد", "qty": "المتوفر"},
                       {"name": 300, "code": 180}, height=5)
        av.configure(selectmode="extended")
        addrow = ttk.Frame(tab1)
        addrow.pack(fill="x", pady=4)
        ttk.Label(addrow, text="الكمية المطلوبة").pack(side="right", padx=4)
        qty_e = ttk.Entry(addrow, width=8, justify="center")
        qty_e.insert(0, "1")
        qty_e.pack(side="right", padx=4)
        ttk.Button(addrow, text="＋ إضافة المحدد للطلب", style="Accent.TButton", command=lambda: add_selected()).pack(side="right", padx=6)
        ttk.Button(addrow, text="＋ إضافة نواقص المورد", command=lambda: add_shortage()).pack(side="right", padx=6)

        ttk.Label(tab1, text="أصناف الطلب", font=(FONT, 11, "bold")).pack(anchor="e")
        lt = make_tree(tab1, ("name", "code", "part", "qty"),
                       {"name": "اسم المنتج", "code": "رقم المنتج عند المورد", "part": "رقم القطعة", "qty": "الكمية المطلوبة"},
                       {"name": 300, "code": 180}, height=5)
        lrow = ttk.Frame(tab1)
        lrow.pack(fill="x")
        ttk.Button(lrow, text="حذف السطر المحدد", command=lambda: remove_line()).pack(side="right", padx=4)
        ttk.Label(lrow, text="(انقر مرتين على سطر لتعديل كميته)", style="Muted.TLabel").pack(side="right", padx=6)

        lines = []
        state = {"rep": ""}

        def refresh_dest():
            if is_admin:
                phone = ""
                if rep_cb.get():
                    with connect() as c:
                        r = c.execute("SELECT phone FROM suppliers WHERE name=?", (rep_cb.get(),)).fetchone()
                    phone = r["phone"] if r else ""
                dest_var.set(f"سيُرسل مباشرة إلى المورد: {rep_cb.get() or '—'}   |   جواله: {phone or 'غير مسجّل (سأطلبه منك عند الإرسال)'}")
            else:
                mp = setting("manager_phone")
                dest_var.set(f"سيُرسل إلى جوال المدير ({mp or 'غير محدد — اطلب من المدير إضافته'}) ليراجعه ويرسله للمورد")

        def load_items(*_):
            clear_tree(av)
            rp = rep_cb.get()
            if not all_var.get() and not rp:
                return
            term = "%" + flt.get().strip() + "%"
            sql = """SELECT i.*, COALESCE(NULLIF(m.code,''), i.rep_code) AS sup_code FROM items i
                     LEFT JOIN item_supplier_codes m ON m.item_id=i.id AND m.supplier=?
                     WHERE (COALESCE(i.part,'') LIKE ? OR COALESCE(i.car,'') LIKE ? OR COALESCE(i.rep_code,'') LIKE ? OR COALESCE(i.item_no,'') LIKE ? OR COALESCE(m.code,'') LIKE ?)"""
            params = [rp] + [term] * 5
            if not all_var.get():
                sql += " AND (i.supplier=? OR m.id IS NOT NULL OR EXISTS(SELECT 1 FROM purchases p WHERE p.item_id=i.id AND p.supplier=?))"
                params.extend([rp, rp])
            if cat_f.get() != "الكل":
                sql += " AND i.category=?"
                params.append(cat_f.get())
            if make_f.get() != "الكل":
                sql += " AND i.make=?"
                params.append(make_f.get())
            if model_f.get() != "الكل":
                sql += " AND i.model=?"
                params.append(model_f.get())
            sql += " ORDER BY i.item_no LIMIT 300"
            with connect() as c:
                rows = c.execute(sql, params).fetchall()
            for r in rows:
                q_ = r["qty"] or 0
                add_row(av, (r["item_no"], item_display_name(r), r["part"], r["sup_code"] or "", q_), iid=str(r["id"]),
                        extra=("out",) if q_ <= 0 else (("low",) if q_ <= 5 else ()))

        def redraw():
            clear_tree(lt)
            for i, ln in enumerate(lines):
                add_row(lt, (ln["name"], ln["code"], ln["part"], ln["qty"]), iid=str(i))
            total_var.set(f"عدد الأصناف: {len(lines)}   |   إجمالي الكمية: {sum(x['qty'] for x in lines)}")

        def add_line(r, q):
            for ln in lines:
                if ln["id"] == r["id"]:
                    ln["qty"] += q
                    return
            lines.append({"id": r["id"], "name": item_display_name(r), "part": r["part"] or "", "code": self._supplier_code(r["id"], rep_cb.get()) or r["rep_code"] or "", "qty": q})

        def read_qty():
            q = int(num(qty_e.get()))
            if q <= 0:
                messagebox.showwarning("تنبيه", "اكتب كمية أكبر من صفر")
                return 0
            return q

        def add_selected():
            sel = av.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد صنفًا أو أكثر من القائمة أولًا")
                return
            q = read_qty()
            if not q:
                return
            with connect() as c:
                for iid in sel:
                    r = c.execute("SELECT * FROM items WHERE id=?", (int(iid),)).fetchone()
                    if r:
                        add_line(r, q)
            redraw()

        def add_shortage():
            if not rep_cb.get():
                messagebox.showwarning("تنبيه", "اختر المورد أولًا")
                return
            q = read_qty()
            if not q:
                return
            with connect() as c:
                rows = c.execute("SELECT * FROM items WHERE (supplier=? OR EXISTS(SELECT 1 FROM purchases p WHERE p.item_id=items.id AND p.supplier=?)) AND COALESCE(qty,0)<=0 ORDER BY item_no", (rep_cb.get(), rep_cb.get())).fetchall()
            if not rows:
                messagebox.showinfo("تنبيه", "لا توجد أصناف نافدة لهذا المورد")
                return
            for r in rows:
                add_line(r, q)
            redraw()

        def remove_line():
            sel = lt.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد السطر المراد حذفه")
                return
            lines.pop(int(sel[0]))
            redraw()

        def edit_qty(_e=None):
            sel = lt.selection()
            if not sel:
                return
            ln = lines[int(sel[0])]
            n = simpledialog.askinteger("تعديل الكمية", f"الكمية المطلوبة من {ln['name']}:", parent=self, minvalue=1, maxvalue=100000, initialvalue=ln["qty"])
            if n:
                ln["qty"] = n
                redraw()

        def on_rep(_e=None):
            if lines and rep_cb.get() != state["rep"]:
                if not messagebox.askyesno("تغيير المورد", "تغيير المورد سيفرغ أصناف الطلب الحالي. متابعة؟"):
                    rep_cb.set(state["rep"])
                    return
                lines.clear()
                redraw()
            state["rep"] = rep_cb.get()
            refresh_dest()
            load_items()

        def issue():
            rp = rep_cb.get()
            if not rp:
                messagebox.showwarning("تنبيه", "اختر المورد أولًا")
                return
            if not lines:
                messagebox.showwarning("تنبيه", "أضف صنفًا واحدًا على الأقل للطلب")
                return
            if is_admin:
                phone = self._supplier_phone_for_send(rp)
                if not phone:
                    return
                status = "sent"
                target = f"المورد {rp}"
            else:
                phone = normalize_phone(setting("manager_phone"))
                if len(phone) < 9:
                    messagebox.showwarning("تنبيه", "المدير لم يحدد رقم جواله بعد.\nاطلب منه إضافته من الإعدادات.")
                    return
                status = "pending"
                target = "جوال المدير"
            if not messagebox.askyesno("تأكيد", f"سيتم إصدار طلب شراء ({len(lines)} صنف) وفتح واتساب لإرساله إلى {target}. متابعة؟"):
                return
            po_id, po_no = self._save_po(rp, lines, note.get().strip(), status)
            self._open_whatsapp(phone, self.po_message(po_id, to_manager=not is_admin))
            messagebox.showinfo("تم", f"تم إصدار طلب الشراء رقم {po_no}.\nاضغط (إرسال) في واتساب لإتمام الإرسال.")
            self.po_page()

        def add_prompt(_e=None):
            sel = av.selection()
            if not sel:
                return
            with connect() as c:
                r = c.execute("SELECT * FROM items WHERE id=?", (int(sel[0]),)).fetchone()
            if not r:
                return
            q = simpledialog.askinteger("الكمية المطلوبة", f"كم تريد أن تطلب من:\n{item_display_name(r)}\nرقمه عند المورد: {self._supplier_code(r['id'], rep_cb.get()) or '-'}",
                                        parent=self, minvalue=1, maxvalue=100000, initialvalue=1)
            if q:
                add_line(r, q)
                redraw()

        def on_make(_e=None):
            models = ["الكل"]
            if make_f.get() != "الكل":
                with connect() as c:
                    models += [r["name"] for r in c.execute(
                        "SELECT m.name FROM car_models m JOIN car_makes k ON k.id=m.make_id WHERE k.name=? ORDER BY m.name", (make_f.get(),)).fetchall()]
            model_f.configure(values=models)
            model_f.set("الكل")
            load_items()

        def reset_filters():
            cat_f.set("الكل")
            make_f.set("الكل")
            model_f.configure(values=["الكل"])
            model_f.set("الكل")
            load_items()

        ttk.Button(top2, text="مسح الفلاتر", command=reset_filters).pack(side="left", padx=4)
        cat_f.bind("<<ComboboxSelected>>", load_items)
        make_f.bind("<<ComboboxSelected>>", on_make)
        model_f.bind("<<ComboboxSelected>>", load_items)
        av.bind("<Double-1>", add_prompt)
        rep_cb.bind("<<ComboboxSelected>>", on_rep)
        flt.bind("<KeyRelease>", load_items)
        lt.bind("<Double-1>", edit_qty)
        refresh_dest()

        # ---------- الطلبات السابقة
        bar2 = ttk.Frame(tab2)
        bar2.pack(fill="x")
        cols = ("po_no", "date", "rep", "by", "items", "qty", "status")
        t2 = make_tree(tab2, cols, {"po_no": "رقم الطلب", "date": "التاريخ", "rep": "المورد", "by": "أصدره", "items": "الأصناف", "qty": "إجمالي الكمية", "status": "الحالة"},
                       {"po_no": 150, "date": 150, "status": 230})
        own = "" if is_admin else self.user
        st_ar = {"pending": "⏳ بانتظار إرسال المدير للمورد", "sent": "✅ أُرسل للمورد"}

        def load2():
            with connect() as c:
                rows = c.execute("""
                    SELECT p.*,(SELECT COUNT(*) FROM po_lines l WHERE l.po_id=p.id) n,
                    (SELECT COALESCE(SUM(qty),0) FROM po_lines l WHERE l.po_id=p.id) q
                    FROM purchase_orders p WHERE (?='' OR p.created_by=?) ORDER BY p.id DESC LIMIT 300
                """, (own, own)).fetchall()
            clear_tree(t2)
            for r in rows:
                add_row(t2, (r["po_no"], str(r["created_at"])[:16], r["rep_name"], r["created_by"], r["n"], r["q"], st_ar.get(r["status"], r["status"])),
                        iid=str(r["id"]), extra=("low",) if r["status"] == "pending" else ())
            self.refresh_badges()

        def sel_po():
            sel = t2.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد طلبًا أولًا")
                return None
            return int(sel[0])

        def details():
            pid = sel_po()
            if pid:
                self.po_details(pid)

        def send_to_rep():
            pid = sel_po()
            if not pid:
                return
            with connect() as c:
                po = c.execute("SELECT rep_name FROM purchase_orders WHERE id=?", (pid,)).fetchone()
            phone = self._supplier_phone_for_send(po["rep_name"])
            if not phone:
                return
            self._open_whatsapp(phone, self.po_message(pid, to_manager=False))
            with connect() as c:
                c.execute("UPDATE purchase_orders SET status='sent' WHERE id=?", (pid,))
            load2()

        def resend_manager():
            pid = sel_po()
            if not pid:
                return
            phone = normalize_phone(setting("manager_phone"))
            if len(phone) < 9:
                messagebox.showwarning("تنبيه", "المدير لم يحدد رقم جواله بعد")
                return
            self._open_whatsapp(phone, self.po_message(pid, to_manager=True))

        def delete_po():
            pid = sel_po()
            if not pid:
                return
            if not messagebox.askyesno("تأكيد", "حذف هذا الطلب نهائيًا؟"):
                return
            with connect() as c:
                c.execute("DELETE FROM po_lines WHERE po_id=?", (pid,))
                c.execute("DELETE FROM purchase_orders WHERE id=?", (pid,))
            load2()

        ttk.Button(bar2, text="👁 التفاصيل", command=details).pack(side="right", padx=4)
        if is_admin:
            ttk.Button(bar2, text="📤 إرسال للمورد (واتساب)", style="Success.TButton", command=send_to_rep).pack(side="right", padx=4)
            ttk.Button(bar2, text="حذف", style="Danger.TButton", command=delete_po).pack(side="left", padx=4)
        else:
            ttk.Button(bar2, text="📤 إعادة إرسال لجوال المدير", command=resend_manager).pack(side="right", padx=4)
        t2.bind("<Double-1>", lambda e: details())
        load2()

    def po_details(self, po_id):
        with connect() as c:
            po = c.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
            lines = c.execute("SELECT * FROM po_lines WHERE po_id=? ORDER BY id", (po_id,)).fetchall()
        if not po:
            return
        win = tk.Toplevel(self)
        win.title(f"طلب الشراء {po['po_no']}")
        win.configure(bg=BG)
        self.center(win, 860, 520)
        ttk.Label(win, text=f"طلب شراء {po['po_no']} — {po['rep_name']}", style="Title.TLabel").pack(pady=8)
        ttk.Label(win, text=f"أصدره: {po['created_by']}    |    {str(po['created_at'])[:16]}").pack()
        t = make_tree(win, ("name", "code", "part", "qty"), {"name": "اسم المنتج", "code": "رقم المنتج عند المورد", "part": "رقم القطعة", "qty": "الكمية"}, {"name": 320, "code": 200})
        for l in lines:
            add_row(t, (l["name"], l["rep_code"], l["part"], l["qty"]))
        if po["note"]:
            ttk.Label(win, text="ملاحظات: " + po["note"]).pack(pady=6)

    def manager_phone_dialog(self, on_done=None):
        def save(d):
            phone = normalize_phone(d["phone"])
            if len(phone) < 9:
                raise ValueError("رقم الجوال غير صحيح (مثال 0501234567)")
            setsetting("manager_phone", phone)

        self.form("جوال المدير", [("phone", "رقم واتساب المدير لاستلام طلبات الموظفين", setting("manager_phone"))], save, on_done=on_done)

    # ------------------------------------------------------------- استيراد فاتورة مورد من PDF
    def _save_import_invoice(self, sup, inv, date_iso, rate, factor, lines):
        """يسجّل أسطر الفاتورة كمشتريات معلّقة (المصاريف = الشحن+الضريبة−الخصم موزعة بالنسبة)."""
        with connect() as c:
            if c.execute("SELECT 1 FROM purchases WHERE batch=? AND supplier=? LIMIT 1", (inv, sup)).fetchone():
                raise ValueError("هذه الفاتورة سبق تسجيلها لنفس المورد")
            stamp = f"{date_iso} {datetime.now().strftime('%H:%M:%S')}"
            n = 0
            for ln in lines:
                q = int(round(ln["qty"]))
                if q <= 0 or not ln.get("item_id"):
                    continue
                unit = ln["price"]
                if ln.get("total"):
                    u2 = ln["total"] / q  # سعر الوحدة الدقيق من إجمالي السطر (الأسعار في الفواتير تكون مقرّبة)
                    if abs(u2 - unit) <= 0.02 * unit + 0.01:
                        unit = u2
                buy = round(unit * rate, 4)
                exp_total = round(unit * factor * rate * q, 4)
                c.execute("""INSERT INTO purchases(batch,date,item_id,supplier,qty,buy,expense,landed,status)
                             VALUES(?,?,?,?,?,?,?,?,'pending')""", (inv, stamp, ln["item_id"], sup, q, buy, exp_total, buy + exp_total / q))
                self._save_supplier_code(c, ln["item_id"], sup, ln["code"])
                n += 1
        return n

    # ------------------------------------------------------------- صور الأصناف من فاتورة (حتى لو سُجّلت سابقًا)
    def _read_invoice_pdf(self, path):
        try:
            return parse_supplier_invoice(read_pdf_words(path))
        except Exception as e:
            messagebox.showerror("تعذّرت قراءة الملف", str(e))
            return None

    def _image_plan(self, c, supplier, lines, imgs, replace):
        """يطابق أسطر الفاتورة مع الأصناف الموجودة (برمز المورد) ويحدد أين تُضاف الصورة."""
        plan = []
        for i, ln in enumerate(lines):
            item_id = self._match_supplier_line(c, supplier, ln["code"])
            row = c.execute("SELECT item_no,image FROM items WHERE id=?", (item_id,)).fetchone() if item_id else None
            has_img = bool(row and row["image"])
            img = imgs.get(i)
            if not row:
                action = "غير موجود في المخزون"
            elif not img:
                action = "لا توجد صورة في الفاتورة"
            elif has_img and not replace:
                action = "له صورة — تخطّي"
            else:
                action = "سيُستبدل" if has_img else "سيُضاف"
            plan.append({"i": i, "n": ln["n"], "code": ln["code"], "desc": ln["desc"], "item_id": item_id,
                         "item_no": row["item_no"] if row else "", "has_image": has_img, "img": img,
                         "action": action, "apply": action in ("سيُضاف", "سيُستبدل")})
        return plan

    def _apply_image_plan(self, plan):
        n = 0
        with connect() as c:
            for p in plan:
                if not p["apply"]:
                    continue
                cur = c.execute("SELECT image FROM items WHERE id=?", (p["item_id"],)).fetchone()
                c.execute("UPDATE items SET image=? WHERE id=?", (store_image(p["img"]), p["item_id"]))
                if cur and cur["image"]:
                    delete_image(cur["image"])
                n += 1
        return n

    def import_images_only(self):
        """يضيف صور فاتورة PDF للأصناف الموجودة (مفيد للفواتير القديمة التي سُجّلت بدون صور)."""
        if not (self.role == "admin" or self.can("inv_edit")):
            return
        path = filedialog.askopenfilename(parent=self, title="اختر فاتورة المورد (PDF)", filetypes=[("PDF", "*.pdf"), ("كل الملفات", "*.*")])
        if not path:
            return
        parsed = self._read_invoice_pdf(path)
        if not parsed:
            return
        if not parsed["lines"]:
            messagebox.showwarning("تنبيه", "\n".join(parsed["warnings"]) or "لم أجد أصنافًا في الملف")
            return
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            imgs = extract_pdf_row_images(path, parsed["lines"])
        except Exception:
            imgs = {}
        finally:
            self.config(cursor="")
        if not imgs:
            messagebox.showinfo("الصور", "ما وجدت صورًا داخل هذه الفاتورة (ربما هي ممسوحة ضوئيًا).")
            return
        with connect() as c:
            sups = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
        win = tk.Toplevel(self)
        win.title("🖼 صور الأصناف من فاتورة")
        win.configure(bg=BG)
        win.transient(self)
        self.center(win, 1180, 720)
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="إضافة صور الفاتورة للأصناف الموجودة", style="Title.TLabel").pack(anchor="e")
        ttk.Label(body, text=f"الملف: {os.path.basename(path)} — {len(imgs)} صورة. تُطابق الأسطر مع الأصناف برمز المنتج عند المورد.", style="Sub.TLabel").pack(anchor="e")
        top = ttk.Frame(body)
        top.pack(fill="x", pady=8)
        ttk.Label(top, text="المورد").pack(side="right", padx=4)
        sup_cb = ttk.Combobox(top, values=sups, state="readonly", width=28)
        sup_cb.pack(side="right", padx=4)
        guess = (parsed.get("supplier_guess") or "").lower()
        pre = next((sp for sp in sups if guess and (sp.lower() in guess or guess in sp.lower())), "")
        if pre:
            sup_cb.set(pre)
        ttk.Label(top, text="الأصناف التي لها صورة").pack(side="right", padx=(18, 4))
        MODES = ["لا تغيّرها (أضف للأصناف بدون صورة فقط)", "استبدلها بصور الفاتورة"]
        mode_cb = ttk.Combobox(top, values=MODES, state="readonly", width=36)
        mode_cb.set(MODES[0])
        mode_cb.pack(side="right", padx=4)
        t = make_tree(body, ("n", "code", "desc", "item", "cur", "new", "action"),
                      {"n": "#", "code": "رمز المورد", "desc": "الوصف", "item": "الصنف في المخزون", "cur": "صورته الحالية", "new": "صورة الفاتورة", "action": "الإجراء"},
                      {"n": 40, "code": 110, "desc": 340, "item": 120, "cur": 100, "new": 100, "action": 190})
        sum_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=sum_var, font=(FONT, 11, "bold"), foreground=NAVY).pack(anchor="e", pady=(0, 6))
        state = {"plan": []}

        def refresh(*_):
            with connect() as c:
                plan = self._image_plan(c, sup_cb.get().strip(), parsed["lines"], imgs, mode_cb.get() == MODES[1])
            state["plan"] = plan
            clear_tree(t)
            for p in plan:
                tag = ("best",) if p["apply"] else (("low",) if p["action"] == "غير موجود في المخزون" else ())
                add_row(t, (p["n"], p["code"], p["desc"][:70], p["item_no"] or "—", "✔" if p["has_image"] else "—", "📷" if p["img"] else "—", p["action"]), iid=str(p["i"]), extra=tag)
            n_apply = sum(1 for p in plan if p["apply"])
            sum_var.set(f"سيتم تحديث صور {n_apply} صنف   |   غير موجود في المخزون: {sum(1 for p in plan if p['action'] == 'غير موجود في المخزون')}")

        def show_img(_e=None):
            sel = t.selection()
            if not sel or int(sel[0]) not in imgs:
                return
            dlg = tk.Toplevel(win)
            dlg.title("صورة الفاتورة")
            dlg.configure(bg=BG)
            dlg.transient(win)
            ph = load_photo(imgs[int(sel[0])], (420, 420))
            lbl = ttk.Label(dlg, image=ph) if ph else ttk.Label(dlg, text="تعذّر عرض الصورة")
            lbl.image = ph
            lbl.pack(padx=14, pady=14)

        def save():
            if not sup_cb.get().strip():
                messagebox.showwarning("تنبيه", "اختر المورد أولًا (ليتم مطابقة الرموز)", parent=win)
                return
            try:
                n = self._apply_image_plan(state["plan"])
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            win.destroy()
            messagebox.showinfo("تم", f"تم تحديث صور {n} صنف.")

        ttk.Button(bar, text="💾  حفظ الصور", style="Success.TButton", command=save).pack(side="right", padx=6, ipadx=20, ipady=3)
        ttk.Button(bar, text="إغلاق", command=win.destroy).pack(side="left", padx=4)
        sup_cb.bind("<<ComboboxSelected>>", refresh)
        mode_cb.bind("<<ComboboxSelected>>", refresh)
        t.bind("<Double-1>", show_img)
        refresh()

    def import_pdf_invoice(self, on_done=None):
        if not self.can("purchases"):
            return
        path = filedialog.askopenfilename(parent=self, title="اختر فاتورة المورد (PDF)", filetypes=[("PDF", "*.pdf"), ("كل الملفات", "*.*")])
        if not path:
            return
        try:
            parsed = parse_supplier_invoice(read_pdf_words(path))
        except Exception as e:
            messagebox.showerror("تعذّرت قراءة الملف", str(e))
            return
        if not parsed["lines"]:
            messagebox.showwarning("تنبيه", "\n".join(parsed["warnings"]) or "لم أجد أصنافًا في الملف")
            return
        if parsed["warnings"]:
            messagebox.showwarning("ملاحظات على القراءة", "\n".join(parsed["warnings"]))
        self._import_review(parsed, path, on_done)

    # ------------------------------------------------------------- المشابهات والمكرر
    def _similar_for_line(self, c, ln):
        g = guess_item_fields(ln["code"], ln["desc"])
        cand = {"part": ln["code"], "rep_code": ln["code"], "category": g["category"], "make": g["make"], "model": g["model"],
                "y1": g["y1"], "y2": g["y2"], "kind": g["kind"], "condition": g["condition"], "origin": g["origin"],
                "img_hash": image_dhash(ln["img"]) if ln.get("img") else None}
        return find_similar_items(c, cand)

    def _item_compare_data(self, c, item_id, title):
        r = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        named = _named_codes(c, [item_id]).get(item_id, [])
        years = "-".join(x for x in (r["y1"], r["y2"]) if x)
        extra = [("رقم الصنف / الباركود", r["item_no"]), ("المتوفر", r["qty"] or 0), ("سعر المفرد", sar(num(r["retail"])))]
        if self.can("view_cost"):
            extra.append(("التكلفة", sar(num(r["buy"]) + num(r["expense"]))))
        extra.append(("ملاحظات", r["notes"] or ""))
        return {"title": title, "image": image_path(r["image"]) if r["image"] else "",
                "fields": {"part": r["part"] or "", "rep_code": r["rep_code"] or "", "codes": " / ".join(named),
                           "car": r["car"] or "", "years": years, "category": r["category"] or "", "kind": r["kind"] or "",
                           "origin": r["origin"] or "", "cond": "مستعمل" if str(r["condition"] or "NEW").upper() == "USED" else "جديد"},
                "extra": extra}

    def _line_compare_data(self, ln):
        g = guess_item_fields(ln["code"], ln["desc"])
        years = "-".join(x for x in (g["y1"], g["y2"]) if x)
        return {"title": "الصنف في فاتورة المورد", "image": ln.get("img") or "",
                "fields": {"part": ln["code"], "rep_code": ln["code"], "codes": "", "car": f"{g['make']} {g['model']}".strip(),
                           "years": years, "category": g["category"], "kind": g["kind"], "origin": g["origin"],
                           "cond": "مستعمل" if g["condition"] == "USED" else "جديد"},
                "extra": [("الكمية في الفاتورة", f"{ln['qty']:g}"), ("سعر الوحدة", f"{ln['price']:,.2f}"), ("الوصف الكامل", ln["desc"])]}

    def _form_compare_data(self, d, img_src):
        years = "-".join(x for x in (d["y1"], d["y2"]) if x)
        return {"title": "الصنف الذي تضيفه الآن", "image": img_src or "",
                "fields": {"part": d["part"], "rep_code": d["rep_code"], "codes": "", "car": f"{d['make']} {d['model']}".strip(),
                           "years": years, "category": d["category"], "kind": d["kind"], "origin": d["origin"],
                           "cond": "مستعمل" if d["condition"] == "USED" else "جديد"},
                "extra": [("الكمية", d["qty"])]}

    def compare_window(self, parent, left, right):
        """مقارنة صنفين جنبًا إلى جنب: الصور + أرقام القطع + المواصفات (الأخضر متطابق، الأحمر مختلف)."""
        win = tk.Toplevel(parent)
        win.title("⚖ مقارنة صنفين")
        win.configure(bg=BG)
        win.transient(parent)
        self.center(win, 1000, 720)
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="إغلاق", command=win.destroy).pack()
        fr = self.scroll_area(win)
        fr.columnconfigure(0, weight=1)
        fr.columnconfigure(1, weight=1)
        ttk.Label(fr, text="مقارنة صنفين", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="e")
        ttk.Label(fr, text="🟩 متطابق     🟥 مختلف     ⬜ ناقص في أحدهما", style="Sub.TLabel").grid(row=1, column=0, columnspan=3, sticky="e", pady=(0, 8))
        photos = []

        def head(col, d):
            box = ttk.Frame(fr)
            box.grid(row=2, column=col, padx=8, pady=6, sticky="n")
            ttk.Label(box, text=d["title"], font=(FONT, 12, "bold")).pack()
            lbl = ttk.Label(box, text="لا توجد صورة", style="Muted.TLabel")
            lbl.pack(pady=6)
            if d.get("image") and os.path.exists(d["image"]):
                ph = load_photo(d["image"], (260, 260))
                if ph:
                    photos.append(ph)
                    lbl.configure(image=ph, text="")

        head(1, left)
        head(0, right)

        def cell(row, col, text, bg="white", bold=False):
            tk.Label(fr, text=str(text), bg=bg, fg=TEXT, anchor="e", justify="right", wraplength=380, padx=8, pady=5,
                     font=(FONT, 10, "bold" if bold else "normal"), highlightbackground=BORDER, highlightthickness=1).grid(row=row, column=col, sticky="nsew", padx=1, pady=1)

        r_ = 3
        for key, label in COMPARE_FIELDS:
            a_, b_ = str(left["fields"].get(key, "") or "").strip(), str(right["fields"].get(key, "") or "").strip()
            bg = "#e2e8f0"
            if a_ and b_:
                bg = "#dcfce7" if a_.upper() == b_.upper() else "#fee2e2"
            cell(r_, 2, label, "#f8fafc", True)
            cell(r_, 1, a_ or "—", bg)
            cell(r_, 0, b_ or "—", bg)
            r_ += 1
        labels = []
        for d in (left, right):
            for lab, _ in d["extra"]:
                if lab not in labels:
                    labels.append(lab)
        for lab in labels:
            lv = next((v for l_, v in left["extra"] if l_ == lab), "")
            rv = next((v for l_, v in right["extra"] if l_ == lab), "")
            cell(r_, 2, lab, "#f8fafc", True)
            cell(r_, 1, lv if str(lv) != "" else "—")
            cell(r_, 0, rv if str(rv) != "" else "—")
            r_ += 1
        win._photos = photos

    def _similar_dialog(self, parent, sims, subject, mode="import", left=None):
        """يعرض الأصناف المشابهة مع أرقامها. يرجع ("link", رقم) أو ("new", None) أو None عند الإلغاء."""
        result = {"v": None}
        dlg = tk.Toplevel(parent)
        dlg.title("⚠ أصناف مشابهة")
        dlg.configure(bg=BG)
        dlg.transient(parent)
        dlg.grab_set()
        fr = ttk.Frame(dlg, padding=14)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text="قد يكون هذا الصنف مكررًا", style="Title.TLabel").pack(anchor="e")
        ttk.Label(fr, text=subject, style="Sub.TLabel", wraplength=900, justify="right").pack(anchor="e", pady=(0, 6))
        t = make_tree(fr, ("score", "item_no", "part", "rep", "name", "qty", "why"),
                      {"score": "التشابه", "item_no": "رقم الصنف", "part": "رقم القطعة", "rep": "رمز المنتج عند المورد", "name": "الصنف", "qty": "المتوفر", "why": "السبب"},
                      {"score": 70, "item_no": 100, "part": 120, "rep": 170, "name": 260, "qty": 70, "why": 260}, height=min(max(len(sims), 2), 6))
        for i, s in enumerate(sims):
            rep_txt = " / ".join(x for x in (s["rep_code"], s["codes"]) if x)
            add_row(t, (f"{s['score']}%", s["item_no"], s["part"] or "-", rep_txt or "-", s["name"] + (f" ({s['origin']})" if s["origin"] else ""), s["qty"], "، ".join(s["reasons"])),
                    iid=str(s["id"]), extra=("best",) if i == 0 else ())
        if sims:
            t.selection_set(str(sims[0]["id"]))

        def link():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد الصنف الذي تريد الربط به", parent=dlg)
                return
            result["v"] = ("link", int(sel[0]))
            dlg.destroy()

        def new():
            result["v"] = ("new", None)
            dlg.destroy()

        def compare(_e=None):
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد صنفًا من القائمة لمقارنته", parent=dlg)
                return
            with connect() as c_:
                right = self._item_compare_data(c_, int(sel[0]), "الصنف الموجود في المخزون")
            self.compare_window(dlg, left, right)

        btns = ttk.Frame(fr)
        btns.pack(fill="x", pady=(10, 0))
        if mode == "import":
            ttk.Button(btns, text="🔗 هو نفس الصنف — اربطه بالمحدد", style="Success.TButton", command=link).pack(side="right", padx=4)
            ttk.Button(btns, text="صنف مختلف — أنشئ صنفًا جديدًا", command=new).pack(side="right", padx=4)
        else:
            ttk.Button(btns, text="صنف مختلف — احفظه كصنف جديد", style="Accent.TButton", command=new).pack(side="right", padx=4)
        if left:
            ttk.Button(btns, text="⚖ مقارنة مع المحدد", style="Accent.TButton", command=compare).pack(side="right", padx=4)
            t.bind("<Double-1>", compare)
        ttk.Button(btns, text="إلغاء", command=dlg.destroy).pack(side="left", padx=4)
        self.autosize(dlg, fr, 1100)
        dlg.wait_window()
        return result["v"]

    def _apply_import_images(self, active_lines, replace):
        """يضع صور الفاتورة كصورة للصنف (للأصناف بدون صورة فقط، أو يستبدل الموجود)."""
        with connect() as c:
            for ln in active_lines:
                if not ln.get("img") or not ln.get("item_id") or not os.path.exists(ln["img"]):
                    continue
                cur = c.execute("SELECT image FROM items WHERE id=?", (ln["item_id"],)).fetchone()
                if not cur or (cur["image"] and not replace):
                    continue
                c.execute("UPDATE items SET image=? WHERE id=?", (store_image(ln["img"]), ln["item_id"]))
                if cur["image"]:
                    delete_image(cur["image"])

    def duplicates_window(self):
        if not (self.role == "admin" or self.can("inv_edit")):
            return
        win = tk.Toplevel(self)
        win.title("🧬 فحص الأصناف المكررة")
        win.configure(bg=BG)
        self.center(win, 1200, 680)
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="الأصناف المشتبه بتكرارها", style="Title.TLabel").pack(anchor="e")
        ttk.Label(body, text="يقارن البرنامج السيارة والموديل ونوع القطعة ونوع المفتاح والسنوات والصور والرموز. الأصلي والصيني، والجديد والمستعمل لا يُعتبران مكررين.",
                  style="Sub.TLabel", wraplength=1100, justify="right").pack(anchor="e")
        count_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=count_var, style="Muted.TLabel").pack(anchor="e")
        t = make_tree(body, ("score", "a", "ac", "b", "bc", "why"),
                      {"score": "التشابه", "a": "الصنف الأول", "ac": "أرقام الأول", "b": "الصنف الثاني", "bc": "أرقام الثاني", "why": "السبب"},
                      {"score": 70, "a": 250, "ac": 190, "b": 250, "bc": 190, "why": 220})
        pairs = []

        def label(r):
            return f"{r['item_no']} | {r['name']}" + (f" ({r['origin']})" if r["origin"] else "") + f" | متوفر {r['qty']}"

        def label_full(r):
            return label(r) + (f" | {codes_label(r)}" if codes_label(r) else "")

        def load():
            pairs.clear()
            clear_tree(t)
            self.config(cursor="watch")
            win.update_idletasks()
            try:
                with connect() as c:
                    found = find_duplicate_pairs(c)
            finally:
                self.config(cursor="")
            for i, p in enumerate(found):
                pairs.append(p)
                add_row(t, (f"{p['score']}%", label(p["a"]), codes_label(p["a"]) or "-", label(p["b"]), codes_label(p["b"]) or "-", "، ".join(p["reasons"])), iid=str(i),
                        extra=("best",) if p["score"] >= 90 else ())
            count_var.set(f"عدد الأزواج المشتبه بها: {len(found)}" if found else "لم أجد أصنافًا مكررة ✔")

        def current():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد زوجًا من القائمة أولًا", parent=win)
                return None
            return pairs[int(sel[0])]

        def merge(keep_first):
            p = current()
            if not p:
                return
            keep, drop = (p["a"], p["b"]) if keep_first else (p["b"], p["a"])
            if not messagebox.askyesno("تأكيد الدمج",
                                       f"سيتم دمج:\n   {label_full(drop)}\nداخل:\n   {label_full(keep)}\n\n"
                                       f"الكمية بعد الدمج: {keep['qty'] + drop['qty']}\n"
                                       "كل مشتريات ومبيعات الصنف المحذوف تنتقل للصنف المُبقى، ورموزه وباركوده القديم تبقى تعمل.\n"
                                       "لا يمكن التراجع (تُحفظ نسخة احتياطية تلقائيًا). متابعة؟", parent=win):
                return
            try:
                bdir = os.path.join(os.path.dirname(DB), "merge_backups")
                os.makedirs(bdir, exist_ok=True)
                shutil.copy2(DB, os.path.join(bdir, "قبل_الدمج_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db"))
                with connect() as c:
                    res = merge_items(c, keep["id"], drop["id"])
                if res.get("delete_image"):
                    delete_image(res["delete_image"])
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            load()

        def ignore():
            p = current()
            if not p:
                return
            a, b = sorted((p["a"]["id"], p["b"]["id"]))
            with connect() as c:
                c.execute("INSERT OR IGNORE INTO dup_ignored(a_id,b_id) VALUES(?,?)", (a, b))
            load()

        def compare():
            p = current()
            if not p:
                return
            with connect() as c:
                l_ = self._item_compare_data(c, p["a"]["id"], "الصنف الأول")
                r_ = self._item_compare_data(c, p["b"]["id"], "الصنف الثاني")
            self.compare_window(win, l_, r_)

        t.bind("<Double-1>", lambda e: compare())
        ttk.Button(bar, text="⚖ مقارنة", style="Accent.TButton", command=compare).pack(side="right", padx=4)
        ttk.Button(bar, text="دمج: أبقِ الأول واحذف الثاني", style="Success.TButton", command=lambda: merge(True)).pack(side="right", padx=4)
        ttk.Button(bar, text="دمج: أبقِ الثاني واحذف الأول", style="Success.TButton", command=lambda: merge(False)).pack(side="right", padx=4)
        ttk.Button(bar, text="ليسا مكررين (تجاهل)", command=ignore).pack(side="right", padx=4)
        ttk.Button(bar, text="🔄 إعادة الفحص", command=load).pack(side="left", padx=4)
        load()

    def _import_review(self, parsed, path, on_done=None):
        with connect() as c:
            sups = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
        try:
            row_imgs = extract_pdf_row_images(path, parsed["lines"])
        except Exception:
            row_imgs = {}
        lines = [dict(l, item_id=None, skip=False, manual=False, img=row_imgs.get(i), similar=[]) for i, l in enumerate(parsed["lines"])]
        CUR = {"SAR": "ريال سعودي (SAR)", "AED": "درهم إماراتي (AED)", "USD": "دولار أمريكي (USD)"}

        win = tk.Toplevel(self)
        win.title("استيراد فاتورة مورد من PDF")
        self._alert_block = getattr(self, "_alert_block", 0) + 1

        def _unblock(e, w=win):
            if e.widget is w:
                self._alert_block = max(0, getattr(self, "_alert_block", 1) - 1)
                self.after(1500, self.check_stock_alerts)

        win.bind("<Destroy>", _unblock)
        win.configure(bg=BG)
        win.transient(self)
        self.center(win, 1260, 800)
        bar = ttk.Frame(win, padding=10)
        bar.pack(side="bottom", fill="x")
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="مراجعة فاتورة المورد", style="Title.TLabel").pack(anchor="e")
        ttk.Label(body, text=f"الملف: {os.path.basename(path)} — الأصناف غير الموجودة أنشئها أو اربطها بصنف موجود، ثم احفظ", style="Sub.TLabel").pack(anchor="e")

        head = ttk.LabelFrame(body, text="بيانات الفاتورة", padding=8)
        head.pack(fill="x", pady=6)
        r1 = ttk.Frame(head)
        r1.pack(fill="x", pady=3)
        ttk.Label(r1, text="المورد (إجباري)").pack(side="right", padx=4)
        sup_cb = ttk.Combobox(r1, values=sups, state="readonly", width=30)
        sup_cb.pack(side="right", padx=4)
        ttk.Label(r1, text="رقم الفاتورة").pack(side="right", padx=(18, 4))
        inv_e = ttk.Entry(r1, width=24, justify="right")
        inv_e.insert(0, parsed["invoice_no"])
        inv_e.pack(side="right", padx=4)
        ttk.Label(r1, text="التاريخ").pack(side="right", padx=(18, 4))
        date_e = ttk.Entry(r1, width=12, justify="center")
        date_e.insert(0, parsed["date"] or datetime.now().strftime("%Y-%m-%d"))
        date_e.pack(side="right", padx=4)
        r2 = ttk.Frame(head)
        r2.pack(fill="x", pady=3)
        ttk.Label(r2, text="عملة الفاتورة").pack(side="right", padx=4)
        cur_cb = ttk.Combobox(r2, values=list(CUR.values()), state="readonly", width=20)
        cur_cb.set(CUR.get(parsed["currency"] or "SAR", CUR["SAR"]))
        cur_cb.pack(side="right", padx=4)
        ttk.Label(r2, text="سعر التحويل إلى الريال").pack(side="right", padx=(18, 4))
        rate_e = ttk.Entry(r2, width=8, justify="center")
        rate_e.pack(side="right", padx=4)
        ttk.Label(r2, text="الشحن").pack(side="right", padx=(18, 4))
        ship_e = ttk.Entry(r2, width=9, justify="center")
        ship_e.insert(0, f"{parsed['shipping']:g}")
        ship_e.pack(side="right", padx=4)
        ttk.Label(r2, text="الضريبة").pack(side="right", padx=(12, 4))
        tax_e = ttk.Entry(r2, width=9, justify="center")
        tax_e.insert(0, f"{parsed['tax']:g}")
        tax_e.pack(side="right", padx=4)
        ttk.Label(r2, text="الخصم").pack(side="right", padx=(12, 4))
        disc_e = ttk.Entry(r2, width=9, justify="center")
        disc_e.insert(0, f"{parsed['discount']:g}")
        disc_e.pack(side="right", padx=4)
        n_imgs = sum(1 for ln in lines if ln.get("img"))
        IMG_MODES = ["للأصناف بدون صورة فقط", "استبدال صور الأصناف", "لا تستورد الصور"]
        r3 = ttk.Frame(head)
        r3.pack(fill="x", pady=3)
        ttk.Label(r3, text=f"صور الفاتورة ({n_imgs} صورة مقروءة)").pack(side="right", padx=4)
        img_mode = ttk.Combobox(r3, values=IMG_MODES, state="readonly", width=26)
        img_mode.set(IMG_MODES[0] if n_imgs else IMG_MODES[2])
        img_mode.pack(side="right", padx=4)
        info_var = tk.StringVar(value="")
        ttk.Label(head, textvariable=info_var, style="Muted.TLabel").pack(anchor="e")

        acts = ttk.Frame(body)
        acts.pack(fill="x", pady=4)
        t = make_tree(body, ("n", "code", "desc", "qty", "price", "cost", "status"),
                      {"n": "#", "code": "رمز المنتج عند المورد", "desc": "الوصف", "qty": "الكمية", "price": "سعر الوحدة", "cost": "التكلفة النهائية بالريال", "status": "الحالة في المخزون"},
                      {"n": 40, "code": 170, "desc": 360, "qty": 70, "price": 90, "cost": 140, "status": 520}, height=7)
        t.configure(selectmode="browse")
        sum_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=sum_var, font=(FONT, 11, "bold"), foreground=NAVY).pack(anchor="e", pady=(0, 6))

        def cur_code():
            return {v: k for k, v in CUR.items()}.get(cur_cb.get(), "SAR")

        def default_rate(code):
            if code == "SAR":
                return 1.0
            return num(setting(f"rate_{code}")) or (1.0211 if code == "AED" else 3.75)

        def factor():
            sub = sum(l["total"] for l in lines)
            extra = num(ship_e.get()) + num(tax_e.get()) - num(disc_e.get())
            return (extra / sub if sub > 0 else 0.0), extra, sub

        def item_label(c, item_id):
            r = c.execute("SELECT item_no,category,car,kind,y1,y2,part FROM items WHERE id=?", (item_id,)).fetchone()
            return f"{r['item_no']} | {item_display_name(r)}" if r else "؟"

        def refresh(*_):
            f, extra, sub = factor()
            rate = num(rate_e.get()) or 1.0
            clear_tree(t)
            unresolved = 0
            with connect() as c:
                for i, ln in enumerate(lines):
                    unit_sar = ln["price"] * (1 + f) * rate
                    tag = ()
                    if ln["skip"]:
                        st = "⏭ سيتم تجاهله"
                    elif ln["item_id"]:
                        st = "✅ " + item_label(c, ln["item_id"])
                    else:
                        sim_ = ln.get("similar") or []
                        st = "⚠ غير موجود — أنشئه أو اربطه" + (
                            f"  |  🔍 مشابه: {sim_[0]['item_no']} — قطعة {sim_[0]['part'] or '-'}"
                            + (f" — مورد {sim_[0]['rep_code']}" if sim_[0]["rep_code"] else "") + f" ({sim_[0]['score']}%)" if sim_ else "")
                        tag = ("low",)
                        unresolved += 1
                    q = ln["qty"]
                    add_row(t, (ln["n"], ln["code"], ("📷 " if ln.get("img") else "") + ln["desc"][:80], int(q) if float(q).is_integer() else q, f"{ln['price']:,.2f}", sar(unit_sar), st), iid=str(i), extra=tag)
            cc = cur_code()
            info_var.set(f"المصاريف الموزعة على الأصناف (شحن + ضريبة − خصم): {extra:,.2f} = {f * 100:.2f}% من قيمة الأصناف — تُضاف لتكلفة كل صنف")
            net = sub + extra
            msg = f"الأسطر: {len(lines)}   |   الناقصة: {unresolved}   |   قيمة الأصناف: {sub:,.2f} {cc}   |   الصافي: {net:,.2f} {cc}  ≈  {net * rate:,.2f} ر.س"
            if parsed.get("net_pdf") is not None and abs(net - parsed["net_pdf"]) > 1:
                msg += f"   ⚠ لا يطابق صافي الملف ({parsed['net_pdf']:,.2f})"
            sum_var.set(msg)

        def rematch(*_):
            sup = sup_cb.get().strip()
            with connect() as c:
                for ln in lines:
                    if ln["manual"] or ln["skip"]:
                        continue
                    ln["item_id"] = self._match_supplier_line(c, sup, ln["code"])
                    ln["similar"] = [] if ln["item_id"] else self._similar_for_line(c, ln)
            refresh()

        def on_cur(*_):
            rate_e.delete(0, "end")
            rate_e.insert(0, f"{default_rate(cur_code()):g}")
            refresh()

        def plus_sup():
            name = simpledialog.askstring("إضافة مورد", "اسم المورد:", initialvalue=parsed.get("supplier_guess", "").title(), parent=win)
            if not name:
                return
            try:
                name = self._insert_supplier(name)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            with connect() as c:
                names = [r["name"] for r in c.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
            sup_cb.configure(values=names)
            sup_cb.set(name)
            rematch()

        ttk.Button(r1, text="+", width=3, command=plus_sup).pack(side="right")

        def selected_idx():
            sel = t.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "حدد سطرًا من الجدول أولًا", parent=win)
                return None
            return int(sel[0])

        def create_for(idx, after=None):
            ln = lines[idx]
            if not ln.get("_dup_asked"):
                with connect() as c_:
                    sims_ = self._similar_for_line(c_, ln)
                ln["similar"] = sims_
                if sims_:
                    ln["_dup_asked"] = True
                    res_ = self._similar_dialog(win, sims_, f"{ln['code']} — {ln['desc'][:80]}", mode="import", left=self._line_compare_data(ln))
                    if res_ is None:
                        return
                    if res_[0] == "link":
                        ln["item_id"], ln["manual"], ln["skip"] = res_[1], True, False
                        refresh()
                        if after:
                            after()
                        return
            g = guess_item_fields(ln["code"], ln["desc"])
            f, _, _ = factor()
            rate = num(rate_e.get()) or 1.0
            with connect() as c:
                makes = {r["name"] for r in c.execute("SELECT name FROM car_makes").fetchall()}
                types = {r["name"] for r in c.execute("SELECT name FROM item_types").fetchall()}
                models = {r["name"] for r in c.execute("SELECT m.name FROM car_models m JOIN car_makes k ON k.id=m.make_id WHERE k.name=?", (g["make"],)).fetchall()}
            prefill = {"part": ln["code"], "category": g["category"] if g["category"] in types else "",
                       "make": g["make"] if g["make"] in makes else "", "model": g["model"] if g["model"] in models else "",
                       "y1": g["y1"], "y2": g["y2"], "kind": g["kind"], "condition": g["condition"], "qty": 0,
                       "buy": round(ln["price"] * rate, 2), "expense_pct": round(f * 100, 2), "rep_code": ln["code"], "notes": ln["desc"][:150],
                       "image_src": (ln.get("img") if img_mode.get() != IMG_MODES[2] else ""), "_skip_dup": True, "origin": g["origin"]}

            def saved(item_id):
                ln["item_id"] = item_id
                ln["manual"] = True
                ln["skip"] = False
                refresh()
                if after:
                    after()

            self.item_dialog(prefill=prefill, on_saved=saved)

        def create_sel():
            idx = selected_idx()
            if idx is not None:
                create_for(idx)

        def create_all():
            def step():
                for i, ln in enumerate(lines):
                    if not ln["item_id"] and not ln["skip"]:
                        create_for(i, after=step)
                        return
                messagebox.showinfo("تم", "كل الأصناف صارت موجودة في المخزون", parent=win)
            step()

        def link_sel():
            idx = selected_idx()
            if idx is None:
                return
            item_id = self.pick_item(win, "ربط السطر بصنف موجود", lines[idx]["code"])
            if item_id:
                lines[idx]["item_id"] = item_id
                lines[idx]["manual"] = True
                lines[idx]["skip"] = False
                refresh()

        def similar_sel():
            idx = selected_idx()
            if idx is None:
                return
            with connect() as c_:
                sims_ = self._similar_for_line(c_, lines[idx])
            if not sims_:
                messagebox.showinfo("المشابهات", "ما وجدت أصنافًا مشابهة لهذا السطر.", parent=win)
                return
            res_ = self._similar_dialog(win, sims_, f"{lines[idx]['code']} — {lines[idx]['desc'][:80]}", mode="import", left=self._line_compare_data(lines[idx]))
            if res_ and res_[0] == "link":
                lines[idx]["item_id"], lines[idx]["manual"], lines[idx]["skip"] = res_[1], True, False
                refresh()

        def view_line_img():
            idx = selected_idx()
            if idx is None:
                return
            ln = lines[idx]
            if not ln.get("img") or not os.path.exists(ln["img"]):
                messagebox.showinfo("الصورة", "هذا السطر ما فيه صورة مقروءة من الفاتورة.", parent=win)
                return
            dlg = tk.Toplevel(win)
            dlg.title(f"صورة {ln['code']}")
            dlg.configure(bg=BG)
            dlg.transient(win)
            dlg.grab_set()
            ph = load_photo(ln["img"], (420, 420))
            lbl = ttk.Label(dlg, image=ph) if ph else ttk.Label(dlg, text="تعذّر عرض الصورة")
            lbl.image = ph
            lbl.pack(padx=14, pady=14)
            ttk.Label(dlg, text=ln["desc"][:90], wraplength=420, justify="center").pack(padx=14)
            bt = ttk.Frame(dlg)
            bt.pack(pady=12)

            def drop():
                ln["img"] = None
                dlg.destroy()
                refresh()

            ttk.Button(bt, text="🗑 إزالة هذه الصورة (لا تُستخدم)", style="Danger.TButton", command=drop).pack(side="right", padx=6)
            ttk.Button(bt, text="إبقاء", command=dlg.destroy).pack(side="right", padx=6)

        def skip_sel():
            idx = selected_idx()
            if idx is not None:
                lines[idx]["skip"] = not lines[idx]["skip"]
                refresh()

        def do_save(receive_now=False):
            sup = sup_cb.get().strip()
            if not sup:
                messagebox.showwarning("تنبيه", "اسم المورد إجباري — اختره من القائمة (أو أضفه بزر +)", parent=win)
                return
            try:
                date_iso = datetime.strptime(date_e.get().strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("تنبيه", "التاريخ لازم يكون بالشكل 2026-10-15", parent=win)
                return
            inv = inv_e.get().strip() or datetime.now().strftime("PUR%y%m%d%H%M%S")
            rate = num(rate_e.get())
            if rate <= 0:
                messagebox.showwarning("تنبيه", "اكتب سعر التحويل إلى الريال", parent=win)
                return
            active = [ln for ln in lines if not ln["skip"]]
            if not active:
                messagebox.showwarning("تنبيه", "كل الأسطر متجاهلة", parent=win)
                return
            missing = [ln for ln in active if not ln["item_id"]]
            if missing:
                messagebox.showwarning("أصناف ناقصة", f"باقي {len(missing)} سطر بدون صنف.\nأنشئها أو اربطها بصنف موجود أو تجاهلها قبل الحفظ.", parent=win)
                return
            f, _, _ = factor()
            try:
                n = self._save_import_invoice(sup, inv, date_iso, rate, f, active)
            except Exception as e:
                messagebox.showerror("خطأ", str(e), parent=win)
                return
            if cur_code() != "SAR":
                setsetting(f"rate_{cur_code()}", rate)
            if img_mode.get() != IMG_MODES[2]:
                try:
                    self._apply_import_images(active, img_mode.get() == IMG_MODES[1])
                except Exception as e:
                    messagebox.showwarning("الصور", f"تم حفظ الفاتورة لكن تعذّر حفظ بعض الصور:\n{e}", parent=win)
            msg = f"تم تسجيل فاتورة الشراء {inv} ({n} صنف) بحالة معلّقة.\nعند استلام البضاعة حدد الفاتورة واضغط (إضافة الفاتورة المحددة للمخزون)."
            if receive_now:
                with connect() as c:
                    ids = [r[0] for r in c.execute("SELECT id FROM purchases WHERE batch=? AND supplier=? AND status='pending'", (inv, sup)).fetchall()]
                n2, changes = self._receive_purchases(ids)
                msg = f"تم تسجيل الفاتورة {inv} وإضافة {n2} صنف إلى المخزون."
                if changes:
                    msg += "\n\nتحديث التكلفة (متوسط مرجّح):\n" + "\n".join(changes[:10]) + ("\n..." if len(changes) > 10 else "")
            win.destroy()
            if on_done:
                on_done()
            messagebox.showinfo("تم", msg)

        ttk.Button(acts, text="＋ إنشاء صنف جديد للسطر المحدد", style="Accent.TButton", command=create_sel).pack(side="right", padx=4)
        ttk.Button(acts, text="⏩ إنشاء كل الأصناف الناقصة بالتتابع", command=create_all).pack(side="right", padx=4)
        ttk.Button(acts, text="🔗 ربط بصنف موجود", command=link_sel).pack(side="right", padx=4)
        ttk.Button(acts, text="🔍 المشابهات", command=lambda: similar_sel()).pack(side="right", padx=4)
        ttk.Button(acts, text="🖼 صورة السطر", command=lambda: view_line_img()).pack(side="right", padx=4)
        ttk.Button(acts, text="⏭ تجاهل / إلغاء التجاهل", command=skip_sel).pack(side="right", padx=4)
        ttk.Button(acts, text="↺ إعادة المطابقة", command=rematch).pack(side="left", padx=4)
        ttk.Button(bar, text="✔  تسجيل وإضافة للمخزون الآن", style="Success.TButton", command=lambda: do_save(True)).pack(side="right", padx=8, ipadx=20, ipady=4)
        ttk.Button(bar, text="💾  تسجيل فقط (معلّقة)", style="Accent.TButton", command=lambda: do_save(False)).pack(side="right", padx=8, ipadx=20, ipady=4)

        t.bind("<Double-1>", lambda e: create_sel() if (t.selection() and not lines[int(t.selection()[0])]["item_id"]) else link_sel())
        cur_cb.bind("<<ComboboxSelected>>", on_cur)
        sup_cb.bind("<<ComboboxSelected>>", rematch)
        for e_ in (ship_e, tax_e, disc_e, rate_e):
            e_.bind("<KeyRelease>", refresh)

        guess = (parsed.get("supplier_guess") or "").lower()
        pre = next((sp for sp in sups if guess and (sp.lower() in guess or guess in sp.lower())), "")
        if pre:
            sup_cb.set(pre)
        on_cur()
        rematch()

    def sync_inventory(self, show_message=True):
        url = setting("sheets_url").strip()
        token = setting("sheets_token").strip()
        if not url or not token:
            if show_message:
                messagebox.showwarning("Google Sheets", "أدخل رابط Apps Script ورمز المزامنة من الإعدادات أولًا")
            return
        with connect() as c:
            rows = c.execute("""
                SELECT item_no,part,car,condition,qty,retail
                FROM items ORDER BY item_no
            """).fetchall()
        payload = {
            "token": token,
            "updated_at": now_str(),
            "items": [dict(r) for r in rows]
        }

        def worker():
            try:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
                with safe_urlopen(req, timeout=12) as response:
                    response.read()
                setsetting("sheets_last_sync", now_str())
                setsetting("sheets_last_error", "")
                if show_message:
                    self.after(0, lambda: messagebox.showinfo("Google Sheets", "تمت المزامنة بنجاح"))
            except Exception as e:
                msg = str(e)  # نحفظ النص لأن المتغير e يُحذف بعد نهاية except
                try:
                    setsetting("sheets_last_error", msg)
                except Exception:
                    pass
                if show_message:
                    self.after(0, lambda: messagebox.showerror("Google Sheets", f"فشلت المزامنة: {msg}"))

        threading.Thread(target=worker, daemon=True).start()

    def sync_from_settings(self):
        win = tk.Toplevel(self)
        win.title("إعداد Google Sheets")
        win.configure(bg=BG)
        fr = ttk.Frame(win, padding=16)
        fr.pack(fill="both", expand=True)
        ttk.Label(fr, text="رابط Google Apps Script").pack(pady=4, anchor="e")
        url = ttk.Entry(fr, width=75)
        url.pack(pady=4)
        url.insert(0, setting("sheets_url"))
        ttk.Label(fr, text="رمز المزامنة").pack(pady=4, anchor="e")
        token = ttk.Entry(fr, width=40, show="*")
        token.pack(pady=4, anchor="e")
        token.insert(0, setting("sheets_token"))

        def save_sheets():
            setsetting("sheets_url", url.get().strip())
            setsetting("sheets_token", token.get().strip())
            win.destroy()
            self.sync_inventory(True)

        ttk.Button(fr, text="حفظ وتجربة المزامنة", style="Accent.TButton", command=save_sheets).pack(pady=10)
        self.autosize(win, fr, 640)

    def change_pw(self):
        self.form("تغيير كلمة المرور", [("old", "كلمة المرور الحالية", ""), ("new", "كلمة المرور الجديدة", "")], self._change_pw)

    def _change_pw(self, d):
        if not d["new"]:
            raise ValueError("اكتب كلمة المرور الجديدة")
        if len(d["new"]) < 4:
            raise ValueError("كلمة المرور قصيرة (4 أحرف على الأقل)")
        with connect() as c:
            r = c.execute("SELECT * FROM users WHERE username=?", (self.user,)).fetchone()
        if not hmac.compare_digest(pw_hash(d["old"], r["salt"])[1], r["hash"]):
            raise ValueError("كلمة المرور الحالية غير صحيحة")
        s, h = pw_hash(d["new"])
        with connect() as c:
            c.execute("UPDATE users SET salt=?,hash=? WHERE username=?", (s, h, self.user))
        messagebox.showinfo("تم", "تم تغيير كلمة المرور")

    def backup(self):
        dest = filedialog.asksaveasfilename(defaultextension=".db", initialfile="نسخة_احتياطية_العباد.db", filetypes=[("Database", "*.db")])
        if dest:
            shutil.copy2(DB, dest)
            messagebox.showinfo("تم", "تم حفظ النسخة الاحتياطية")

    # ------------------------------------------------------------------ التقارير
    def reports(self):
        if not self.can("reports"):
            return
        self.clear("reports")
        self.page_title("التقارير", "ملخص المبيعات والمخزون والديون")
        with connect() as c:
            cards = [
                ("عدد الأصناف", c.execute("SELECT COUNT(*) FROM items").fetchone()[0], ACCENT),
                ("الكمية المتوفرة", c.execute("SELECT COALESCE(SUM(qty),0) FROM items").fetchone()[0], ACCENT),
                ("إجمالي المبيعات", sar(c.execute("SELECT COALESCE(SUM(price*qty),0) FROM sales").fetchone()[0]), GREEN),
                ("المبالغ المحصلة", sar(c.execute("SELECT COALESCE(SUM(paid),0) FROM sales").fetchone()[0]), GREEN),
                ("ديون الفواتير قبل التحصيل اللاحق", sar(c.execute("SELECT COALESCE(SUM(price*qty-COALESCE(paid,0)),0) FROM sales").fetchone()[0]), AMBER),
                ("تحصيلات الديون اللاحقة", sar(c.execute("SELECT COALESCE(SUM(amount),0) FROM debt_payments").fetchone()[0]), GREEN),
                ("صافي ديون العملاء", sar(c.execute("SELECT COALESCE((SELECT SUM(price*qty-COALESCE(paid,0)) FROM sales),0)-COALESCE((SELECT SUM(amount) FROM debt_payments),0)").fetchone()[0]), RED),
                ("إجمالي المصروفات", sar(c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses").fetchone()[0]), RED),
            ]
            if self.can("view_cost"):
                cards.append(("قيمة المخزون بالتكلفة", sar(c.execute("SELECT COALESCE(SUM(qty*(COALESCE(buy,0)+COALESCE(expense,0))),0) FROM items").fetchone()[0]), ACCENT))
        self.card_grid(cards)
        ttk.Label(self.body, text="مبيعات كل بائع", font=(FONT, 14, "bold")).pack(anchor="e", pady=(12, 0))
        with connect() as c:
            sellers = c.execute("""
                SELECT COALESCE(NULLIF(seller,''),'غير مسجل') seller,
                COUNT(*) operations, COALESCE(SUM(qty),0) pieces,
                COALESCE(SUM(price*qty),0) total, COALESCE(SUM(paid),0) paid
                FROM sales GROUP BY COALESCE(NULLIF(seller,''),'غير مسجل')
                ORDER BY total DESC
            """).fetchall()
        self.table(("seller", "operations", "pieces", "total", "paid", "remaining"),
                   {"seller": "البائع", "operations": "عدد عمليات البيع", "pieces": "عدد القطع المباعة", "total": "إجمالي قيمة المبيعات", "paid": "المبلغ المحصل", "remaining": "المتبقي"},
                   [(r["seller"], r["operations"], r["pieces"], sar(r["total"]), sar(r["paid"]), sar(r["total"] - r["paid"])) for r in sellers])


if __name__ == "__main__":
    init()
    App().mainloop()
