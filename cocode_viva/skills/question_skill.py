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
            "text": "请说明 TaskFlow 的任务数据模型如何支持优先级、截止日期、标签、归档状态和统计功能。哪些字段是你后来从 AI 初版中调整或新增的？",
            "focus": "能否解释高级字段和最终代码相对 AI 初版的演进。",
        },
        {
            "id": "q2",
            "dimension": "AI 协作",
            "text": "请比较 `ai/initial_code.py` 和 `final/taskflow.py`：你认为最关键的三处变化是什么？每一处变化解决了 AI 初版的什么问题？",
            "focus": "是否能把个人贡献落到初版代码和最终代码的具体差异上。",
        },
        {
            "id": "q3",
            "dimension": "测试验证",
            "text": "你的测试如何覆盖组合查询、排序、非法输入、导入导出或归档等必做工程功能？请举一个测试说明它防止了什么 AI 常见错误。",
            "focus": "是否理解测试应验证必做功能组合，而不是只跑通基本增删改查。",
        },
        {
            "id": "q4",
            "dimension": "过程反思",
            "text": "请选 `ai/full_conversation.md` 中最能体现你个人思考的一轮，说明那轮提示词的目标、AI 建议的价值或问题，以及你最终如何取舍。",
            "focus": "是否有明确的提示策略、验证动作和工程取舍。",
        },
    ]

    if not features["date_validation"]:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "text": "如果用户输入非法截止日期、非法优先级或不存在的标签筛选条件，你的程序应该如何处理？当前实现是否覆盖？",
            "focus": "追问未明显体现的日期校验能力。",
        })
    else:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "text": "你是如何校验截止日期格式的？当日期校验与排序、统计或导入功能结合时，最容易出现什么边界错误？",
            "focus": "确认学生理解日期校验实现。",
        })

    if not features["import_export"]:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "text": "作业要求包含导入导出能力。请说明你为什么没有实现，或者如果要补充，你会如何设计文件格式、冲突处理和校验流程？",
            "focus": "追问缺失的必做工程功能和设计补救能力。",
        })
    else:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "text": "导入导出功能如何处理重复 id、字段缺失或损坏 JSON？你是否保留了数据校验的一致入口？",
            "focus": "考察数据迁移和持久化的健壮性。",
        })

    if interaction["rounds"] < 5:
        questions.append({
            "id": "q7",
            "dimension": "原创性",
            "text": "你的 AI 交互记录少于要求的 5 轮有效迭代。请说明最终代码中哪些关键修改来自你的独立判断，而不是直接复制 AI 输出。",
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
            "text": "最终报告中你声称的关键贡献，哪一项最能体现你的工程能力？请结合具体函数、测试和 AI 对话记录说明。",
            "focus": "要求把贡献落到具体证据上。",
        })

    return questions
