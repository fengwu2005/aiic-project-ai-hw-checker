import json

import pytest

from final.taskflow import (
    add_task,
    archive_tasks,
    batch_update_status,
    complete_task,
    delete_task,
    export_tasks,
    import_tasks,
    list_tasks,
    load_tasks,
    task_statistics,
    validate_priority,
)


def test_add_task_creates_advanced_fields(tmp_path):
    path = tmp_path / "tasks.json"
    task = add_task("write report", "finish final report", "high", "2026-06-10", "course,AI", path)
    assert task["id"] == 1
    assert task["status"] == "todo"
    assert task["tags"] == ["ai", "course"]
    assert "created_at" in task


def test_add_task_persists_json(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("demo", "persist me", "medium", "2026-06-10", ["demo"], path)
    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "demo"


def test_complete_task_changes_status(tmp_path):
    path = tmp_path / "tasks.json"
    task = add_task("demo", "", "low", "2026-06-10", [], path)
    completed = complete_task(task["id"], path)
    assert completed["status"] == "done"


def test_delete_task_removes_item(tmp_path):
    path = tmp_path / "tasks.json"
    task = add_task("demo", "", "low", "2026-06-10", [], path)
    delete_task(task["id"], path)
    assert load_tasks(path) == []


def test_filter_by_priority_and_tag(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("a", "alpha", "high", "2026-06-10", "course", path)
    add_task("b", "beta", "low", "2026-06-11", "life", path)
    result = list_tasks(priority="high", tag="course", path=path)
    assert [task["title"] for task in result] == ["a"]


def test_filter_by_deadline_range(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("a", "", "high", "2026-06-10", [], path)
    add_task("b", "", "low", "2026-06-20", [], path)
    result = list_tasks(deadline_from="2026-06-15", deadline_to="2026-06-30", path=path)
    assert [task["title"] for task in result] == ["b"]


def test_keyword_search_checks_title_and_description(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("write", "AI defense report", "high", "2026-06-10", [], path)
    add_task("buy milk", "daily", "low", "2026-06-11", [], path)
    assert len(list_tasks(keyword="defense", path=path)) == 1


def test_sort_by_priority(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("low task", "", "low", "2026-06-10", [], path)
    add_task("high task", "", "high", "2026-06-11", [], path)
    result = list_tasks(sort_by="priority", path=path)
    assert [task["priority"] for task in result] == ["high", "low"]


def test_batch_archive_hides_tasks_by_default(tmp_path):
    path = tmp_path / "tasks.json"
    first = add_task("a", "", "high", "2026-06-10", [], path)
    second = add_task("b", "", "medium", "2026-06-11", [], path)
    archive_tasks([first["id"], second["id"]], path)
    assert list_tasks(path=path) == []
    assert len(list_tasks(include_archived=True, path=path)) == 2


def test_batch_update_rejects_missing_id(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("a", "", "high", "2026-06-10", [], path)
    with pytest.raises(ValueError):
        batch_update_status([1, 999], "done", path)


def test_export_and_import_tasks_with_duplicate_id(tmp_path):
    path = tmp_path / "tasks.json"
    export_path = tmp_path / "export.json"
    add_task("original", "", "high", "2026-06-10", [], path)
    export_tasks(export_path, path)
    imported_count = import_tasks(export_path, path)
    assert imported_count == 1
    assert sorted(task["id"] for task in load_tasks(path)) == [1, 2]


def test_import_rejects_invalid_json(tmp_path):
    path = tmp_path / "tasks.json"
    source = tmp_path / "bad.json"
    source.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError):
        import_tasks(source, path)


def test_statistics_counts_overdue_and_tags(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("old", "", "high", "2026-01-01", "course", path)
    add_task("done", "", "low", "2026-01-02", "course", path)
    complete_task(2, path)
    stats = task_statistics(today="2026-02-01", path=path)
    assert stats["overdue"] == 1
    assert stats["high_priority_open"] == 1
    assert stats["by_tag"]["course"] == 2


def test_invalid_priority_raises():
    with pytest.raises(ValueError):
        validate_priority("urgent")


def test_invalid_deadline_raises(tmp_path):
    with pytest.raises(ValueError):
        add_task("bad", "", "high", "2026-02-31", [], tmp_path / "tasks.json")
