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
            if len(answer) >= 50:
                score += 1
                evidence_hits.append("回答长度足以表达一个完整解释。")
            else:
                gaps.append("回答过短，难以判断是否真的理解。")
            if _has_any(answer, ["函数", "文件", "验收", "边界", "异常", "原因", "修改", "验证", "测试"]):
                score += 1
                evidence_hits.append("提到了函数、验证、边界或修改原因。")
            else:
                gaps.append("没有说明函数位置、边界处理或修改原因。")
            if _has_any(answer, ["pil", "image", "pixel", "rgb", "kernel", "laplacian", "卷积", "滤波", "像素", "裁剪", "反色", "通道", "窗口"]):
                score += 1
                evidence_hits.append("提到了图像处理概念，例如像素、RGB、卷积或滤波。")
            else:
                gaps.append("没有落到图像处理概念，容易变成泛泛回答。")
            if _has_any(answer, ["load_image", "resize_image", "crop_image", "invert_image", "blur_image", "edge_detect", "median_filter", "transform_image", "image_ops.py"]):
                score += 1
                evidence_hits.append("指出了具体函数或文件。")
            else:
                gaps.append("没有指出具体函数或文件，证据定位不足。")
            if _has_any(answer, ["我认为", "我决定", "我发现", "我实现", "我验证", "报告", "验收", "输入", "输出", "预期"]):
                score += 1
                evidence_hits.append("能把个人说明、报告或验证方式接到证据链上。")
            elif question.get("dimension") in {"报告证据", "验证说明"}:
                gaps.append("没有说明报告依据、验证方式或个人实现判断。")
            if len(answer) >= 160 and score >= 3:
                score = min(score + 1, 5)
                evidence_hits.append("回答较充分，能支撑进一步判断。")
        else:
            gaps.append("学生表示不会或没有提供可评分信息。")

        if not gaps and score < 5:
            gaps.append("回答可用，但还可以补充验证方式或更具体的代码细节。")
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
    weak_answers = sum(1 for answer in non_empty_answers if len(answer.strip()) < 40)
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
    elif defense_score <= 14 or (avg_answer_len < 70 and defense_score < 17):
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
        return "回答能较好落到代码、图像概念或验证证据。"
    if score >= 2:
        return f"回答部分有效；主要缺口：{gaps[0] if gaps else '证据还不够具体。'}"
    return f"回答证据不足；主要问题：{gaps[0] if gaps else '缺少可验证说明。'}"


def _build_risk_flags(analysis: dict, defense: dict, material_scores: dict) -> list[dict[str, str]]:
    flags = []
    execution = analysis.get("execution", {})
    interaction = analysis.get("interaction", {})
    hidden_total = int(execution.get("total") or 0)
    hidden_passed = int(execution.get("passed") or 0)

    if defense["validity"] == "invalid":
        flags.append({"level": "high", "label": "答辩无效", "detail": "学生未能提供足够的代码、图像概念或验证证据。"})
    elif defense["validity"] == "weak":
        flags.append({"level": "high", "label": "答辩较弱", "detail": "回答较短或缺少关键证据，无法充分证明本人掌握。"})
    elif defense["validity"] == "partial":
        flags.append({"level": "medium", "label": "答辩部分有效", "detail": "能解释部分内容，但证据链仍不完整。"})

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
        strengths.append("答辩回答能较好连接代码、系统验收和修改原因。")
    elif defense_score < 9:
        risks.append("答辩回答较短或泛化，和最终代码的对应关系不足。")
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
    }
