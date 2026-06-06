from __future__ import annotations


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
            "text": "最终任务对象里，哪个字段是你补得最关键？为什么？",
            "focus": "能否解释一个具体字段及其工程意义。",
        },
        {
            "id": "q2",
            "dimension": "AI 协作",
            "is_followup": False,
            "source": "local_seed",
            "text": "AI 初版代码里，你最先修掉的一个问题是什么？",
            "focus": "是否能说出初版缺陷和自己的修改。",
        },
        {
            "id": "q3",
            "dimension": "系统验收",
            "is_followup": False,
            "source": "local_seed",
            "text": "隐藏验收会调用哪个函数？请举一个你实现的例子。",
            "focus": "是否理解固定函数接口和系统验收。",
        },
        {
            "id": "q4",
            "dimension": "过程反思",
            "is_followup": False,
            "source": "local_seed",
            "text": "哪一轮 AI 对话最体现你的判断？一句话说明。",
            "focus": "是否能指出具体 AI 协作证据。",
        },
    ]

    if not features["date_validation"]:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "is_followup": False,
            "source": "local_seed",
            "text": "非法日期输入时，你的代码会怎么处理？",
            "focus": "追问日期校验能力。",
        })
    else:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "is_followup": False,
            "source": "local_seed",
            "text": "你用哪个函数校验截止日期？",
            "focus": "确认学生理解日期校验实现。",
        })

    if not features["import_export"]:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "is_followup": False,
            "source": "local_seed",
            "text": "导入导出没完成时，你会先补哪个函数？",
            "focus": "追问缺失功能的补救设计。",
        })
    else:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "is_followup": False,
            "source": "local_seed",
            "text": "导入遇到重复 id 时，你怎么处理？",
            "focus": "考察数据迁移和持久化的健壮性。",
        })

    if interaction["rounds"] < 5:
        questions.append({
            "id": "q7",
            "dimension": "原创性",
            "is_followup": False,
            "source": "local_seed",
            "text": "最终代码里，哪一处最能证明是你自己改的？",
            "focus": "交互证据不足时追问个人贡献。",
        })
    elif execution and execution.get("passed", 0) < execution.get("total", 0):
        questions.append({
            "id": "q7",
            "dimension": "系统验收",
            "is_followup": False,
            "source": "local_seed",
            "text": "隐藏验收失败时，你会先查哪个函数？",
            "focus": "考察对验收失败的定位能力。",
        })
    else:
        questions.append({
            "id": "q7",
            "dimension": "原创性",
            "is_followup": False,
            "source": "local_seed",
            "text": "报告里哪一项贡献最关键？对应哪个函数？",
            "focus": "要求把贡献落到具体证据上。",
        })

    return questions[:5]
