from __future__ import annotations

import json
from typing import Any

from cocode_viva.llm_client import LLMClient
from cocode_viva.skills.agent_tools import execute_tool_requests, material_index


ASSIGNMENT_BRIEF = """
固定作业：TaskFlow Pro。
必做功能：任务数据模型、增删改查、状态更新、JSON 持久化、组合筛选、关键词搜索、排序、批量归档/完成、导入导出、统计摘要、至少 12 个测试。
AI 协作材料：第一次 prompt、第一次 AI 回复、AI 初版代码、完整后续对话、最终代码、测试、README、学生报告。
评分关注：最终代码质量、测试证据、AI 协作过程、答辩理解、原创性和个人贡献比例。
Bonus：只有学生自定义扩展功能才可能获得最多 5 分，不得弥补必做功能缺失。
""".strip()


class DefenseAgent:
    """LLM-driven defense agent with a small JSON tool protocol."""

    def __init__(self) -> None:
        self.client = LLMClient()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    async def generate_initial_question(self, analysis: dict[str, Any], material_texts: dict[str, str]) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
        if not self.enabled:
            return None, []

        tool_results = await self._collect_evidence(
            purpose="生成现场答辩问题",
            analysis=analysis,
            material_texts=material_texts,
        )
        system = _system_prompt()
        user = json.dumps({
            "assignment": ASSIGNMENT_BRIEF,
            "task": "请基于静态分析和工具证据只生成第 1 个现场答辩问题。这个问题应优先验证学生是否理解最终代码与 AI 初版代码的关键差异。只输出 JSON：{\"question\":{\"dimension\":\"...\",\"text\":\"...\",\"focus\":\"...\",\"evidence\":\"引用你使用的材料或工具证据\"}}",
            "analysis": _compact_analysis(analysis),
            "tool_results": tool_results,
        }, ensure_ascii=False)
        result = await self.client.chat_json(system, user)
        question = _normalize_single_question((result or {}).get("question"), "q1")
        return question, tool_results

    async def generate_next_question(
        self,
        analysis: dict[str, Any],
        material_texts: dict[str, str],
        questions: list[dict[str, Any]],
        answers: dict[str, str],
        previous_question: dict[str, Any],
        previous_answer: str,
        next_id: str,
    ) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
        if not self.enabled:
            return None, []

        tool_results = await self._collect_evidence(
            purpose="根据上一轮回答生成下一轮追问",
            analysis=analysis,
            material_texts=material_texts,
            answers=answers,
        )
        system = _system_prompt()
        user = json.dumps({
            "assignment": ASSIGNMENT_BRIEF,
            "task": "请根据上一问、学生上一轮回答、已问历史和工具证据生成下一道现场追问。不要重复已问问题；如果上一轮回答空泛，必须针对其缺口追问；如果上一轮回答扎实，则换到仍未验证的关键维度。只输出 JSON：{\"question\":{\"dimension\":\"...\",\"text\":\"...\",\"focus\":\"...\",\"evidence\":\"引用证据\"}}",
            "analysis": _compact_analysis(analysis),
            "tool_results": tool_results,
            "asked_questions": questions,
            "answers": answers,
            "previous_question": previous_question,
            "previous_answer": previous_answer,
        }, ensure_ascii=False)
        result = await self.client.chat_json(system, user)
        question = _normalize_single_question((result or {}).get("question"), next_id)
        return question, tool_results

    async def generate_report(
        self,
        analysis: dict[str, Any],
        material_texts: dict[str, str],
        questions: list[dict[str, Any]],
        answers: dict[str, str],
        rule_report: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if not self.enabled:
            return None, []

        tool_results = await self._collect_evidence(
            purpose="生成最终评分报告",
            analysis=analysis,
            material_texts=material_texts,
            answers=answers,
        )
        system = _system_prompt()
        user = json.dumps({
            "assignment": ASSIGNMENT_BRIEF,
            "task": "请像严谨的计算机课程助教一样，根据材料、工具证据和答辩回答生成最终评分参考。你只负责评分和证据判断，不要给学习建议，不要逐题打分，不要输出示范答案。若答辩回答过短或无效，必须显著降低本人掌握与原创性判断。只输出 JSON，字段包括：total_adjustment_reason, contribution, contribution_level, strengths, risks, basis, bonus_suggestion。",
            "analysis": _compact_analysis(analysis),
            "tool_results": tool_results,
            "questions": questions,
            "answers": answers,
            "rule_report": rule_report,
        }, ensure_ascii=False)
        result = await self.client.chat_json(system, user)
        if not isinstance(result, dict):
            return None, tool_results
        return _normalize_report_overlay(result), tool_results

    async def _collect_evidence(
        self,
        purpose: str,
        analysis: dict[str, Any],
        material_texts: dict[str, str],
        answers: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        system = _system_prompt()
        user = json.dumps({
            "assignment": ASSIGNMENT_BRIEF,
            "purpose": purpose,
            "instruction": "你现在不能直接评分。请先选择要调用的本地工具来索取证据。只输出 JSON：{\"tool_requests\":[{\"tool\":\"read_material|search_material|compare_initial_final_code|get_static_analysis|list_materials\",\"args\":{...},\"reason\":\"...\"}]}。建议至少调用 compare_initial_final_code、read_material(student_report)、read_material(tests)、read_material(full_conversation) 或 search_material。",
            "available_tools": _available_tools(),
            "material_index": material_index(material_texts, analysis),
            "static_analysis": _compact_analysis(analysis),
            "answers_preview": answers or {},
        }, ensure_ascii=False)
        result = await self.client.chat_json(system, user)
        requests = (result or {}).get("tool_requests")
        if not isinstance(requests, list) or not requests:
            requests = _default_tool_requests()
        return execute_tool_requests(requests, material_texts, analysis)


def _system_prompt() -> str:
    return (
        "你是专业、严格但公平的计算机课程助教 Agent。"
        "你必须基于证据判断学生理解程度和 AI 协作质量。"
        "你不能臆测不存在的代码或对话。"
        "需要材料细节时，通过指定 JSON 工具请求索取。"
        "输出必须是合法 JSON。"
    )


def _available_tools() -> list[dict[str, str]]:
    return [
        {"tool": "list_materials", "args": "{}", "description": "列出可读取的提交材料"},
        {"tool": "read_material", "args": "{\"key\":\"final_code\",\"start_line\":1,\"max_lines\":80}", "description": "按材料 key 和行号读取内容"},
        {"tool": "search_material", "args": "{\"key\":\"student_report\",\"query\":\"关键贡献\"}", "description": "在指定材料中搜索关键词"},
        {"tool": "compare_initial_final_code", "args": "{\"max_lines\":160}", "description": "比较 AI 初版代码和最终代码差异"},
        {"tool": "get_static_analysis", "args": "{}", "description": "读取本地静态分析摘要"},
    ]


def _default_tool_requests() -> list[dict[str, Any]]:
    return [
        {"tool": "get_static_analysis", "args": {}, "reason": "获取结构化静态分析"},
        {"tool": "compare_initial_final_code", "args": {"max_lines": 180}, "reason": "比较 AI 初版和最终版代码"},
        {"tool": "read_material", "args": {"key": "tests", "start_line": 1, "max_lines": 120}, "reason": "查看测试证据"},
        {"tool": "read_material", "args": {"key": "full_conversation", "start_line": 1, "max_lines": 140}, "reason": "查看 AI 协作过程"},
        {"tool": "read_material", "args": {"key": "student_report", "start_line": 1, "max_lines": 120}, "reason": "查看学生报告和反思"},
    ]


def _compact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "missing": analysis.get("missing", []),
        "materials": analysis.get("materials", {}),
        "code": analysis.get("code", {}),
        "interaction": analysis.get("interaction", {}),
    }


def _normalize_questions(raw: Any) -> list[dict[str, str]] | None:
    if not isinstance(raw, list) or len(raw) < 5:
        return None
    questions = []
    for index, item in enumerate(raw[:5], start=1):
        if not isinstance(item, dict):
            return None
        text = str(item.get("text", "")).strip()
        if not text:
            return None
        questions.append({
            "id": f"q{index}",
            "dimension": str(item.get("dimension", "综合能力")).strip() or "综合能力",
            "is_followup": False,
            "text": text,
            "focus": str(item.get("focus", "考察学生对提交材料的真实理解。")).strip(),
            "evidence": str(item.get("evidence", "")).strip(),
        })
    return questions


def _normalize_single_question(raw: Any, question_id: str) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text", "")).strip()
    if not text:
        return None
    return {
        "id": question_id,
        "dimension": str(raw.get("dimension", "综合能力")).strip() or "综合能力",
        "is_followup": False,
        "text": text,
        "focus": str(raw.get("focus", "考察学生对提交材料的真实理解。")).strip(),
        "evidence": str(raw.get("evidence", "")).strip(),
    }


def _normalize_report_overlay(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_adjustment_reason": str(raw.get("total_adjustment_reason", "")).strip(),
        "contribution": _safe_int(raw.get("contribution")),
        "contribution_level": str(raw.get("contribution_level", "")).strip(),
        "strengths": _string_list(raw.get("strengths")),
        "risks": _string_list(raw.get("risks")),
        "basis": _string_list(raw.get("basis")),
        "bonus_suggestion": str(raw.get("bonus_suggestion", "")).strip(),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:8]


def _safe_int(value: Any) -> int | None:
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, integer))
