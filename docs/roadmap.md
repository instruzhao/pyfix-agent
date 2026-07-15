# Roadmap

## Completed through v0.3.1

- pytest-driven iterative repair loop
- replacement and unified-diff patch modes
- traceback-driven and full context strategies
- structured traces, CLI/config support, resettable examples, and CI
- clean Git workspace guard and shared edit policy
- isolated schema v2 benchmark fixtures with external holdouts
- 15 hint-free curated cases, Success@1, Pass@k, regressions, failures, and token metrics

## v0.4.0 Role-oriented Internals — Completed

- stable core contracts for repair requests, context, proposals, apply results, outcomes, and retry decisions
- `RepairEngine` as the deterministic workflow coordinator
- independent test execution, workspace session, context, prompt, model, evaluator, and retry components
- independent patch and replacement backends behind the same protocol
- modular benchmark manifest, workspace, holdout, runner, metrics, report, and CLI responsibilities
- compatibility facades for `DefaultAgent` and `pyfixagent.benchmark`
- component-level architecture tests in addition to end-to-end compatibility tests
- four-repetition real-model benchmark report for release qualification

## Next: v0.5 Reliability and Isolation

- per-iteration Git checkpoints and automatic rollback on regression
- temporary Git worktree execution instead of in-place clean-workspace execution
- configurable test commands with an explicit command policy
- semantic retry strategies driven by failure deltas rather than only format/apply failures
- token-based context budgeting and symbol-level dependency expansion
- trace redaction and a static trace viewer

## Deferred

- untrusted-code execution without container isolation
- Web UI
- GitHub pull-request automation
- vector database/RAG
- generated tests
- multi-agent or multi-model voting
