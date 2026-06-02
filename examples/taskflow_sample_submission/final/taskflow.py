import argparse
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path


DATA_FILE = Path("tasks.json")
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_STATUS = {"todo", "doing", "done", "archived"}
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD") from exc


def validate_priority(priority):
    if priority not in VALID_PRIORITIES:
        raise ValueError("priority must be high, medium, or low")
    return priority


def validate_status(status):
    if status not in VALID_STATUS:
        raise ValueError("status must be todo, doing, done, or archived")
    return status


def normalize_tags(tags):
    if tags is None:
        return []
    if isinstance(tags, str):
        raw_tags = tags.split(",")
    else:
        raw_tags = tags
    return sorted({tag.strip().lower() for tag in raw_tags if tag and tag.strip()})


def load_tasks(path=DATA_FILE):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("task data file is not valid JSON") from exc
    if not isinstance(data, list):
        raise ValueError("task data file must contain a list")
    return [normalize_task(item) for item in data]


def save_tasks(tasks, path=DATA_FILE):
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id(tasks):
    return max([int(task["id"]) for task in tasks], default=0) + 1


def normalize_task(task):
    if not isinstance(task, dict):
        raise ValueError("each task must be an object")
    required = {"id", "title", "priority", "deadline", "status"}
    missing = required - task.keys()
    if missing:
        raise ValueError(f"task missing fields: {', '.join(sorted(missing))}")

    normalized = {
        "id": int(task["id"]),
        "title": str(task["title"]).strip(),
        "description": str(task.get("description", "")).strip(),
        "priority": validate_priority(str(task["priority"])),
        "deadline": parse_date(str(task["deadline"])).isoformat(),
        "status": validate_status(str(task["status"])),
        "tags": normalize_tags(task.get("tags", [])),
        "created_at": str(task.get("created_at") or now_iso()),
        "updated_at": str(task.get("updated_at") or now_iso()),
    }
    if not normalized["title"]:
        raise ValueError("title cannot be empty")
    return normalized


def add_task(title, description="", priority="medium", deadline=None, tags=None, path=DATA_FILE):
    if deadline is None:
        raise ValueError("deadline is required")
    tasks = load_tasks(path)
    timestamp = now_iso()
    task = normalize_task({
        "id": next_id(tasks),
        "title": title,
        "description": description,
        "priority": priority,
        "deadline": deadline,
        "status": "todo",
        "tags": normalize_tags(tags),
        "created_at": timestamp,
        "updated_at": timestamp,
    })
    tasks.append(task)
    save_tasks(tasks, path)
    return task


def find_task(tasks, task_id):
    for task in tasks:
        if int(task["id"]) == int(task_id):
            return task
    raise ValueError("task not found")


def update_status(task_id, status, path=DATA_FILE):
    tasks = load_tasks(path)
    task = find_task(tasks, task_id)
    task["status"] = validate_status(status)
    task["updated_at"] = now_iso()
    save_tasks(tasks, path)
    return task


def complete_task(task_id, path=DATA_FILE):
    return update_status(task_id, "done", path)


def delete_task(task_id, path=DATA_FILE):
    tasks = load_tasks(path)
    filtered = [task for task in tasks if int(task["id"]) != int(task_id)]
    if len(filtered) == len(tasks):
        raise ValueError("task not found")
    save_tasks(filtered, path)
    return True


def batch_update_status(task_ids, status, path=DATA_FILE):
    tasks = load_tasks(path)
    ids = {int(task_id) for task_id in task_ids}
    changed = []
    for task in tasks:
        if int(task["id"]) in ids:
            task["status"] = validate_status(status)
            task["updated_at"] = now_iso()
            changed.append(task)
    if len(changed) != len(ids):
        raise ValueError("one or more tasks were not found")
    save_tasks(tasks, path)
    return changed


def archive_tasks(task_ids, path=DATA_FILE):
    return batch_update_status(task_ids, "archived", path)


def list_tasks(
    status=None,
    priority=None,
    tag=None,
    deadline_from=None,
    deadline_to=None,
    keyword=None,
    sort_by=None,
    include_archived=False,
    path=DATA_FILE,
):
    tasks = load_tasks(path)
    if not include_archived:
        tasks = [task for task in tasks if task["status"] != "archived"]
    if status:
        validate_status(status)
        tasks = [task for task in tasks if task["status"] == status]
    if priority:
        validate_priority(priority)
        tasks = [task for task in tasks if task["priority"] == priority]
    if tag:
        normalized_tag = tag.strip().lower()
        tasks = [task for task in tasks if normalized_tag in task["tags"]]
    if deadline_from:
        start = parse_date(deadline_from)
        tasks = [task for task in tasks if parse_date(task["deadline"]) >= start]
    if deadline_to:
        end = parse_date(deadline_to)
        tasks = [task for task in tasks if parse_date(task["deadline"]) <= end]
    if keyword:
        needle = keyword.lower()
        tasks = [
            task for task in tasks
            if needle in task["title"].lower() or needle in task["description"].lower()
        ]
    if sort_by:
        tasks = sort_tasks(tasks, sort_by)
    return tasks


def sort_tasks(tasks, sort_by):
    if sort_by == "deadline":
        return sorted(tasks, key=lambda task: parse_date(task["deadline"]))
    if sort_by == "priority":
        return sorted(tasks, key=lambda task: PRIORITY_RANK[task["priority"]])
    if sort_by == "created_at":
        return sorted(tasks, key=lambda task: task["created_at"])
    raise ValueError("sort_by must be deadline, priority, or created_at")


def export_tasks(destination, path=DATA_FILE):
    tasks = load_tasks(path)
    destination = Path(destination)
    destination.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(tasks)


def import_tasks(source, path=DATA_FILE):
    source = Path(source)
    try:
        imported = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("import file is not valid JSON") from exc
    if not isinstance(imported, list):
        raise ValueError("import file must contain a list")

    tasks = load_tasks(path)
    existing_ids = {int(task["id"]) for task in tasks}
    next_available = next_id(tasks)
    normalized_imports = []
    for item in imported:
        task = normalize_task(item)
        if int(task["id"]) in existing_ids:
            task["id"] = next_available
            next_available += 1
        existing_ids.add(int(task["id"]))
        normalized_imports.append(task)
    tasks.extend(normalized_imports)
    save_tasks(tasks, path)
    return len(normalized_imports)


def task_statistics(today=None, path=DATA_FILE):
    tasks = load_tasks(path)
    today_value = parse_date(today) if today else date.today()
    status_counter = Counter(task["status"] for task in tasks)
    tag_counter = Counter(tag for task in tasks for tag in task["tags"])
    overdue = [
        task for task in tasks
        if task["status"] not in {"done", "archived"} and parse_date(task["deadline"]) < today_value
    ]
    high_open = [
        task for task in tasks
        if task["priority"] == "high" and task["status"] not in {"done", "archived"}
    ]
    return {
        "total": len(tasks),
        "by_status": dict(status_counter),
        "overdue": len(overdue),
        "high_priority_open": len(high_open),
        "by_tag": dict(tag_counter),
    }


def build_parser():
    parser = argparse.ArgumentParser(description="TaskFlow Pro command line task manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("title")
    add_parser.add_argument("--description", default="")
    add_parser.add_argument("--priority", default="medium")
    add_parser.add_argument("--deadline", required=True)
    add_parser.add_argument("--tags", default="")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--priority")
    list_parser.add_argument("--tag")
    list_parser.add_argument("--from-date")
    list_parser.add_argument("--to-date")
    list_parser.add_argument("--keyword")
    list_parser.add_argument("--sort-by")
    list_parser.add_argument("--include-archived", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("task_id")
    status_parser.add_argument("status")

    done_parser = subparsers.add_parser("done")
    done_parser.add_argument("task_id")

    archive_parser = subparsers.add_parser("archive")
    archive_parser.add_argument("task_ids", nargs="+")

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("task_id")

    subparsers.add_parser("stats")

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("destination")

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("source")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "add":
            result = add_task(args.title, args.description, args.priority, args.deadline, args.tags)
        elif args.command == "list":
            result = list_tasks(
                status=args.status,
                priority=args.priority,
                tag=args.tag,
                deadline_from=args.from_date,
                deadline_to=args.to_date,
                keyword=args.keyword,
                sort_by=args.sort_by,
                include_archived=args.include_archived,
            )
        elif args.command == "status":
            result = update_status(args.task_id, args.status)
        elif args.command == "done":
            result = complete_task(args.task_id)
        elif args.command == "archive":
            result = archive_tasks(args.task_ids)
        elif args.command == "delete":
            result = {"deleted": delete_task(args.task_id)}
        elif args.command == "stats":
            result = task_statistics()
        elif args.command == "export":
            result = {"exported": export_tasks(args.destination)}
        elif args.command == "import":
            result = {"imported": import_tasks(args.source)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ValueError as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
