from __future__ import annotations

import ast
def analyze_code(source: str) -> dict:
    result = {
        "line_count": len([line for line in source.splitlines() if line.strip()]),
        "functions": [],
        "classes": [],
        "imports": [],
        "syntax_ok": True,
        "syntax_error": "",
        "features": {},
    }

    try:
        tree = ast.parse(source or "\n")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result["functions"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                result["classes"].append(node.name)
            elif isinstance(node, ast.Import):
                result["imports"].extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                result["imports"].append(node.module)
    except SyntaxError as exc:
        result["syntax_ok"] = False
        result["syntax_error"] = f"第 {exc.lineno} 行：{exc.msg}"

    lowered = source.lower()
    result["features"] = {
        "json_persistence": "json" in lowered and ("open(" in lowered or "pathlib" in lowered),
        "cli_interface": "argparse" in lowered or "click" in lowered or "sys.argv" in lowered,
        "priority": "priority" in lowered or "优先级" in lowered,
        "deadline": "deadline" in lowered or "due" in lowered or "截止" in lowered,
        "tags": "tags" in lowered or "tag" in lowered or "标签" in lowered,
        "keyword_search": "keyword" in lowered or "search" in lowered or "query" in lowered or "关键词" in lowered,
        "sort": "sort" in lowered or "sorted(" in lowered or "排序" in lowered,
        "statistics": "stats" in lowered or "statistics" in lowered or "count" in lowered or "统计" in lowered,
        "archive": "archived" in lowered or "archive" in lowered or "归档" in lowered,
        "batch_operation": "batch" in lowered or "bulk" in lowered or "ids" in lowered or "批量" in lowered,
        "import_export": "export_tasks" in lowered or "import_tasks" in lowered or "导入" in lowered or "导出" in lowered,
        "status_filter": "status" in lowered or "completed" in lowered or "done" in lowered,
        "id_generation": "uuid" in lowered or "next_id" in lowered or "max(" in lowered,
        "date_validation": "datetime" in lowered or "fromisoformat" in lowered or "strptime" in lowered,
        "error_handling": "try:" in lowered and "except" in lowered,
    }

    return result
