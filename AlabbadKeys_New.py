
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import re, sqlite3, os, sys, hashlib, secrets, hmac, shutil, tempfile, webbrowser, html, json, threading, zipfile
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

DB = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "alabbad_keys_new.db")

# ------------------------------------------------------------------ الألوان والخط
APP_VERSION = "16.1.0"
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
