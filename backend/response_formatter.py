from typing import Any


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

    response = "وجدت النتائج التالية:\n"
    for row in results:
        row_data = [f"{column_names[i]}: {value}" for i, value in enumerate(row)]
        response += ", ".join(row_data) + "\n"

    if metadata and metadata.get("overflow"):
        row_limit = metadata.get("row_limit")
        if row_limit:
            response += f"\nتم عرض أول {row_limit} صف فقط. يمكنك تنزيل النتائج كملف CSV لعرض بيانات أكثر."

    return response
