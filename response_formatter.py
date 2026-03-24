from typing import Any


def format_response(results: list[tuple[Any, ...]] | None, column_names: list[str] | None) -> str:
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

    return response
