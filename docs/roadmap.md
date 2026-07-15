# Roadmap

## Completed through v0.2.3

- pytest-driven iterative repair loop
- replacement and unified-diff patch modes
- traceback-driven and full context strategies
- structured traces, CLI/config support, resettable examples, CI, and initial benchmark documentation

## v0.2.4 Engineering Baseline — Completed in v0.3.0

- unified package version and installable `pyfixagent` command
- meaningful process exit status
- generic prompts without demo-specific file bias
- CI matrix for supported Python versions
- corrected documentation and Chinese resume encoding
- trace schema version and pre-run workspace metadata

## v0.3.0 Repeatable and Guarded Baseline — Completed

- `pyfixagent-benchmark` command
- versioned YAML benchmark case manifest
- reset-before/reset-after execution
- repeated runs with Success@1 and Pass@k
- JSON/Markdown reports and per-run structured traces
- provider token metrics when available
- clean Git workspace guard enabled by default in the CLI
- shared tool-level edit policy for patch and replacement modes
- allowed paths, forbidden test paths, file count, and changed-line budgets

## v0.3.1 Credible Benchmark Baseline — Completed

- schema v2 manifests with generated generic tasks and no case-specific task hints
- physically separated visible and holdout tests
- final success gated on external holdout validation
- fresh temporary Git repository for every case/strategy/repetition
- five repetitions by default
- 15 curated cases across varied bug categories
- visible, holdout, Success@1, Pass@k, regression, no-progress, failure, policy, and token metrics
- `pyfixagent-benchmark --validate` for no-model protocol validation

## Next: v0.4

- temporary Git worktree execution instead of in-place clean-workspace execution
- per-iteration checkpoints and automatic rollback on regression
- configurable test commands with an explicit command policy
- token-based context budgeting and symbol-level dependency expansion
- a larger curated benchmark suite with multiple bug categories
- trace redaction and a static trace viewer

## Deferred

- untrusted-code execution without container isolation
- Web UI
- GitHub pull-request automation
- vector database/RAG
- generated tests
- multi-agent or multi-model voting
