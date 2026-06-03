from __future__ import annotations

import difflib
from typing import Any


MAX_TOOL_TEXT_CHARS = 6000
MATERIAL_LABELS = {
    "readme": "README.md",
    "final_code": "final/taskflow.py",
    "tests": "tests/test_taskflow.py",
    "initial_prompt": "ai/initial_prompt.md",
    "initial_response": "ai/initial_response.md",
    "initial_code": "ai/initial_code.py",
    "full_conversation": "ai/full_conversation.md",
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
        elif tool == "compare_initial_final_code":
            result = _compare_initial_final_code(material_texts, args)
        elif tool == "get_static_analysis":
            result = {
                "missing": analysis.get("missing", []),
                "code": analysis.get("code", {}),
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
        "tests": "学生最终测试代码",
        "initial_prompt": "第一次请求 AI 生成代码的 prompt",
        "initial_response": "AI 第一次回复或结果摘要",
        "initial_code": "AI 第一次生成的原始代码",
        "full_conversation": "后续所有 AI 协作对话",
        "student_report": "学生最终报告、实现方法、迭代记录和反思",
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


def _compare_initial_final_code(material_texts: dict[str, str], args: dict[str, Any]) -> dict[str, Any]:
    max_lines = max(60, min(240, int(args.get("max_lines", 140) or 140)))
    initial = material_texts.get("initial_code", "").splitlines()
    final = material_texts.get("final_code", "").splitlines()
    diff = list(difflib.unified_diff(
        initial,
        final,
        fromfile="ai/initial_code.py",
        tofile="final/taskflow.py",
        lineterm="",
        n=2,
    ))
    omitted = max(0, len(diff) - max_lines)
    return {
        "diff": _limit("\n".join(diff[:max_lines])),
        "omitted_lines": omitted,
        "initial_line_count": len(initial),
        "final_line_count": len(final),
    }


def _limit(text: str) -> str:
    if len(text) <= MAX_TOOL_TEXT_CHARS:
        return text
    return text[:MAX_TOOL_TEXT_CHARS] + "\n...[truncated]"

