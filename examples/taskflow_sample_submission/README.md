# TaskFlow Pro 作业提交说明

这是一个 AI 辅助完成的命令行智能任务管理器。程序入口是 `final/taskflow.py`，数据默认保存到 `tasks.json`。

## 功能清单

- 添加、删除、完成、更新状态、查看任务
- 任务字段包含 id、标题、描述、优先级、截止日期、状态、标签、创建时间、更新时间
- 支持按状态、优先级、标签、截止日期范围组合筛选
- 支持关键词搜索标题和描述
- 支持按截止日期、优先级、创建时间排序
- 支持批量归档和批量更新状态
- 支持 JSON 导入和导出
- 支持统计不同状态数量、逾期任务、高优先级未完成任务和标签分布

## 运行示例

```bash
python final/taskflow.py add "finish report" --description "write AI collaboration report" --priority high --deadline 2026-06-10 --tags course,ai
python final/taskflow.py list --priority high --tag ai --sort-by deadline
python final/taskflow.py archive 1 2
python final/taskflow.py stats
python final/taskflow.py export backup.json
python final/taskflow.py import backup.json
```

## 测试

```bash
python -m pytest tests/test_taskflow.py
```

## 已知限制

- 当前版本只使用本地 JSON 文件，不支持多用户并发写入。
- 导入重复 id 时会重新分配 id，但没有保留完整冲突日志。
- 命令行输出为 JSON，适合自动化测试，但交互体验还可以继续优化。

## AI 使用说明

我保留了第一次 prompt、第一次 AI 回复、第一次 AI 代码和后续完整对话。AI 初版提供了基础 argparse 和 JSON 持久化框架，但缺少高级筛选、导入导出、批量操作和严谨测试。我主要修改了数据模型、校验入口、测试隔离、导入导出冲突处理和统计逻辑。

