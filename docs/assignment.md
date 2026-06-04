# 作业题目：TaskFlow Pro - 使用 AI 协作实现可验收的智能任务管理器

## 一、作业背景

在 AI 辅助编程已经普及的背景下，学生直接让 AI 生成一个“能跑”的程序已经不能体现真实能力。AI 初版代码通常存在需求遗漏、边界处理薄弱、接口不稳定、结构冗长、异常处理不可靠等问题。

本作业允许并鼓励学生使用 AI，但要求学生完整记录从 AI 初版到最终版本的迭代过程，并在答辩中证明自己理解最终代码、能识别 AI 的问题、能根据系统验收要求修正程序、能说明自己的工程判断。

## 二、任务描述

请使用 Python 实现一个命令行任务管理器 `TaskFlow Pro`。它不是简单 Todo List，而是一个具备筛选、搜索、排序、批量操作、导入导出和统计能力的小型工程项目。

程序入口固定为：

```text
final/taskflow.py
```

核心功能必须使用 Python 标准库实现，便于教师和答辩系统本地复现。

## 三、任务数据模型

每个任务至少包含以下字段：

- `id`：任务唯一编号
- `title`：任务标题
- `description`：任务描述
- `priority`：任务优先级，只能是 `high`、`medium`、`low`
- `deadline`：截止日期，格式为 `YYYY-MM-DD`
- `status`：任务状态，至少包含 `todo`、`doing`、`done`、`archived`
- `tags`：标签列表，例如 `["course", "urgent"]`
- `created_at`：创建时间
- `updated_at`：更新时间

## 四、必做核心功能

命令行程序必须支持：

- 添加任务
- 删除任务
- 更新任务状态
- 完成任务
- 查看任务列表
- 查看单个任务详情
- 使用 JSON 文件持久化保存任务
- 对非法优先级、非法状态、非法日期、不存在的任务 id 给出明确错误

## 五、必做工程功能

最终程序必须支持以下工程功能，这些功能全部属于必做要求，不能作为 bonus 申报：

- 组合筛选：按状态、优先级、标签、截止日期范围组合筛选
- 关键词搜索：搜索标题和描述
- 排序：按截止日期、优先级、创建时间排序
- 批量操作：批量完成或批量归档多个任务
- 导入导出：导入/导出 JSON 数据，并处理重复 id、字段缺失、格式错误
- 统计摘要：输出不同状态数量、逾期任务数量、高优先级未完成数量、标签分布

## 六、固定函数接口与隐藏验收要求

为了让答辩系统能够在代码层面严格验证功能，`final/taskflow.py` 除了提供命令行入口外，必须暴露以下可调用函数。函数名不能修改；业务逻辑不能只写在 CLI 解析中。

- `add_task(title, description="", priority="medium", deadline=None, tags=None, path=DATA_FILE)`
- `list_tasks(status=None, priority=None, tag=None, deadline_from=None, deadline_to=None, keyword=None, sort_by=None, include_archived=False, path=DATA_FILE)`
- `update_status(task_id, status, path=DATA_FILE)`
- `complete_task(task_id, path=DATA_FILE)`
- `delete_task(task_id, path=DATA_FILE)`
- `batch_update_status(task_ids, status, path=DATA_FILE)`
- `archive_tasks(task_ids, path=DATA_FILE)`
- `export_tasks(destination, path=DATA_FILE)`
- `import_tasks(source, path=DATA_FILE)`
- `task_statistics(today=None, path=DATA_FILE)`

接口约束：

- 所有会读写任务数据的函数必须支持 `path` 参数，用于指定 JSON 数据文件，保证系统验收之间互不污染。
- 非法优先级、非法状态、非法日期、字段缺失、JSON 格式错误、不存在的任务 id 必须抛出明确异常，不能静默忽略或直接填默认值掩盖问题。
- `list_tasks` 默认不返回 `archived` 状态任务；传入 `include_archived=True` 时可以包含归档任务。
- `import_tasks` 遇到重复 id 必须有确定处理策略，例如重新分配 id，并保证最终数据中 id 唯一。
- `task_statistics(today=...)` 必须支持传入固定日期，便于系统验收逾期任务数量。
- 学生可以额外增加函数、类和 CLI 参数，但不能破坏上述接口。

答辩系统会使用教师隐藏验收用例导入 `final/taskflow.py`，在临时目录中调用这些函数，检查数据模型、增删改查、输入校验、组合筛选、搜索排序、批量操作、导入导出、统计摘要等行为。隐藏验收结果会影响“最终程序功能”和“系统验收与验证”得分。

## 七、自主扩展 Bonus

在完成全部必做功能的前提下，学生可以自由结合 AI 设计并实现额外功能。只有学生自定义扩展功能可以作为 bonus；上述必做核心功能和必做工程功能都不能算作 bonus。

扩展功能不是必做项，但如果设计合理、实现可运行，并且能在 README、报告和答辩中说明 AI 与学生各自的贡献，可以获得最多 5 分 bonus。

可选扩展示例：

- 自然语言添加任务，例如输入“下周三前完成实验报告，优先级高”
- 根据截止日期和优先级自动推荐今日任务
- 任务模板或周期性任务
- 简单的数据可视化或 Markdown 报表导出
- 任务提醒策略
- 更友好的交互式命令行模式
- 基于历史任务的智能标签建议

扩展功能要求：

- 必须在 `README.md` 中列出扩展功能的使用方式
- 必须在 `report/report.md` 中说明设计动机、实现方法、AI 提供了什么帮助、学生自己做了哪些判断和修改
- 扩展功能不能替代必做功能；如果必做要求缺失，bonus 不用于弥补必做得分

## 八、AI 协作要求

学生必须保留完整 AI 协作证据：

- 第一次请求 AI 生成代码的原始 prompt
- AI 第一次生成的结果或完整回复
- AI 第一次生成的代码，单独保存，不允许覆盖
- 后续所有轮次对话，至少 5 轮有效迭代
- 每轮对话应说明：提示目标、AI 回应、发现的问题、验证方式、自己的处理
- 最终报告必须说明 AI 的主要问题、自己的关键贡献、项目实现方法和最终反思

## 九、固定提交格式

请将以下目录压缩为 zip：

```text
TaskFlow_Submission/
  README.md
  final/
    taskflow.py
  ai/
    initial_prompt.md
    initial_response.md
    initial_code.py
    full_conversation.md
  report/
    report.md
```

## 十、每个提交文件的含义

`README.md`

项目说明文件。必须包含功能清单、运行方式、命令示例、已知限制。

`final/taskflow.py`

最终代码文件。它是学生经过 AI 协作、人工修改和自查后提交的版本，也是答辩系统分析与隐藏验收的主要代码证据。

`ai/initial_prompt.md`

第一次要求 AI 完成作业的原始 prompt。用于观察学生是否能表达清晰需求，还是只输入“帮我完成作业”。

`ai/initial_response.md`

AI 第一次回复的完整内容或摘要。用于判断 AI 初版方案包含哪些设计、遗漏了哪些问题。

`ai/initial_code.py`

AI 第一次生成的代码原样保存。答辩系统会要求学生比较它和最终代码，说明自己做了哪些关键修改。

`ai/full_conversation.md`

后续所有轮次对话记录。每轮需要体现提示目标、AI 回应、发现的问题、验证方式和学生处理。只粘贴 AI 输出而没有学生判断，会降低原创性评价。

`report/report.md`

学生自己写的最终报告。必须包含：

- 项目实现方法
- 核心数据结构和模块划分
- 关键功能实现说明
- 迭代记录
- AI 初版的主要问题
- 自己的关键贡献
- 系统验收准备与自查方法
- 最终反思和已知不足

## 十一、评分标准

必做总分 100，另设最多 5 分 bonus：

- 最终程序功能：25 分
- 代码质量与工程结构：15 分
- 系统验收与验证：15 分
- AI 协作过程记录：15 分
- 现场答辩理解表现：20 分
- 报告与原创性说明：10 分
- AI 共创扩展 Bonus：最多 +5 分

## 十二、答辩重点

答辩系统会围绕以下问题进行有限轮次追问：

- 学生是否理解最终代码的数据模型、关键函数和必做工程功能
- 学生是否能比较 AI 初版代码和最终代码
- 学生是否能指出 AI 初版的具体问题
- 学生是否能解释每轮提示的目标、验证方式和处理结果
- 学生是否理解系统隐藏验收如何验证 AI 代码和自己的修改
- 学生是否能说明为什么接受或拒绝 AI 建议
- 学生是否能把个人贡献对应到具体代码、验收要求、对话和报告
