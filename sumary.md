# PyFixAgent 项目总结

## 项目定位

PyFixAgent 是一个面向本地 Python 小项目的测试驱动代码修复 Agent 原型。它的核心目标是：运行目标工作区中的 pytest，读取失败信息和 Python 源码，将上下文交给大模型生成修复内容，再把修复应用到本地项目并重新运行测试验证结果。

该项目目前更适合作为教学、实验和原型验证用途，而不是生产级自动修复系统。

## 当前主要功能

### 1. 本地 pytest 驱动修复

- 支持在配置指定的 workspace 中运行 pytest。
- 会先执行一次测试，若测试已经通过则直接结束。
- 若测试失败，会把测试输出、文件树和 Python 源码交给模型生成修复。
- 支持多轮迭代修复，最大迭代次数由 `configs/default.yaml` 中的 `agent.max_iterations` 控制。
- 采用增量修复策略：前一轮修改后若测试仍失败，不自动回滚，而是在当前修改基础上继续生成下一轮修复。

### 2. 大模型接入

- 通过 LiteLLM 调用模型。
- 默认配置使用 OpenAI 兼容接口，并指向 DashScope 兼容模式端点。
- 模型名称、API 地址、API key 环境变量、temperature、max tokens 和超时时间均可通过配置文件调整。
- 项目包含 mock model，便于单元测试中模拟模型行为。

### 3. 两种模型输出模式

项目支持两类修复输出：

- `patch` 模式：模型返回标准 git unified diff。
- `replacement` 模式：模型返回 JSON 数组，每个对象包含 `path`、`old`、`new`，可选 `start_line`，由程序执行精确文本替换。

`patch` 模式会对模型输出进行清理、diff 头规范化、格式校验，并通过 `git apply --check -` 校验后再应用。

`replacement` 模式适合小范围精确修改，会限制目标文件必须是 workspace 内的 `.py` 文件，并拒绝修改 `tests/` 目录。

### 4. 补丁处理与评估能力

- 可以从模型输出中提取 patch。
- 可以清理 Markdown 代码块、JSON 包装和自然语言前缀。
- 可以规范化 git diff header。
- 可以校验 patch 是否包含必要的 `diff --git`、`---/+++` 和 hunk header。
- 可以拒绝不安全路径、创建/删除文件 patch、包含 Markdown fence 的输出等。
- `patch_eval` 包提供了独立的 patch 解析、规范化、校验和 `git apply --check` 评估流程。

### 5. 本地命令沙箱

- `LocalSandbox` 封装了子进程执行、超时控制、stdout/stderr 捕获和命令结果结构化返回。
- 命令策略会拦截明显危险的命令，例如 `rm`、`sudo`、`shutdown`、`curl`、`wget`、`powershell`、`cmd` 等。
- 当前主要允许 pytest 和 Python 命令，用于本地测试修复流程。

### 6. 文件读取与输出记录

- 可以列出 workspace 文件树。
- 可以读取 workspace 内所有 Python 文件并拼接进模型 prompt。
- 修复 patch 会保存到 `outputs/patches`。
- 每次 agent 运行会保存完整 trace JSON 到 `outputs/traces`。
- trace 中包含任务、测试输出、模型原始输出、清理后的 patch、每轮迭代记录、错误信息和最终状态。

### 7. 示例工作区与重置脚本

- 项目内置 `workspaces/demo_project` 和 `workspaces/sklearn_iris_tree_project` 示例工作区。
- `scripts/reset_demo.py` 可将 demo workspace 重置到失败基线，也可以清理生成的 patches 和 traces。

### 8. 测试覆盖

当前项目有较完整的单元测试，覆盖范围包括：

- 默认 Agent 主流程。
- patch 清理、校验、应用和 git apply 检查。
- replacement JSON 解析与应用。
- sandbox 命令策略。
- prompt 内容。
- trace 保存。
- patch_eval 的 parser、normalizer、validator 和 runner。
- 文件工具与示例 sklearn iris 项目。

当前本地测试结果为：`64 passed, 1 skipped`。

## 当前不足与风险

### 1. 仍是原型系统，不具备生产级安全隔离

当前 sandbox 只是命令白名单/黑名单加 subprocess 超时，不提供容器隔离、文件系统隔离、网络隔离、CPU 限制或内存限制。它可以降低误操作风险，但不能防御恶意代码或不可信项目。

### 2. 文档与代码存在默认模式不一致

README 描述默认从 `patch` 模式开始，并在 patch 校验连续失败后切换到 `replacement` 模式；但当前 `DefaultAgent` 构造函数的默认 `initial_mode` 是 `replacement`，`main.py` 也没有从配置中传入该参数。这会导致实际默认行为和文档说明不一致。

### 3. 任务和路径策略仍偏示例化

默认配置中的任务强绑定到 `workspaces/sklearn_iris_tree_project` 和 `ml_iris_tree/`，prompt 示例中也出现了具体路径。这有利于 demo，但会降低泛化到任意 Python 项目的能力。

### 4. 只能处理较小规模 Python 项目

当前会读取 workspace 中所有 Python 文件并整体放进 prompt。对于文件较多、源码较大的项目，容易遇到上下文过长、成本较高、模型注意力分散等问题。项目还没有实现文件检索、相关性筛选、分块读取或增量上下文管理。

### 5. 修复范围有限

- replacement 模式只允许修改 `.py` 文件，且禁止修改 `tests/`。
- patch 校验不支持创建或删除文件。
- 当前流程主要面向 pytest 失败修复，不适合复杂重构、跨语言项目、依赖升级、配置变更或需要人工设计判断的大型任务。

### 6. 缺少自动回滚和分支隔离

Agent 采用增量修复策略，patch 应用后若测试仍失败，不会自动回滚到上一轮状态。该策略便于连续修复，但也可能让工作区逐步积累错误修改。当前也没有自动创建临时 Git 分支或隔离工作副本。

### 7. 缺少 Web UI、服务化和外部系统集成

项目目前是命令行原型，没有 Web UI、API 服务、任务队列、多用户能力、GitHub Issue/PR 集成、CI 集成或可视化 trace 页面。

### 8. 大模型调用可靠性仍依赖提示词和供应商

虽然项目对模型输出做了清理、校验和失败反馈，但模型仍可能返回格式错误、语义错误或过度修改的结果。当前没有多模型投票、候选 patch 排序、静态分析、覆盖率分析或更强的修复验证策略。

### 9. trace 可能包含敏感信息

trace JSON 会记录 prompt、源码、模型输出和 pytest 日志。如果目标项目包含敏感代码或密钥，trace 文件可能泄露信息，不适合直接提交到公开仓库。

### 10. 评估体系还不完整

`patch_eval` 已经具备 patch 格式评估能力，但项目尚未形成完整 benchmark、成功率统计、失败类型分析、耗时/成本指标、模型对比实验或长期回归评估系统。

## 后续改进方向

- 统一 README、配置和代码中的默认修复模式。
- 将 workspace、允许修改路径、初始模式等能力配置化。
- 引入 Git 分支或临时副本隔离，每轮失败后可选择回滚。
- 增加基于失败测试和 import 图的相关文件筛选，减少 prompt 体积。
- 强化 sandbox，至少支持容器化执行和资源限制。
- 扩展 patch 支持能力，例如新增文件、删除文件和非 Python 配置文件修改。
- 为 trace 增加脱敏选项和更友好的查看工具。
- 建立更系统的 benchmark 和修复成功率评估。
- 增加 CLI 参数，允许用户指定 workspace、任务、模型和迭代次数。
- 增加 CI 配置，持续运行单元测试和示例修复流程。
