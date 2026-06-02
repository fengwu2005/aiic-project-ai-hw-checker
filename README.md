# CoCode Viva：AI 协作编程作业答辩系统

CoCode Viva 是一个面向“允许学生使用 AI 完成编程作业”的答辩系统。系统固定作业为 **TaskFlow 命令行任务管理器**，学生提交 zip 作业包后，系统会读取最终代码、测试、AI 交互记录和反思报告，生成有限轮次答辩问题，并输出评分参考与个人贡献比例判断。

## 页面结构

系统只有三个页面：

1. 题目要求：展示 TaskFlow 作业背景、功能要求、固定提交格式和评分标准。
2. 提交与答辩：上传 zip，系统分析材料并生成现场答辩问题。
3. 评分报告：展示总分、分项得分、原创性判断、证据和风险提示。

## 运行方式

```bash
cd /home/ubuntu/fengwu/aiic-project0/project-1wk
python3 app.py
```

浏览器访问：

```text
http://127.0.0.1:8000
```

如果环境缺少依赖：

```bash
pip3 install -r requirements.txt
```

## 可选大模型配置

系统默认可以离线运行，使用本地规则生成问题和报告。如果需要接入 OpenAI-compatible API，可设置：

```bash
export OPENAI_API_KEY="你的 API Key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4.1-mini"
python3 app.py
```

当前实现会优先调用本地 skills 结构化读取提交材料，再把分析摘要交给大模型生成问题。没有 API key 时自动使用本地 QuestionSkill。

## 样例提交包

样例源码目录：

```text
examples/taskflow_sample_submission/
```

样例 zip：

```text
examples/taskflow_sample_submission.zip
```

系统第二页也提供“下载样例提交包”入口。

## 固定提交格式

学生提交 zip 内必须包含：

```text
TaskFlow_Submission/
  README.md
  final/
    taskflow.py
  tests/
    test_taskflow.py
  ai/
    ai_initial_prompt.md
    ai_initial_output.md
    interaction_log.md
  report/
    reflection.md
```

文件名是系统读取材料和生成答辩问题的重要依据。

## 本地 skills

- `ArchiveSkill`：安全解压 zip，限制路径穿越、文件数量和文件大小。
- `FileReaderSkill`：按固定命名读取提交材料。
- `CodeAnalysisSkill`：解析 Python AST，识别函数、类、导入、功能关键词和测试覆盖。
- `InteractionSkill`：分析 AI 交互轮次、提示具体度、反思中的个人判断证据。
- `QuestionSkill`：根据材料分析生成 7 个个性化答辩问题。
- `ScoringSkill`：根据材料证据和答辩回答生成评分参考。

## 交付物对应

- 作业题目与考核方法：见系统第一页和 `docs/assignment.md`
- 可运行答辩系统：`app.py`
- 设计说明文档：`docs/design.md`
- 学生提交样例：`examples/taskflow_sample_submission.zip`

