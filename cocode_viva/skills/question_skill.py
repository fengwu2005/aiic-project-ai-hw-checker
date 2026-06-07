from __future__ import annotations


def _code_ref(analysis: dict, function_name: str) -> str:
    line = analysis.get("code", {}).get("function_lines", {}).get(function_name)
    if line:
        return f"final/image_ops.py:{line} `{function_name}`"
    return f"final/image_ops.py `{function_name}`"


def _hidden_case(analysis: dict, keyword: str) -> str:
    for case in analysis.get("execution", {}).get("cases", []):
        name = str(case.get("name", ""))
        if keyword.lower() in name.lower():
            return f"隐藏验收 `{name}`：{'通过' if case.get('ok') else '失败'}"
    return f"隐藏验收包含 `{keyword}` 相关用例"


def generate_questions(analysis: dict) -> list[dict]:
    code = analysis["code"]
    interaction = analysis["interaction"]
    features = code["features"]
    execution = analysis.get("execution", {})

    questions = [
        {
            "id": "q1",
            "dimension": "代码理解",
            "is_followup": False,
            "source": "local_seed",
            "text": "请解释 `load_image` 为什么要统一图像模式。",
            "focus": "考察是否理解图像模式、RGB 转换和后续像素处理的关系。",
            "evidence": _code_ref(analysis, "load_image"),
        },
        {
            "id": "q2",
            "dimension": "实现方法",
            "is_followup": False,
            "source": "local_seed",
            "text": "`blur_image` 的 3x3 均值是怎么计算的？",
            "focus": "考察是否能说明窗口、通道平均和边界处理。",
            "evidence": f"{_code_ref(analysis, 'blur_image')}；{_hidden_case(analysis, 'blur_image')}",
        },
        {
            "id": "q3",
            "dimension": "边界情况",
            "is_followup": False,
            "source": "local_seed",
            "text": "`crop_image` 如何判断裁剪框非法？为什么要这样做？",
            "focus": "考察参数校验、坐标边界和异常设计。",
            "evidence": f"{_code_ref(analysis, 'crop_image')}；{_hidden_case(analysis, 'parameter validation')}",
        },
        {
            "id": "q4",
            "dimension": "报告证据",
            "is_followup": False,
            "source": "local_seed",
            "text": "报告里最关键的实现，对应哪个函数？",
            "focus": "考察学生能否把报告描述绑定到具体代码证据。",
            "evidence": "report/report.md 的实现说明；final/image_ops.py 对应函数实现",
        },
    ]

    if not features["parameter_validation"]:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "is_followup": False,
            "source": "local_seed",
            "text": "非法缩放比例或裁剪框时，你的代码怎么处理？",
            "focus": "追问参数校验能力。",
            "evidence": _hidden_case(analysis, "parameter validation"),
        })
    else:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "is_followup": False,
            "source": "local_seed",
            "text": "你在哪个函数里校验图像参数？",
            "focus": "确认学生理解参数校验实现。",
            "evidence": f"{_code_ref(analysis, 'resize_image')}；{_code_ref(analysis, 'crop_image')}；{_code_ref(analysis, 'median_filter')}",
        })

    if not features["edge_detection"]:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "is_followup": False,
            "source": "local_seed",
            "text": "边缘检测没完成时，你会先补哪部分？",
            "focus": "追问缺失图像功能的补救设计。",
            "evidence": _hidden_case(analysis, "edge_detect"),
        })
    else:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "is_followup": False,
            "source": "local_seed",
            "text": "`edge_detect` 为什么要处理卷积结果的正负和范围？",
            "focus": "考察卷积响应、边缘强度、像素范围和 clamp 设计。",
            "evidence": f"{_code_ref(analysis, 'edge_detect')}；{_hidden_case(analysis, 'edge_detect')}",
        })

    if not interaction.get("mentions_validation"):
        questions.append({
            "id": "q7",
            "dimension": "验证说明",
            "is_followup": False,
            "source": "local_seed",
            "text": "你用什么输入验证图像函数正确？",
            "focus": "报告验证证据不足时追问测试输入、预期输出和验收意识。",
            "evidence": "report/report.md 验证说明；教师隐藏验收结果",
        })
    elif execution and execution.get("passed", 0) < execution.get("total", 0):
        questions.append({
            "id": "q7",
            "dimension": "系统验收",
            "is_followup": False,
            "source": "local_seed",
            "text": "隐藏验收失败时，你会先查哪个图像函数？",
            "focus": "考察对验收失败的定位能力。",
            "evidence": f"隐藏验收通过 {execution.get('passed', 0)}/{execution.get('total', 0)}",
        })
    else:
        questions.append({
            "id": "q7",
            "dimension": "掌握证据",
            "is_followup": False,
            "source": "local_seed",
            "text": "报告里哪项图像处理贡献最关键？对应哪个函数？",
            "focus": "要求把贡献落到具体证据上。",
            "evidence": "report/report.md 个人实现说明段落；final/image_ops.py 对应函数实现",
        })

    return questions[:5]
