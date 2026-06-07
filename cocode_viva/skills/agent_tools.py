from __future__ import annotations

from typing import Any


MAX_TOOL_TEXT_CHARS = 6000
MATERIAL_LABELS = {
    "readme": "README.md",
    "final_code": "final/image_ops.py",
    "student_report": "report/report.md",
}


def material_index(material_texts: dict[str, str], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    index = []
    for key, label in MATERIAL_LABELS.items():
        text = material_texts.get(key, "")
        meta = analysis.get("materials", {}).get(key, {})
        index.append({
            "key": key,
            "path": meta.get("found") or label,
            "chars": len(text),
            "description": _describe_material(key),
        })
    return index


def execute_tool_request(request: dict[str, Any], material_texts: dict[str, str], analysis: dict[str, Any]) -> dict[str, Any]:
    tool = str(request.get("tool", "")).strip()
    args = request.get("args") if isinstance(request.get("args"), dict) else {}

    try:
        if tool == "list_materials":
            result = material_index(material_texts, analysis)
        elif tool == "read_material":
            result = _read_material(material_texts, args)
        elif tool == "search_material":
            result = _search_material(material_texts, args)
        elif tool == "get_static_analysis":
            result = {
                "missing": analysis.get("missing", []),
                "code": analysis.get("code", {}),
                "execution": analysis.get("execution", {}),
                "interaction": analysis.get("interaction", {}),
            }
        else:
            return {
                "tool": tool,
                "ok": False,
                "error": f"unsupported tool: {tool}",
            }
        return {
            "tool": tool,
            "ok": True,
            "result": result,
        }
    except Exception as exc:
        return {
            "tool": tool,
            "ok": False,
            "error": str(exc),
        }


def execute_tool_requests(requests: list[dict[str, Any]], material_texts: dict[str, str], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        execute_tool_request(request, material_texts, analysis)
        for request in requests[:8]
        if isinstance(request, dict)
    ]


def _describe_material(key: str) -> str:
    descriptions = {
        "readme": "学生项目说明、运行方法、功能清单和限制",
        "final_code": "学生最终提交代码",
        "student_report": "学生最终报告、实现方法、验证说明和个人理解",
    }
    return descriptions.get(key, key)


def _read_material(material_texts: dict[str, str], args: dict[str, Any]) -> dict[str, Any]:
    key = str(args.get("key", "")).strip()
    if key not in MATERIAL_LABELS:
        raise ValueError("invalid material key")

    text = material_texts.get(key, "")
    start_line = max(1, int(args.get("start_line", 1) or 1))
    max_lines = max(1, min(160, int(args.get("max_lines", 80) or 80)))
    lines = text.splitlines()
    selected = lines[start_line - 1:start_line - 1 + max_lines]
    content = "\n".join(f"{start_line + idx}: {line}" for idx, line in enumerate(selected))
    return {
        "key": key,
        "path": MATERIAL_LABELS[key],
        "start_line": start_line,
        "end_line": start_line + len(selected) - 1 if selected else start_line,
        "content": _limit(content),
    }


def _search_material(material_texts: dict[str, str], args: dict[str, Any]) -> dict[str, Any]:
    key = str(args.get("key", "")).strip()
    query = str(args.get("query", "")).strip().lower()
    if key not in MATERIAL_LABELS:
        raise ValueError("invalid material key")
    if not query:
        raise ValueError("query is required")

    matches = []
    for line_no, line in enumerate(material_texts.get(key, "").splitlines(), start=1):
        if query in line.lower():
            matches.append({
                "line": line_no,
                "text": line[:500],
            })
            if len(matches) >= int(args.get("max_matches", 8) or 8):
                break
    return {
        "key": key,
        "query": query,
        "matches": matches,
    }


def _limit(text: str) -> str:
    if len(text) <= MAX_TOOL_TEXT_CHARS:
        return text
    return text[:MAX_TOOL_TEXT_CHARS] + "\n...[truncated]"
