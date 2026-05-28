import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from num2words import num2words

_WESTERN_TO_ARABIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_ARABIC_CHAR = re.compile(r"[؀-ۿ]")

_ARABIC_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}

_COLUMN_LABELS: dict[str, str] = {
    # ── employees ──
    "employee_id": "رقم الموظف",
    "first_name_en": "الاسم الأول",
    "second_name_en": "الاسم الثاني",
    "third_name_en": "الاسم الثالث",
    "last_name_en": "اسم العائلة",
    "first_name_ar": "الاسم الأول",
    "second_name_ar": "الاسم الثاني",
    "third_name_ar": "الاسم الثالث",
    "last_name_ar": "اسم العائلة",
    "full_name_ar": "الاسم الكامل",
    "full_name_en": "الاسم الكامل",
    "email": "البريد الإلكتروني",
    "phone_number": "رقم الهاتف",
    "phone": "الهاتف",
    "hire_date": "تاريخ التعيين",
    "job_id": "المسمى الوظيفي",
    "job_title": "المسمى الوظيفي",
    "job_title_ar": "المسمى الوظيفي",
    "job_title_en": "المسمى الوظيفي",
    "salary": "الراتب",
    "total_salary": "إجمالي الرواتب",
    "avg_salary": "متوسط الراتب",
    "min_salary": "أقل راتب",
    "max_salary": "أعلى راتب",
    "manager_id": "رقم المدير",
    # ── departments ──
    "department_id": "رقم القسم",
    "department_name": "القسم",
    "department_name_ar": "القسم",
    "department_name_en": "القسم",
    # ── categories ──
    "category_id": "رقم الفئة",
    "category_name_ar": "الفئة",
    "category_name_en": "الفئة",
    # ── customers ──
    "customer_id": "رقم العميل",
    "city_ar": "المدينة",
    "created_at": "تاريخ الإنشاء",
    # ── customer_orders ──
    "order_id": "رقم الطلب",
    "order_date": "تاريخ الطلب",
    "status": "الحالة",
    "total_amount": "المبلغ الإجمالي",
    # ── order_items ──
    "order_item_id": "رقم عنصر الطلب",
    "product_id": "رقم المنتج",
    "quantity": "الكمية",
    "unit_price": "سعر الوحدة",
    "line_total": "إجمالي السطر",
    # ── products ──
    "product_name_ar": "المنتج",
    "product_name_en": "المنتج",
    "price": "السعر",
    # ── aggregates / aliases ──
    "count": "العدد",
    "employee_count": "عدد الموظفين",
    "total": "المجموع",
    "average": "المتوسط",
}


def _number_to_arabic_words(value: Any) -> str | None:
    """Convert a numeric value to Arabic words. Returns None if not a number."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    # Round to 2 decimal places to avoid 9900.000000
    d = d.quantize(Decimal("0.01"))

    # Remove unnecessary trailing zeros (9900.00 → 9900)
    d = d.normalize()

    # num2words supports decimals via 'to' parameter
    try:
        return num2words(d, lang="ar")
    except Exception:
        return None


def _arabize_column(name: str) -> str:
    key = name.lower().strip()
    if key in _COLUMN_LABELS:
        return _COLUMN_LABELS[key]
    agg_match = re.match(r"(count|sum|avg|min|max)\(\s*(?:distinct\s+)?(.+?)\s*\)", key)
    if agg_match:
        func = agg_match.group(1)
        inner = agg_match.group(2).strip().strip("`\"'")
        func_labels = {"count": "عدد", "sum": "مجموع", "avg": "متوسط", "min": "أقل", "max": "أعلى"}
        inner_label = _COLUMN_LABELS.get(inner, inner)
        return f"{func_labels.get(func, func)} {inner_label}"
    if _ARABIC_CHAR.search(name):
        return name
    return re.sub(r"[_\-]+", " ", name).strip()


def _format_date_arabic(value: Any) -> str | None:
    """Convert a date to TTS-friendly Arabic like '١٠ يونيو ٢٠٢٤'."""
    d: date | None = None
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        # Try parsing common string formats
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                d = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
    if d is None:
        return None
    day = str(d.day).translate(_WESTERN_TO_ARABIC)
    month = _ARABIC_MONTHS.get(d.month, str(d.month))
    year = str(d.year).translate(_WESTERN_TO_ARABIC)
    return f"{day} {month} {year}"


def _format_value(value: Any) -> str:
    if value is None:
        return "غير محدد"
    # Try date first (datetime.date objects and date-like strings)
    date_str = _format_date_arabic(value)
    if date_str is not None:
        return date_str
    # Try number-to-words
    arabic_words = _number_to_arabic_words(value)
    if arabic_words is not None:
        return arabic_words
    # Fallback: convert any remaining Western digits to Arabic-Indic
    return str(value).translate(_WESTERN_TO_ARABIC)


def format_response(
    results: list[tuple[Any, ...]] | None,
    column_names: list[str] | None,
    metadata: dict[str, Any] | None = None,
) -> str:
    if results is None:
        return "حدث خطأ أثناء تنفيذ الاستعلام."

    if not results:
        return "لم أجد أي نتائج لهذا الاستعلام."

    if not column_names:
        return "تم تنفيذ الاستعلام لكن لم يتم العثور على أسماء الأعمدة."

    arabic_cols = [_arabize_column(c) for c in column_names]

    rows = [
        "، ".join(f"{arabic_cols[i]}: {_format_value(value)}" for i, value in enumerate(row))
        for row in results
    ]
    response = "وجدت النتائج التالية:\n" + "\n".join(rows) + "\n"

    if metadata and metadata.get("overflow"):
        row_limit = metadata.get("row_limit")
        if row_limit:
            limit_ar = _number_to_arabic_words(row_limit) or str(row_limit)
            response += f"\nتم عرض أول {limit_ar} صف فقط. يمكنك تنزيل النتائج كملف CSV لعرض بيانات أكثر."

    return response
