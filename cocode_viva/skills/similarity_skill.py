from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from cocode_viva.config import SESSION_DIR


HIGH_THRESHOLD = 0.88
MEDIUM_THRESHOLD = 0.72
MIN_FUNCTION_SHINGLES = 32


def analyze_similarity(current_session_id: str, source: str, current_student_id: str = "") -> dict[str, Any]:
    if not source.strip():
        return {
            "enabled": True,
            "risk_level": "low",
            "risk_label": "无法查重",
            "highest_similarity": 0,
            "matches": [],
            "note": "未读取到终版代码，无法进行代码相似度分析。",
        }
    current = _fingerprint(source)
    comparisons = []
    for path in sorted(SESSION_DIR.glob("*.json")):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if session.get("id") == current_session_id:
            continue
        portal = session.get("portal") or {}
        if current_student_id and portal.get("student_id") == current_student_id:
            continue
        other_source = ((session.get("material_texts") or {}).get("final_code") or "")
        if not other_source:
            continue
        other = _fingerprint(other_source)
        score = _overall_similarity(current, other)
        function_matches = _function_matches(current, other)
        if score >= MEDIUM_THRESHOLD or any(item["score"] >= HIGH_THRESHOLD for item in function_matches):
            comparisons.append({
                "session_id": session.get("id", path.stem),
                "student_name": portal.get("student_name", "未知学生"),
                "assignment_title": portal.get("assignment_title", "未知作业"),
                "overall": round(score, 3),
                "matched_functions": function_matches[:6],
            })

    comparisons.sort(key=lambda item: (item["overall"], max([fn["score"] for fn in item["matched_functions"]] or [0])), reverse=True)
    top = comparisons[:5]
    highest = top[0]["overall"] if top else 0
    high_function = any(fn["score"] >= HIGH_THRESHOLD for item in top for fn in item["matched_functions"])
    if highest >= HIGH_THRESHOLD:
        risk_level = "high"
        risk_label = "代码相似度高"
    elif highest >= MEDIUM_THRESHOLD or high_function:
        risk_level = "medium"
        risk_label = "代码相似需复核"
    else:
        risk_level = "low"
        risk_label = "未发现高相似"
    return {
        "enabled": True,
        "risk_level": risk_level,
        "risk_label": risk_label,
        "highest_similarity": round(highest, 3),
        "matches": top,
        "note": "相似度只作为教师复核风险提示，不直接参与自动扣分。",
    }


def _fingerprint(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source or "\n")
    except SyntaxError:
        return {"tokens": set(), "functions": {}}
    normalizer = _Normalizer()
    normalized = normalizer.visit(tree)
    ast.fix_missing_locations(normalized)
    tokens = _shingles(_node_tokens(normalized))
    functions = {}
    for node in normalized.body:
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = _shingles(_node_tokens(node), size=4)
    return {"tokens": tokens, "functions": functions}


def _overall_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    return _jaccard(left["tokens"], right["tokens"])


def _function_matches(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    matches = []
    for name, left_tokens in left["functions"].items():
        best_name = ""
        best_score = 0.0
        for other_name, right_tokens in right["functions"].items():
            if len(left_tokens) < MIN_FUNCTION_SHINGLES or len(right_tokens) < MIN_FUNCTION_SHINGLES:
                continue
            score = _jaccard(left_tokens, right_tokens)
            if score > best_score:
                best_score = score
                best_name = other_name
        if best_score >= MEDIUM_THRESHOLD:
            matches.append({
                "function": name,
                "matched_function": best_name,
                "score": round(best_score, 3),
            })
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _node_tokens(node: ast.AST) -> list[str]:
    tokens = []
    for child in ast.walk(node):
        tokens.append(type(child).__name__)
        if isinstance(child, ast.Call):
            tokens.append("call:" + _call_name(child.func))
        elif isinstance(child, ast.Attribute):
            tokens.append("attr:" + child.attr)
        elif isinstance(child, ast.FunctionDef):
            tokens.append("func")
        elif isinstance(child, ast.Import):
            tokens.extend("import:" + alias.name.split(".")[0] for alias in child.names)
        elif isinstance(child, ast.ImportFrom) and child.module:
            tokens.append("import:" + child.module.split(".")[0])
        elif isinstance(child, ast.Constant):
            tokens.append("const:" + type(child.value).__name__)
    return tokens


def _shingles(tokens: list[str], size: int = 5) -> set[str]:
    if not tokens:
        return set()
    if len(tokens) <= size:
        return {"|".join(tokens)}
    return {
        "|".join(tokens[index:index + size])
        for index in range(0, len(tokens) - size + 1)
    }


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return type(node).__name__


class _Normalizer(ast.NodeTransformer):
    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = "ARG"
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="VAR", ctx=node.ctx), node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="STR"), node)
        if isinstance(node.value, (int, float, complex)):
            return ast.copy_location(ast.Constant(value=0), node)
        return node
