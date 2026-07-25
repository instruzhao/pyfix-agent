# Resume Notes

## English

- Built PyFixAgent, a test-driven repair prototype for local Python projects. It runs pytest, selects bounded failure-related context, applies constrained LLM edits, and verifies the result with pytest.
- Added a shared edit policy for replacement and patch modes: workspace-relative Python paths, optional source roots, test-file protection, and file/change budgets.
- Implemented temporary-Git-worktree repair, checkpoint/rollback handling, structured traces, digest-bound patch approval, and local/container execution options.
- Added a YAML benchmark runner with isolated fixtures and holdouts, repeated runs, paired report comparison, protocol fingerprints, and JSON/Markdown reports.

## 中文

- 实现 PyFixAgent：面向本地 Python 项目的测试驱动修复原型。它运行 pytest，选择与失败相关的有限上下文，应用受约束的 LLM 编辑，并再次运行 pytest 验证结果。
- 为 replacement 和 patch 模式提供统一编辑策略：仅允许工作区相对的 Python 路径，可选源码目录限制，禁止修改测试文件，并限制文件数和改动行数。
- 实现临时 Git worktree 修复、检查点与回滚、结构化 Trace、基于 SHA-256 的补丁确认，以及本地/容器两种执行方式。
- 实现基于 YAML 的基准运行器，包含隔离的 fixtures 与 holdouts、重复运行、成对报告比较、协议指纹和 JSON/Markdown 报告。
