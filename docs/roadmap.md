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

## v0.4.1 CI and Benchmark Packaging — Completed

- optional `benchmark` dependencies for the sklearn Iris fixture
- benchmark protocol validation separated from the supported Python test matrix
- workflow triggers limited to `main` pushes and pull requests targeting `main`
- duplicate in-progress workflow runs cancelled per branch
- package, CLI, and release documentation aligned on version 0.4.1

## v0.5.0 Transactional Workspaces — Completed

- temporary Git worktree execution for the default CLI and benchmark paths
- per-iteration Git checkpoints and automatic rollback on regression
- final patch export without modifying the selected checkout
- configurable argv-only pytest commands with an explicit command policy
- trace schema 1.1 workspace actions and exported patch metadata

## v0.5.1 Semantic Retry — Completed

- semantic retry strategies driven by failure deltas rather than only format/apply failures
- rollback and context expansion after no-progress attempts
- retry reasons recorded independently from edit application
- partial progress checkpointed for incremental repair
- bounded traceback expansion followed by full context at the configured maximum level
- `qwen3.6-max-preview` real-model qualification across 15 cases and four repetitions

## v0.6.0 Semantic Acceptance — Completed

- a holdout-blind semantic acceptance stage after visible tests pass, separate from edit/apply retry
- code-derived contract risks and counterexample categories instead of case-specific prompt hints
- strict reviewer JSON, evidence validation, fail-closed `needs_review`, and bounded revisions
- benchmark report schema 3 with false-accept and false-reject metrics

## v0.6.1 Repository Understanding — Completed

- token-based context budgeting and symbol-level dependency expansion
- static import and caller relationships without a vector database
- content-addressed index caching with edit-driven invalidation
- repository metadata in trace schema 1.3

## v0.6.2 Scale Validation and Cost Boundaries — Completed

- benchmark manifest schema 3 with tags, context ground truth, and distractors
- nine new hint-free multi-module cases, for 24 total
- paired repository-context A/B variants and benchmark report schema 4
- separate repair/review token and latency metrics plus repository cache/index metrics
- independently bounded reviewer model and compact review contracts
- deterministic enforcement check for explicit positive-input docstring contracts
- configurable path and safe source-content trace redaction in trace schema 1.4

## Next: v0.7.0 Execution Isolation

- container-backed sandbox implementation behind the existing execution boundary
- filesystem, network, process, CPU, memory, and timeout policies
- explicit dependency installation policy and reproducible environment capture
- human approval before applying exported patches to a selected checkout
- trace redaction audit and a static trace viewer

## Deferred

- untrusted-code execution without container isolation
- Web UI
- GitHub pull-request automation
- vector database/RAG
- generated tests
- multi-agent or multi-model voting
