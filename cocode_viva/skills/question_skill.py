from __future__ import annotations


def generate_questions(analysis: dict) -> list[dict]:
    code = analysis["code"]
    interaction = analysis["interaction"]
    features = code["features"]
    test_features = code["test_features"]

    questions = [
        {
            "id": "q1",
            "dimension": "代码理解",
            "text": "请说明 TaskFlow 中任务的数据结构是如何设计的，为什么这种结构适合支持添加、完成、筛选和持久化？",
            "focus": "能否解释核心数据模型，而不是只描述运行结果。",
        },
        {
            "id": "q2",
            "dimension": "AI 协作",
            "text": "AI 第一版代码中你认为最值得修改的一个问题是什么？你是如何发现并验证它的？",
            "focus": "是否能指出具体缺陷、验证方式和个人判断。",
        },
        {
            "id": "q3",
            "dimension": "测试验证",
            "text": "你提交的测试覆盖了哪些边界情况？请举一个测试用例说明它防止了什么错误。",
            "focus": "是否理解测试不是形式要求，而是验证 AI 代码的工具。",
        },
        {
            "id": "q4",
            "dimension": "过程反思",
            "text": "请选一轮你和 AI 的交互，说明那一轮提示词的目标、AI 的回应是否满足目标，以及你后续如何处理。",
            "focus": "是否有明确的提示策略和迭代意识。",
        },
    ]

    if not features["date_validation"]:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "text": "如果用户输入非法截止日期，例如 2026-02-31 或随意字符串，你的程序应该如何处理？当前实现是否覆盖？",
            "focus": "追问未明显体现的日期校验能力。",
        })
    else:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "text": "你是如何校验截止日期格式的？如果日期格式错误，程序返回什么信息，测试是否覆盖？",
            "focus": "确认学生理解日期校验实现。",
        })

    if not features["error_handling"]:
        questions.append({
            "id": "q6",
            "dimension": "健壮性",
            "text": "如果本地 JSON 数据文件不存在、为空或损坏，你的程序会发生什么？你会如何改进？",
            "focus": "追问文件持久化的异常处理。",
        })
    else:
        questions.append({
            "id": "q6",
            "dimension": "健壮性",
            "text": "你的异常处理主要覆盖了哪些场景？有没有可能隐藏真正的 bug？",
            "focus": "考察异常处理的边界意识。",
        })

    if interaction["rounds"] < 3:
        questions.append({
            "id": "q7",
            "dimension": "原创性",
            "text": "你的 AI 交互记录少于要求轮次。请说明最终代码中哪些关键修改来自你的独立判断，而不是直接复制 AI 输出。",
            "focus": "交互证据不足时追问个人贡献。",
        })
    elif not test_features["invalid_input"]:
        questions.append({
            "id": "q7",
            "dimension": "测试验证",
            "text": "你的测试中异常输入覆盖较弱。请现场设计一个非法输入测试，并说明预期结果。",
            "focus": "补充测试设计能力。",
        })
    else:
        questions.append({
            "id": "q7",
            "dimension": "原创性",
            "text": "最终代码中你最能体现个人贡献的一处修改是什么？请结合文件名、函数或测试说明。",
            "focus": "要求把贡献落到具体证据上。",
        })

    return questions

