import pytest

from response_formatter import format_response


def test_format_none_results():
    result = format_response(None, None)
    assert "خطأ" in result


def test_format_empty_results():
    result = format_response([], ["col1", "col2"])
    assert "لم أجد" in result


def test_format_no_column_names():
    result = format_response([("a", 1)], None)
    assert "أسماء الأعمدة" in result


def test_format_no_column_names_empty_list():
    result = format_response([("a", 1)], [])
    assert "أسماء الأعمدة" in result


def test_format_single_row():
    results = [("أحمد", 5000, "هندسة")]
    columns = ["الاسم", "الراتب", "القسم"]
    response = format_response(results, columns)
    assert "وجدت النتائج التالية" in response
    assert "أحمد" in response
    assert "5000" in response
    assert "هندسة" in response


def test_format_multiple_rows():
    results = [("أحمد", 5000), ("سارة", 7000)]
    columns = ["الاسم", "الراتب"]
    response = format_response(results, columns)
    assert "أحمد" in response
    assert "سارة" in response
    lines = response.strip().split("\n")
    assert len(lines) >= 3  # header + 2 data rows


def test_format_with_overflow_metadata():
    results = [("أحمد", 5000)]
    columns = ["الاسم", "الراتب"]
    metadata = {"overflow": True, "row_limit": 200}
    response = format_response(results, columns, metadata)
    assert "200" in response
    assert "CSV" in response


def test_format_without_overflow_metadata():
    results = [("أحمد", 5000)]
    columns = ["الاسم", "الراتب"]
    metadata = {"overflow": False, "row_limit": 200}
    response = format_response(results, columns, metadata)
    assert "CSV" not in response


def test_format_metadata_none():
    results = [("أحمد", 5000)]
    columns = ["الاسم", "الراتب"]
    response = format_response(results, columns, None)
    assert "وجدت النتائج التالية" in response
