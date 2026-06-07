from __future__ import annotations

import json
from typing import Any

from cocode_viva.llm_client import LLMClient
from cocode_viva.skills.agent_tools import execute_tool_requests, material_index


ASSIGNMENT_BRIEF = """
固定作业：ImageLab 图像变换工具。
必做功能：读取图片、保存图片、放大、缩小、旋转、剪切/裁剪、反色、模糊、固定卷积核边缘提取、中值滤波。
提交材料：README、final/image_ops.py 终版代码、report/report.md 学生报告。
评分关注：教师隐藏验收、终版代码质量、报告中的实现与验证证据、答辩理解和掌握可信度。
Bonus：只有学生额外实现的图像功能才可能获得最多 5 分，不得弥补必做功能缺失。
""".strip()


class DefenseAgent:
    """LLM-driven defense agent with a small JSON tool protocol."""

    def __init__(self) -> None:
        self.client = LLMClient()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    async def generate_first_question(self, analysis: dict[str, Any], material_texts: dict[str, str]) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
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
            "task": (
                "请基于静态分析和工具证据只生成第 1 个现场答辩问题。"
                f"{_single_question_rule()}"
                f"{_short_question_rule()}"
                "这个问题应优先验证学生是否能解释终版代码中的关键实现、边界或验证方式。"
                f"只输出 JSON：{_question_output_schema()}"
            ),
            "analysis": _compact_analysis(analysis),
            "tool_results": tool_results,
        }, ensure_ascii=False)
        result = await self.client.chat_json(system, user)
        question = _normalize_single_question(_first_question_payload(result), "q1")
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
            "task": (
                "请根据上一问、学生上一轮回答、已问历史和工具证据生成下一道现场追问。"
                f"{_single_question_rule()}"
                f"{_short_question_rule()}"
                "不要重复已问问题；如果上一轮回答空泛，必须针对其缺口追问；"
                "如果上一轮回答扎实，则换到仍未验证的关键维度。"
                f"只输出 JSON：{_question_output_schema()}"
            ),
            "analysis": _compact_analysis(analysis),
            "tool_results": tool_results,
            "asked_questions": questions,
            "answers": answers,
            "previous_question": previous_question,
            "previous_answer": previous_answer,
        }, ensure_ascii=False)
        result = await self.client.chat_json(system, user)
        question = _normalize_single_question(_first_question_payload(result), next_id)
        return question, tool_results

    async def decide_next_step(
        self,
        analysis: dict[str, Any],
        material_texts: dict[str, str],
        questions: list[dict[str, Any]],
        answers: dict[str, str],
        previous_question: dict[str, Any],
        previous_answer: str,
        next_id: str,
        max_rounds: int,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if not self.enabled:
            return None, []

        tool_results = await self._collect_evidence(
            purpose="根据答辩历史决定继续追问或提前终止",
            analysis=analysis,
            material_texts=material_texts,
            answers=answers,
        )
        system = _system_prompt()
        user = json.dumps({
            "assignment": ASSIGNMENT_BRIEF,
            "task": (
                "请扮演真实课程答辩助教，根据已问问题、全部回答、上一问回答、材料证据和隐藏验收结果，决定下一步。"
                "你必须输出合法 JSON。"
                "action 只能是 ask 或 end_defense。"
                "答辩目标是公平考核学生真实理解，不是惩罚学生某一道题不会。"
                "如果学生单轮表示不会、不知道或答不上来，通常应继续 ask：可以降低难度、换一个维度、让学生解释文件、函数、报告或验收中的更基础证据。"
                "只有在已覆盖多个关键维度后，学生仍连续无法提供任何可验证细节，或已达到最大轮次，才应输出 end_defense。"
                "当仍有补救价值时，输出 ask，并生成一题更公平的追问；可以针对上一轮缺口，也可以切换到尚未验证但更基础的维度。"
                "当上一轮回答扎实时，才可以换到尚未验证的关键维度。"
                "不要重复已问问题。"
                f"{_single_question_rule()}"
                f"{_short_question_rule()}"
                f"输出格式：{_next_step_output_schema()}。"
                "如果 action=end_defense，question 可为 null。"
            ),
            "rules": {
                "max_rounds": max_rounds,
                "current_rounds": len(questions),
                "end_defense_when": [
                    "已达到最大轮次",
                    "已经至少完成 3 轮答辩，且学生多轮连续无法提供任何文件、函数、验收、报告或实现细节",
                    "学生明确拒绝继续答辩，或连续重复逃避且换维度后仍没有任何可评分证据",
                ],
                "ask_when": [
                    "学生只是一道题不会或某个维度答不上来，应换成更基础或不同维度的问题继续考核",
                    "上一轮有部分信息但证据不足，需要追问同一缺口",
                    "学生回答扎实，可以切换到未验证维度",
                ],
            },
            "analysis": _compact_analysis(analysis),
            "tool_results": tool_results,
            "asked_questions": questions,
            "answers": answers,
            "previous_question": previous_question,
            "previous_answer": previous_answer,
        }, ensure_ascii=False)
        result = await self.client.chat_json(system, user)
        return _normalize_next_step(result, next_id), tool_results

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
            "task": "请像严谨的计算机课程助教一样，根据终版代码、报告、隐藏验收和答辩回答生成最终评分参考。你只负责评分和证据判断，不要给学习建议，不要逐题打分，不要输出示范答案。若答辩回答过短或无效，必须显著降低本人掌握可信度判断。只输出 JSON，字段包括：total_adjustment_reason, contribution, contribution_level, strengths, risks, basis, bonus_suggestion。",
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
            "instruction": "你现在不能直接评分。请先选择要调用的本地工具来索取证据。只输出 JSON：{\"tool_requests\":[{\"tool\":\"read_material|search_material|get_static_analysis|list_materials\",\"args\":{...},\"reason\":\"...\"}]}。建议至少调用 get_static_analysis、read_material(final_code)、read_material(student_report)、read_material(readme) 或 search_material。",
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
        "你必须基于证据判断学生对终版代码和报告的理解程度。"
        "你不能臆测不存在的代码、报告内容或验收结果。"
        "需要材料细节时，通过指定 JSON 工具请求索取。"
        "输出必须是合法 JSON。"
    )


def _single_question_rule() -> str:
    return (
        "本次调用只能生成 1 个问题。"
        "禁止输出 questions 数组、候选题列表、题库、多个编号问题或任何备用问题。"
        "如果需要继续追问，也只能给当前这一轮的 1 个问题。"
    )


def _short_question_rule() -> str:
    return (
        "问题必须短小具体，尽量不超过 60 个中文字符。"
        "只问一个点，不要把多个问题用逗号、顿号或分号串起来。"
        "避免泛泛而谈，优先问具体函数、图像边界、输入输出、像素处理、报告证据或一个验收行为。"
        "不要只问宏观反思；问题应像真实教师现场追问实现方法和为什么这样做。"
    )


def _question_output_schema() -> str:
    return "{\"question\":{\"dimension\":\"...\",\"text\":\"...\",\"focus\":\"...\",\"evidence\":\"引用证据\"}}。禁止输出 questions 字段。"


def _next_step_output_schema() -> str:
    return "{\"action\":\"ask|end_defense\",\"reason\":\"...\",\"question\":{\"dimension\":\"...\",\"text\":\"...\",\"focus\":\"...\",\"evidence\":\"...\"}}。禁止输出 questions 字段。"


def _available_tools() -> list[dict[str, str]]:
    return [
        {"tool": "list_materials", "args": "{}", "description": "列出可读取的提交材料"},
        {"tool": "read_material", "args": "{\"key\":\"final_code\",\"start_line\":1,\"max_lines\":80}", "description": "按材料 key 和行号读取内容"},
        {"tool": "search_material", "args": "{\"key\":\"student_report\",\"query\":\"关键贡献\"}", "description": "在指定材料中搜索关键词"},
        {"tool": "get_static_analysis", "args": "{}", "description": "读取本地静态分析和隐藏验收摘要"},
    ]


def _default_tool_requests() -> list[dict[str, Any]]:
    return [
        {"tool": "get_static_analysis", "args": {}, "reason": "获取结构化静态分析"},
        {"tool": "read_material", "args": {"key": "final_code", "start_line": 1, "max_lines": 160}, "reason": "查看最终代码证据"},
        {"tool": "read_material", "args": {"key": "student_report", "start_line": 1, "max_lines": 140}, "reason": "查看学生报告、实现方法和验证说明"},
        {"tool": "read_material", "args": {"key": "readme", "start_line": 1, "max_lines": 100}, "reason": "查看运行说明和功能清单"},
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
        "source": str(raw.get("source", "api_agent")).strip() or "api_agent",
        "text": text,
        "focus": str(raw.get("focus", "考察学生对提交材料的真实理解。")).strip(),
        "evidence": str(raw.get("evidence", "")).strip(),
    }


def _first_question_payload(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return None
    question = raw.get("question")
    if isinstance(question, dict):
        return question
    questions = raw.get("questions")
    if isinstance(questions, list) and questions:
        return questions[0]
    return None


def _normalize_next_step(raw: Any, question_id: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action", "")).strip()
    if action not in {"ask", "end_defense"}:
        return None
    reason = str(raw.get("reason", "")).strip()
    if action == "end_defense":
        return {
            "action": "end_defense",
            "reason": reason or "系统助教判断继续追问已无法有效验证学生理解。",
            "question": None,
        }
    question = _normalize_single_question(_first_question_payload(raw), question_id)
    if not question:
        return None
    return {
        "action": "ask",
        "reason": reason,
        "question": question,
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
