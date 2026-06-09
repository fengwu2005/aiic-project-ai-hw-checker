from __future__ import annotations

from statistics import mean


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _answer_is_no_knowledge(answer: str) -> bool:
    lowered = answer.strip().lower()
    if not lowered:
        return True
    if lowered in {"不会", "不知道", "不清楚", "不懂", "不会回答", "答不上来", "idk"}:
        return True
    terms = ["我不会", "不知道怎么", "不清楚怎么", "不懂", "没看懂", "答不上来", "不会回答", "仍然不会", "i don't know"]
    return any(term in lowered for term in terms)


def _has_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _answer_understanding_hits(answer: str) -> dict[str, bool]:
    return {
        "principle": _has_any(answer, [
            "原理", "因为", "所以", "本质", "目的", "作用", "为什么", "为了", "原因",
            "就是", "相当于", "通过", "用来", "核心", "principle", "because", "so that",
        ]),
        "process": _has_any(answer, [
            "先", "再", "然后", "最后", "步骤", "过程", "流程", "遍历", "计算", "转换",
            "取", "判断", "处理", "输入", "输出", "结果", "step", "process",
        ]),
        "image_concept": _has_any(answer, [
            "pil", "pillow", "image", "pixel", "rgb", "kernel", "laplacian",
            "图像", "像素", "通道", "窗口", "卷积", "滤波", "裁剪", "反色", "旋转",
            "模糊", "边缘", "中值", "尺寸", "坐标", "颜色",
        ]),
        "validation": _has_any(answer, [
            "验证", "测试", "验收", "检查", "对比", "预期", "样例", "输入", "输出",
            "test", "expected", "assert",
        ]),
        "implementation": _has_any(answer, [
            "函数", "接口", "代码", "实现", "修改", "文件", "image_ops.py",
            "load_image", "resize_image", "crop_image", "invert_image", "blur_image",
            "edge_detect", "median_filter", "transform_image",
        ]),
    }


def _local_answer_relevance(question: dict, answer: str) -> int:
    text = f"{question.get('text', '')} {question.get('focus', '')} {question.get('dimension', '')}".lower()
    answer_lower = answer.lower()
    score = 0
    topics = [
        (["验证", "测试", "验收", "判断", "正确"], ["验证", "测试", "验收", "检查", "对比", "预期", "正确", "结果"]),
        (["原理", "为什么", "原因", "目的"], ["原理", "因为", "所以", "目的", "为了", "作用", "本质"]),
        (["过程", "步骤", "怎么", "如何"], ["先", "再", "然后", "过程", "步骤", "计算", "处理", "转换", "遍历"]),
        (["像素", "rgb", "通道", "颜色"], ["像素", "rgb", "通道", "颜色", "亮度"]),
        (["卷积", "边缘", "核"], ["卷积", "边缘", "kernel", "laplacian", "核"]),
        (["滤波", "模糊", "中值", "窗口"], ["滤波", "模糊", "中值", "窗口", "邻域", "平均"]),
        (["裁剪", "坐标", "边界"], ["裁剪", "坐标", "边界", "范围", "越界"]),
        (["输入", "输出", "结果"], ["输入", "输出", "结果", "返回", "得到"]),
    ]
    for question_terms, answer_terms in topics:
        if any(term in text for term in question_terms) and any(term in answer_lower for term in answer_terms):
            score += 1
    return score


IMAGE_CORE_FEATURES = [
    "image_io",
    "resize",
    "rotate",
    "crop",
    "invert",
    "blur",
    "edge_detection",
    "median_filter",
]

IMAGE_ENGINEERING_FEATURES = [
    "cli_interface",
    "pixel_access",
    "parameter_validation",
    "error_handling",
]

FUNCTION_API = [
    "load_image",
    "save_image",
    "resize_image",
    "rotate_image",
    "crop_image",
    "invert_image",
    "blur_image",
    "edge_detect",
    "median_filter",
    "transform_image",
]


def _hidden_case_names(execution: dict, ok: bool | None = None) -> list[str]:
    names = []
    for case in execution.get("cases", []):
        if ok is None or bool(case.get("ok")) is ok:
            names.append(str(case.get("name", "")))
    return names


def _failed_core_algorithms(execution: dict) -> list[str]:
    failed = " ".join(_hidden_case_names(execution, ok=False)).lower()
    core = []
    for label, keyword in [
        ("blur", "blur_image"),
        ("edge", "edge_detect"),
        ("median", "median_filter"),
        ("dispatcher", "transform_image"),
        ("api", "required image function api"),
    ]:
        if keyword in failed:
            core.append(label)
    return core


def score_materials(analysis: dict) -> dict:
    code = analysis["code"]
    interaction = analysis["interaction"]
    missing = analysis["missing"]
    execution = analysis.get("execution", {})

    features = code["features"]
    functions = set(code.get("functions", []))
    hidden_total = int(execution.get("total") or 0)
    hidden_passed = int(execution.get("passed") or 0)
    hidden_rate = hidden_passed / hidden_total if hidden_total else 0
    failed_core = _failed_core_algorithms(execution)

    core_score = sum(1 for name in IMAGE_CORE_FEATURES if features.get(name))
    engineering_score = sum(1 for name in IMAGE_ENGINEERING_FEATURES if features.get(name))
    api_score = sum(1 for name in FUNCTION_API if name in functions)

    functionality = _clamp(
        round(core_score / len(IMAGE_CORE_FEATURES) * 12)
        + round(api_score / len(FUNCTION_API) * 5)
        + round(hidden_rate * 6)
        + (2 if not missing else 0),
        0,
        25,
    )
    if hidden_total:
        if hidden_rate < 0.4:
            functionality = min(functionality, 10)
        elif hidden_rate < 0.75:
            functionality = min(functionality, 15)
        elif hidden_passed < hidden_total:
            functionality = min(functionality, 20)
        if len(failed_core) >= 3:
            functionality = min(functionality, 16)
        elif failed_core:
            functionality = min(functionality, 20)
    code_quality = _clamp(
        (3 if code["syntax_ok"] else 0)
        + round(api_score / len(FUNCTION_API) * 5)
        + round(engineering_score / len(IMAGE_ENGINEERING_FEATURES) * 4)
        + (2 if code.get("line_count", 0) >= 80 else 1 if code.get("line_count", 0) >= 40 else 0)
        + (1 if not missing else 0),
        0,
        15,
    )
    if hidden_total:
        if hidden_rate < 0.4:
            code_quality = min(code_quality, 6)
        elif hidden_rate < 0.75:
            code_quality = min(code_quality, 9)
        elif hidden_passed < hidden_total:
            code_quality = min(code_quality, 12)
        if "api" in failed_core:
            code_quality = min(code_quality, 6)
    validation = _clamp(round(hidden_rate * 15), 0, 15)
    process = _clamp(
        interaction["report_specificity"] * 3
        + (3 if interaction["mentions_implementation"] else 0)
        + (3 if interaction["mentions_validation"] else 0)
        + (2 if interaction["mentions_personal_changes"] else 0)
        + min(len(interaction["thinking_terms"]), 4),
        0,
        15,
    )
    report_chars = interaction["student_report_chars"]
    if report_chars < 200:
        process = min(process, 4)
    elif report_chars < 500:
        process = min(process, 8)
    elif report_chars < 900:
        process = min(process, 12)
    report_score = _clamp(
        (4 if interaction["student_report_chars"] >= 1200 else 3 if interaction["student_report_chars"] >= 700 else 2)
        + (2 if interaction["mentions_implementation"] else 0)
        + (2 if interaction["mentions_validation"] else 0)
        + (1 if interaction["mentions_limitations"] else 0)
        + (1 if interaction["mentions_personal_changes"] else 0),
        0,
        10,
    )
    if report_chars < 200:
        report_score = min(report_score, 3)
    elif report_chars < 500:
        report_score = min(report_score, 5)
    elif report_chars < 900:
        report_score = min(report_score, 7)

    return {
        "functionality": functionality,
        "code_quality": code_quality,
        "validation": validation,
        "process": process,
        "report": report_score,
    }


def score_defense(questions: list[dict], answers: dict[str, str]) -> dict:
    per_question = []
    non_empty_answers = []
    for question in questions:
        answer = answers.get(question["id"], "").strip()
        if answer:
            non_empty_answers.append(answer)
        score = 0
        evidence_hits = []
        gaps = []
        if not _answer_is_no_knowledge(answer):
            hits = _answer_understanding_hits(answer)
            understanding_count = sum(hits.values())
            relevance = _local_answer_relevance(question, answer)
            score = min(5, max(0, understanding_count + min(relevance, 2)))
            if score >= 4:
                evidence_hits.append("回答基本答中了当前问题，并体现出理解。")
            elif score >= 2:
                evidence_hits.append("回答和当前问题相关，但理解说明还不完整。")
                gaps.append("需要更直接地回答本题问的核心点。")
            else:
                gaps.append("回答没有明显答中当前问题，难以判断是否理解。")
        else:
            gaps.append("学生表示不会或没有提供可评分信息。")

        if not gaps and score < 5:
            gaps.append("回答可用；如果能更直接回应本题核心，会更容易判断掌握程度。")
        per_question.append({
            "id": question["id"],
            "dimension": question["dimension"],
            "question": question["text"],
            "evidence": question.get("evidence", ""),
            "focus": question.get("focus", ""),
            "answer": answer,
            "score": score,
            "max_score": 5,
            "evidence_hits": evidence_hits,
            "gaps": gaps,
            "comment": _question_comment(score, evidence_hits, gaps),
        })

    raw = sum(item["score"] for item in per_question)
    max_raw = max(1, len(per_question) * 5)
    defense_score = round(raw / max_raw * 20)
    avg_answer_len = round(mean([len(item["answer"]) for item in per_question]) if per_question else 0)
    unique_answers = len({answer.strip() for answer in non_empty_answers})
    weak_answers = sum(
        1
        for answer in non_empty_answers
        if len(answer.strip()) < 40 and sum(_answer_understanding_hits(answer).values()) < 2
    )
    no_knowledge_answers = sum(1 for answer in non_empty_answers if _answer_is_no_knowledge(answer))
    answered_count = len(non_empty_answers)
    validity = "valid"
    if (
        answered_count == 0
        or no_knowledge_answers >= 2
        or defense_score <= 3
        or weak_answers >= max(1, answered_count - 1)
        or unique_answers <= 1 and answered_count >= 3
    ):
        validity = "invalid"
    elif no_knowledge_answers == 1 or defense_score <= 8 or weak_answers >= max(1, answered_count // 2):
        validity = "weak"
    elif defense_score <= 14:
        validity = "partial"
    return {
        "score": defense_score,
        "raw": raw,
        "max_raw": max_raw,
        "per_question": per_question,
        "avg_answer_len": avg_answer_len,
        "answered_count": answered_count,
        "weak_answers": weak_answers,
        "no_knowledge_answers": no_knowledge_answers,
        "unique_answers": unique_answers,
        "validity": validity,
    }


def _question_comment(score: int, evidence_hits: list[str], gaps: list[str]) -> str:
    if score >= 4:
        return "回答能体现对原理、过程或验证方式的真实理解。"
    if score >= 2:
        return f"回答部分有效；主要缺口：{gaps[0] if gaps else '还需要更清楚地解释原理或过程。'}"
    return f"回答理解证据不足；主要问题：{gaps[0] if gaps else '缺少原理、过程或验证说明。'}"


def _validity_from_scores(per_question: list[dict], no_knowledge_answers: int, unique_answers: int, answered_count: int) -> str:
    raw = sum(int(item.get("score", 0)) for item in per_question)
    max_raw = max(1, len(per_question) * 5)
    defense_score = round(raw / max_raw * 20)
    low_scores = sum(1 for item in per_question if int(item.get("score", 0)) <= 1)
    partial_scores = sum(1 for item in per_question if int(item.get("score", 0)) <= 2)
    if (
        answered_count == 0
        or no_knowledge_answers >= 2
        or defense_score <= 3
        or low_scores >= max(1, answered_count - 1)
        or unique_answers <= 1 and answered_count >= 3
    ):
        return "invalid"
    if no_knowledge_answers == 1 or defense_score <= 8 or partial_scores >= max(1, answered_count // 2 + 1):
        return "weak"
    if defense_score <= 14:
        return "partial"
    return "valid"


def apply_answer_evaluation(report: dict, evaluation: dict) -> dict:
    existing_items = report.get("per_question", [])
    evaluation_items = {
        str(item.get("id", "")): item
        for item in evaluation.get("per_question", [])
        if isinstance(item, dict)
    }
    updated_items = []
    for item in existing_items:
        judged = evaluation_items.get(str(item.get("id", "")))
        if not judged:
            updated_items.append(item)
            continue
        score = _clamp(int(judged.get("score", 0)), 0, 5)
        strengths = [str(text) for text in judged.get("strengths", []) if str(text).strip()]
        gaps = [str(text) for text in judged.get("gaps", []) if str(text).strip()]
        verdict = str(judged.get("verdict", "")).strip()
        updated_items.append({
            **item,
            "score": score,
            "evidence_hits": strengths,
            "gaps": gaps,
            "comment": verdict or _question_comment(score, strengths, gaps),
            "scored_by": "api_agent",
        })

    raw = sum(int(item.get("score", 0)) for item in updated_items)
    max_raw = max(1, len(updated_items) * 5)
    defense_score = round(raw / max_raw * 20)
    detail = dict(report.get("defense_detail", {}))
    detail["raw"] = raw
    detail["max_raw"] = max_raw

    validity = str(evaluation.get("validity", "")).strip()
    if validity not in {"valid", "partial", "weak", "invalid"}:
        validity = _validity_from_scores(
            updated_items,
            int(detail.get("no_knowledge_answers", 0)),
            int(detail.get("unique_answers", 0)),
            int(detail.get("answered_count", 0)),
        )

    material_total = sum((report.get("material_scores") or {}).values())
    raw_total = material_total + defense_score
    total_cap, contribution_cap, cap_note = _defense_caps(validity, int(detail.get("no_knowledge_answers", 0)))

    total = min(raw_total, total_cap, int(report.get("total_cap", 100) or 100))
    contribution = _clamp(
        round(15 + defense_score * 2.4 + (report.get("material_scores") or {}).get("process", 0) * 1.2 + (report.get("material_scores") or {}).get("report", 0) * 1.3 + (report.get("material_scores") or {}).get("code_quality", 0) * 0.4),
        10,
        contribution_cap,
    )

    report["per_question"] = updated_items
    report["defense_score"] = defense_score
    report["defense_validity"] = validity
    report["defense_detail"] = detail
    report["raw_total"] = raw_total
    report["total_cap"] = min(total_cap, int(report.get("total_cap", 100) or 100))
    report["total"] = total
    report["contribution"] = contribution
    report["contribution_level"] = _contribution_level(validity, contribution)
    report["answer_evaluation_summary"] = str(evaluation.get("summary", "")).strip()
    if cap_note:
        report["cap_note"] = cap_note
    return report


def _defense_caps(validity: str, no_knowledge_answers: int) -> tuple[int, int, str]:
    if validity == "invalid":
        return (
            35 if no_knowledge_answers >= 2 else 42,
            25,
            "现场答辩回答没有答中问题或无法证明理解；即使作业包完整，也只能给出很低的本人掌握可信度判断。",
        )
    if validity == "weak":
        return (
            55,
            40,
            "现场答辩回答对问题的理解明显不足，材料证据不能充分转化为本人掌握证据；最终分数和掌握可信度被明显限制。",
        )
    if validity == "partial":
        return (
            72,
            60,
            "现场答辩只部分答中了问题，作业包质量不能完全等同于本人掌握，最终分数受到答辩闸门限制。",
        )
    return 100, 95, ""


def _contribution_level(validity: str, contribution: int) -> str:
    if validity == "invalid":
        return "较低"
    if validity == "weak":
        return "偏低"
    if validity == "partial":
        return "中等" if contribution >= 55 else "偏低"
    if contribution >= 75:
        return "较高"
    if contribution >= 55:
        return "中等"
    return "偏低"


def _build_risk_flags(analysis: dict, defense: dict, material_scores: dict) -> list[dict[str, str]]:
    flags = []
    execution = analysis.get("execution", {})
    interaction = analysis.get("interaction", {})
    hidden_total = int(execution.get("total") or 0)
    hidden_passed = int(execution.get("passed") or 0)

    if defense["validity"] == "invalid":
        flags.append({"level": "high", "label": "答辩无效", "detail": "学生未能说明关键原理、处理过程或验证方式。"})
    elif defense["validity"] == "weak":
        flags.append({"level": "high", "label": "答辩较弱", "detail": "回答尚未清楚体现对原理、过程或结果判断的掌握。"})
    elif defense["validity"] == "partial":
        flags.append({"level": "medium", "label": "答辩部分有效", "detail": "能解释部分内容，但对原理、过程或验证方式的说明还不够完整。"})

    if hidden_total and hidden_passed < hidden_total:
        flags.append({"level": "high", "label": "隐藏验收未全过", "detail": f"隐藏验收通过 {hidden_passed}/{hidden_total}。"})
    if not interaction.get("mentions_validation"):
        flags.append({"level": "medium", "label": "验证说明不足", "detail": "报告没有清楚说明测试输入、预期结果或验收方式。"})
    if not interaction.get("mentions_implementation"):
        flags.append({"level": "medium", "label": "实现说明不足", "detail": "报告没有把关键实现落到函数、接口或图像处理概念。"})
    if interaction.get("student_report_chars", 0) < 700:
        flags.append({"level": "medium", "label": "报告偏空泛", "detail": "报告长度或具体证据不足。"})
    if material_scores.get("validation", 0) >= 14 and defense["score"] <= 8:
        flags.append({"level": "high", "label": "代码强但答辩弱", "detail": "作业包表现较好，但学生未能解释清楚，需教师重点复核。"})
    similarity = analysis.get("similarity", {})
    if similarity.get("risk_level") == "high":
        flags.append({
            "level": "high",
            "label": "代码相似度高",
            "detail": f"与历史提交最高相似度 {similarity.get('highest_similarity', 0)}，建议教师重点追问相似函数。",
        })
    elif similarity.get("risk_level") == "medium":
        flags.append({
            "level": "medium",
            "label": "代码相似需复核",
            "detail": f"与历史提交最高相似度 {similarity.get('highest_similarity', 0)}，仅作为复核提示，不自动扣分。",
        })

    return flags


def _risk_summary(flags: list[dict[str, str]]) -> dict[str, str | int]:
    if any(flag["level"] == "high" for flag in flags):
        return {"rank": 3, "level": "high", "label": "高风险"}
    if any(flag["level"] == "medium" for flag in flags):
        return {"rank": 2, "level": "medium", "label": "需复核"}
    return {"rank": 1, "level": "low", "label": "常规"}


def build_report(analysis: dict, questions: list[dict], answers: dict[str, str]) -> dict:
    material_scores = score_materials(analysis)
    defense = score_defense(questions, answers)
    risk_flags = _build_risk_flags(analysis, defense, material_scores)
    risk_summary = _risk_summary(risk_flags)
    raw_total = sum(material_scores.values()) + defense["score"]
    execution = analysis.get("execution", {})
    hidden_total = int(execution.get("total") or 0)
    hidden_passed = int(execution.get("passed") or 0)
    hidden_rate = hidden_passed / hidden_total if hidden_total else 0
    failed_core = _failed_core_algorithms(execution)

    process = material_scores["process"]
    defense_score = defense["score"]
    report_score = material_scores["report"]
    code_quality = material_scores["code_quality"]

    # Defense is the main evidence that the submitted code and report reflect the
    # student's own understanding.
    contribution = _clamp(
        round(15 + defense_score * 2.4 + process * 1.2 + report_score * 1.3 + code_quality * 0.4),
        10,
        95,
    )

    cap_note = ""
    total_cap = 100
    contribution_cap = 95
    if defense["validity"] == "invalid":
        total_cap = 35 if defense["no_knowledge_answers"] >= 2 else 42
        contribution_cap = 25
        cap_note = "现场答辩回答无效，无法验证学生本人掌握程度；即使作业包完整，也只能给出很低的本人掌握可信度判断。"
    elif defense["validity"] == "weak":
        total_cap = 55
        contribution_cap = 40
        cap_note = "现场答辩回答明显不足，材料证据不能充分转化为本人掌握证据；最终分数和掌握可信度被明显限制。"
    elif defense["validity"] == "partial":
        total_cap = 72
        contribution_cap = 60
        cap_note = "现场答辩只部分证明理解，作业包质量不能完全等同于本人掌握，最终分数受到答辩闸门限制。"

    hidden_cap_note = ""
    if hidden_total and hidden_passed < hidden_total:
        if hidden_rate < 0.4:
            hidden_cap = 45
        elif hidden_rate < 0.75:
            hidden_cap = 60
        elif len(failed_core) >= 3:
            hidden_cap = 68
        else:
            hidden_cap = 80
        if hidden_cap < total_cap:
            total_cap = hidden_cap
            hidden_cap_note = (
                f"隐藏验收仅通过 {hidden_passed}/{hidden_total}，且失败项涉及核心图像函数；"
                "即使答辩能说明思路，也不能替代终版代码的实际完成度。"
            )
            cap_note = f"{cap_note} {hidden_cap_note}".strip()
        if hidden_rate < 0.75 or len(failed_core) >= 3:
            contribution_cap = min(contribution_cap, 55)

    total = min(raw_total, total_cap)
    contribution = min(contribution, contribution_cap)

    if defense["validity"] == "invalid":
        level = "较低"
    elif defense["validity"] == "weak":
        level = "偏低"
    elif defense["validity"] == "partial":
        level = "中等" if contribution >= 55 else "偏低"
    elif defense_score < 8 and process < 7:
        level = "较低"
    elif contribution >= 75:
        level = "较高"
    elif contribution >= 55:
        level = "中等"
    else:
        level = "偏低"

    strengths = []
    risks = []
    code = analysis["code"]
    interaction = analysis["interaction"]
    implemented_image_features = [
        name for name in IMAGE_CORE_FEATURES if code["features"].get(name)
    ]
    if len(implemented_image_features) >= 7:
        strengths.append("最终代码体现了较完整的图像读取、变换和滤波能力。")
    else:
        risks.append("未明显识别到完整图像处理功能，可能影响作业核心功能。")
    if interaction["mentions_implementation"] and interaction["mentions_validation"]:
        strengths.append("报告能同时说明实现方法和验证方式，可辅助判断学生掌握情况。")
    else:
        risks.append("报告对实现方法或验证方式说明不足，教师需要结合答辩重点复核。")
    if defense_score >= 14:
        strengths.append("答辩回答能较好说明实现原理、处理过程或验证方式。")
    elif defense_score < 9:
        risks.append("答辩回答没有充分说明原理、过程或结果判断，教师需要重点复核掌握情况。")
    if cap_note:
        risks.insert(0, cap_note)
    if execution:
        passed = execution.get("passed", 0)
        hidden_total = execution.get("total", 0)
        if hidden_total and passed == hidden_total:
            strengths.append(f"教师隐藏验收通过 {passed}/{hidden_total}，最终图像函数行为与作业接口要求一致。")
        else:
            risks.append(f"教师隐藏验收通过 {passed}/{hidden_total}，说明最终图像代码存在接口或行为缺口。")
            if failed_core:
                risks.append(f"核心失败项涉及：{', '.join(failed_core)}。")
    similarity = analysis.get("similarity", {})
    if similarity.get("matches"):
        top = similarity["matches"][0]
        function_names = [
            item.get("function", "")
            for item in top.get("matched_functions", [])
            if item.get("function")
        ][:4]
        risks.append(
            f"代码相似度提示：与 {top.get('student_name', '其他提交')} 的历史提交整体相似度 {top.get('overall')}；"
            f"相似函数包括 {', '.join(function_names) if function_names else '若干结构片段'}。该项仅提示教师复核，不直接计入分数。"
        )

    return {
        "total": total,
        "raw_total": raw_total,
        "total_cap": total_cap,
        "cap_note": cap_note,
        "material_scores": material_scores,
        "defense_score": defense["score"],
        "defense_validity": defense["validity"],
        "per_question": defense["per_question"],
        "defense_detail": {
            "raw": defense["raw"],
            "max_raw": defense["max_raw"],
            "avg_answer_len": defense["avg_answer_len"],
            "answered_count": defense["answered_count"],
            "weak_answers": defense["weak_answers"],
            "no_knowledge_answers": defense["no_knowledge_answers"],
            "unique_answers": defense["unique_answers"],
        },
        "contribution": contribution,
        "contribution_level": level,
        "risk_flags": risk_flags,
        "risk_rank": risk_summary["rank"],
        "risk_level": risk_summary["level"],
        "risk_label": risk_summary["label"],
        "strengths": strengths,
        "risks": risks,
        "basis": [
            "最终代码功能、结构和系统验收表现作为作业结果证据。",
            "教师隐藏验收结果作为代码真实行为证据。",
            "学生报告中的实现方法、验证说明和限制说明作为学习过程证据。",
            "现场答辩回答与终版代码、报告和隐藏验收的一致性作为理解程度证据。",
            "系统不判断学生是否使用外部工具，只判断终版成果和答辩能否证明掌握。",
            "若学生自主实现额外图像功能，教师可结合 README、隐藏验收、报告和答辩证据额外给出最多 5 分 bonus。",
        ],
        "similarity": analysis.get("similarity", {}),
        "privacy": analysis.get("privacy", {}),
    }
