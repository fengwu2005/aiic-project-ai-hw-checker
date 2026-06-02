# TaskFlow Pro 学生报告

## 一、项目实现方法

我实现的 TaskFlow Pro 是一个基于 Python 标准库的命令行任务管理器。核心思路是将任务保存为 JSON 数组，每个任务使用字典表示。命令行层由 `argparse` 负责，业务逻辑拆分为可测试函数，例如 `add_task`、`list_tasks`、`batch_update_status`、`import_tasks` 和 `task_statistics`。

任务字段包括 `id`、`title`、`description`、`priority`、`deadline`、`status`、`tags`、`created_at`、`updated_at`。其中 tags 会统一转成小写列表，deadline 通过 `datetime.strptime` 校验，priority 和 status 使用固定集合校验。

## 二、关键功能说明

组合筛选由 `list_tasks` 实现，它支持状态、优先级、标签、截止日期范围和关键词搜索。排序逻辑拆分到 `sort_tasks`，支持按 deadline、priority 和 created_at 排序。批量操作由 `batch_update_status` 实现，`archive_tasks` 只是把状态批量改成 archived。

导入导出是我重点修改的部分。导出时直接把当前任务列表写入目标 JSON。导入时会先校验 JSON 必须是列表，再逐个调用 `normalize_task` 校验字段。如果导入任务 id 和已有任务冲突，我没有选择跳过，而是重新分配新 id，避免静默丢数据。

统计功能由 `task_statistics` 实现，返回总任务数、不同状态数量、逾期任务数、高优先级未完成数量和标签分布。函数返回字典而不是直接打印，方便测试断言。

## 三、迭代记录

第一次 AI 生成的代码只实现了 add、list、complete、delete，状态只有 pending/completed，标签只是字符串，缺少 description、created_at、updated_at，也没有高级功能。

第一轮迭代中，我主要修复数据校验问题。AI 建议校验日期和优先级，但没有指出损坏 JSON 被吞掉的问题。我改成 JSON 损坏时抛出 ValueError。

第二轮迭代中，我设计高级接口。AI 提出了组合筛选和统计，但遗漏截止日期范围和导入重复 id。我自己加入 deadline_from、deadline_to 和导入冲突处理。

第三轮迭代中，我补充测试。AI 给出的测试共享默认文件，我认为会导致测试污染，所以给核心函数加了 `path` 参数，在测试中使用 `tmp_path`。

第四轮迭代中，我处理导入策略。AI 建议对坏数据宽松处理，但我认为作业需要可解释性，所以字段缺失和非法日期应该明确报错，重复 id 才自动修正。

第五轮迭代中，我重构命令行层和业务逻辑。业务函数只返回数据，CLI 层统一输出 JSON，这样既适合命令行，也适合测试。

## 四、AI 的主要问题

AI 初版最大的问题是“看起来完整但实际很浅”。它能快速写出 argparse 和 JSON 持久化框架，但容易遗漏需求细节，例如组合筛选、排序、导入导出冲突、批量操作和统计。

AI 第二个问题是边界处理过于宽松。它倾向于用 `except Exception` 隐藏错误，或者在导入坏数据时跳过。这会让程序演示时少报错，但真实数据会变得不可靠。

AI 第三个问题是测试质量不稳定。它会生成数量看似足够的测试，但很多测试共享默认数据文件，存在顺序依赖和环境污染。

## 五、我的关键贡献

我的关键贡献主要有五点：

- 重新设计任务数据模型，加入 description、tags、created_at、updated_at 和 archived 状态。
- 设计统一校验入口，包括 priority、status、deadline 和导入任务字段校验。
- 实现组合筛选、关键词搜索、排序、批量归档、导入导出和统计。
- 给核心函数增加 `path` 参数，使用 `tmp_path` 写出可隔离测试。
- 对 AI 建议进行取舍，没有采用“吞掉所有异常”和“坏数据直接跳过”的宽松策略。

## 六、测试与验证方法

我编写了 15 个 pytest 测试，覆盖添加、持久化、完成、删除、组合筛选、日期范围、关键词搜索、排序、批量归档、批量缺失 id、导入导出重复 id、非法 JSON、统计、非法优先级和非法日期。

这些测试主要用于验证 AI 初版容易遗漏的问题：边界输入、文件隔离、高级功能组合和数据导入风险。

## 七、最终反思

我认为这个项目中 AI 适合生成初始框架和提出接口建议，但最终质量依赖学生自己验证和判断。直接复制 AI 初版代码会得到一个功能很浅、边界不可靠的程序。我的主要收获是：使用 AI 编程时，最重要的不是让 AI 多写代码，而是把需求拆清楚、把风险测出来、把设计取舍说清楚。

