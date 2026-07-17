# PyFixAgent

PyFixAgent is a test-driven repair agent for local Python projects. It runs pytest, collects failure output, selects relevant source context, asks an LLM for a constrained code edit, applies the edit, reruns pytest, and records a structured trace of the repair attempt.

It is a prototype for demonstrating the repair loop and traceability. It is not a production-grade coding agent, sandbox, benchmark platform, or general automated software engineering system.

## Overview

The default v0.6.2 workflow is transactional, repository-aware, review-gated, and cost-observable:

    create a temporary Git worktree
    run the configured pytest command
    collect failure output
    select traceback-driven context
    expand direct static dependencies under a token budget
    prompt the model through LiteLLM
    apply replacement or patch edits
    rerun pytest
    record structured trace
    checkpoint progress or roll back regressions
    review visible-pass candidates for semantic risks
    perform bounded evidence-driven revisions
    export a candidate/final patch and remove the worktree

The repository includes two resettable demo workspaces:

- `workspaces/demo_project`
- `workspaces/sklearn_iris_tree_project`

## What PyFixAgent Does

- Runs pytest inside a configured local workspace.
- Parses pytest failures and traceback output.
- Selects relevant Python files using the default `traceback` context strategy.
- Calls a LiteLLM-backed model.
- Applies either JSON replacement edits or unified diff patches.
- Verifies each edit by rerunning pytest.
- Stores generated patches under `outputs/patches`.
- Stores structured traces under `outputs/traces`.

## Features

- Test-driven repair loop for local Python projects.
- Default `replacement` mode for small exact old/new edits.
- Optional `patch` mode for unified diff style repairs.
- Default `traceback` context strategy.
- Fallback `full` context strategy for small workspaces.
- Structured trace fields for test summaries, failure deltas, model output, apply results, edit summaries, model call metadata, environment, and final summary.
- CLI overrides for workspace, mode, context strategy, task, config path, and max iterations.
- Clean Git workspace checks and a shared edit policy for patch/replacement modes.
- Repeatable YAML-driven benchmarks with JSON and Markdown reports.
- Reset script for restoring demo workspaces to their committed failing baselines.
- Component-based internals with separate repair orchestration, test execution, context, prompting, model, edit backend, retry, trace evaluation, and benchmark responsibilities.
- Temporary Git worktree execution for the default CLI workflow, leaving the selected repository unchanged.
- Per-iteration checkpoints with automatic rollback when an edit introduces new test failures.
- Configurable argv-only pytest commands protected by an explicit command policy.
- Failure-delta retry decisions that distinguish partial progress, no progress, regressions, and timeouts.
- Bounded context expansion after rolled-back semantic failures.
- Independent semantic review with strict JSON, evidence validation, deterministic structural risk cues, and bounded revisions.
- Execution-free Python repository indexing with content-addressed cache invalidation.
- Bounded import/importer graph expansion and symbol-range context selection.
- Paired repository-context A/B benchmarks with context recall and distractor metrics.
- Separate repair/review token and latency accounting with a bounded reviewer model.
- Configurable path or source-content trace redaction.

## Quick Start

Install the project in editable mode:

    python -m pip install -e .

Install the optional scientific dependencies when running the complete benchmark protocol or the sklearn Iris demo:

    python -m pip install -e ".[benchmark]"

Copy `.env.example` to `.env` and set the API key required by your model provider. The default config uses an OpenAI-compatible DashScope endpoint:

    DASHSCOPE_API_KEY=your_api_key_here

The default configured model is `qwen3.6-max-preview`.

Then reset the examples and run the default configured workspace:

    python scripts/reset_demo.py --all
    python -m pyfixagent.main

## Example Commands

Show CLI options:

    python -m pyfixagent.main --help

Run the billing demo:

    python scripts/reset_demo.py --all
    python -m pyfixagent.main --workspace workspaces/demo_project --mode replacement --context-strategy traceback

Run the sklearn iris demo:

    python scripts/reset_demo.py --all
    python -m pyfixagent.main --workspace workspaces/sklearn_iris_tree_project --mode replacement --context-strategy traceback

Run the project unit tests:

    pytest -m "not integration"

List benchmark cases without calling a model:

    pyfixagent-benchmark --list

Validate all benchmark fixtures and holdouts without calling a model:

    pyfixagent-benchmark --validate

Run each configured benchmark case five times (the CLI default):

    pyfixagent-benchmark

Run the v0.6.2 multi-module cases as paired repository-context A/B trials:

    pyfixagent-benchmark --tag v0.6.2 --repository-mode off --repository-mode on --repeat 4

Benchmark results are written under `outputs/benchmarks/`. Each run copies a read-only fixture into a disposable repository, performs repair in an inner temporary Git worktree, exports the aggregate patch, and removes the repair worktree afterward. The materialized benchmark workspace is also removed unless `--keep-workspaces` is explicitly supplied.

PyFixAgent includes a GitHub Actions workflow that runs the supported Python test matrix on pushes to `main` and pull requests targeting `main`. Benchmark protocol validation runs once in a separate job with the optional benchmark dependencies installed.

Reset generated demo state and remove temporary patches/traces:

    python scripts/reset_demo.py --all --clean-outputs

Configuration priority is:

    CLI arguments > configs/default.yaml > code defaults

By default, the CLI refuses to run when the selected workspace contains uncommitted changes. Use `--allow-dirty` only when mixing an agent run with existing changes is intentional. Use one or more `--allowed-path` arguments to enforce source-root boundaries.

The CLI repairs a detached temporary Git worktree and exports the final patch under `outputs/patches/`; it does not modify the selected workspace. `--in-place` is an explicit compatibility escape hatch for trusted workflows that require the previous behavior.

Test commands are configured as argv lists rather than shell strings:

    test:
      commands:
        - [python, -m, pytest, -p, no:cacheprovider]

Only direct `pytest` or `python -m pytest` commands are accepted.

## Repair Modes

`replacement` is the default mode. The model returns a JSON array of small edits with `path`, `old`, `new`, and optional `start_line`. PyFixAgent validates workspace paths, rejects edits outside the workspace, rejects test-file modifications, and requires exact old-text matching. This mode is designed for reliable small-scope edits.

`patch` is optional. The model returns a unified diff patch. PyFixAgent cleans the patch text, checks it with `git apply --check -`, applies it with `git apply -`, and then reruns pytest. If patch mode repeatedly fails validation, the agent can fall back to replacement mode.

## Context Strategy

The default context strategy is `traceback`. It seeds context from:

- failing test files
- traceback source files
- modules directly imported by failing tests

v0.6.1 then uses a static AST index to follow direct imports and reverse importers up to the configured depth. Related symbols are preferred when their names are referenced by the seed evidence, and selected source is clipped to `context.max_selected_tokens`. The index is content-addressed, cached outside the repair workspace, and rebuilt after a source edit changes its fingerprint.

This remains intentionally bounded: it does not execute imports, resolve dynamic dispatch, index non-Python languages, use embeddings, or provide RAG. For very small workspaces, `--context-strategy full` can include all Python files while still honoring the configured source-context budget.

## Structured Trace

Structured trace is the main repair visibility feature. Each run records enough structured data to understand what happened without reading the full pytest log:

- `test_summary_before` and `test_summary_after`
- `failure_delta`
- `iteration_result`
- `context`
- `model_output`
- `apply`
- `generated_diff`
- `edit_summary`
- `model_call`
- `environment`
- `final_summary`

See `docs/trace.md` for the field guide.

The default `trace.redaction_mode: paths` replaces known local workspace, project, and home roots. Use `--trace-redaction safe` to hash source-bearing prompts, diffs, model output, tasks, and pytest logs while retaining structured metrics. Redaction is a publication aid, not a general secret scanner; review traces before sharing them.

You can summarize a structured trace JSON with:

    python scripts/summarize_trace.py outputs/traces/run_xxx.json

The summary reports final status, iteration count, failure deltas, selected context size, modified files, and model metadata.

## Demo Benchmark

v0.2.2 includes a small benchmark comparing traceback-driven context selection with full-workspace context on resettable demo workspaces. The benchmark tracks prompt size, selected files, iterations, failure deltas, modified files, and final test status.

It covers:

- `workspaces/demo_project`
- `workspaces/sklearn_iris_tree_project`

See `docs/benchmark.md` for detailed results. This benchmark compares context strategy behavior; it is not an academic benchmark, not comparable to SWE-bench, and not a claim of production-grade repair ability.

The benchmark runner generates tasks from allowed paths and cannot accept case-specific hints. Agent-visible tests live inside each fixture; holdout tests live outside the fixture and run only after the repair loop. v0.6.2 manifest schema 3 adds evaluation-only context ground truth and tags; report schema 4 adds paired repository A/B, retrieval quality, cache/index timing, and separate repair/review cost.

See `docs/results/v0.3.1-qwen3.6-flash.md` for a sanitized one-run report across all 15 cases.

The v0.4.0 release qualification repeated all 15 cases four times. It reached 100% visible-test success and 91.7% external-holdout success across 60 runs. See `docs/results/v0.4.0-qwen3.6-flash-repeat4.md` for the sanitized report and failure analysis.

v0.4.1 is a maintenance release that declares the optional scientific benchmark dependencies and separates benchmark validation from the multi-version unit-test matrix. It does not change repair behavior or invalidate the v0.4.0 real-model qualification result. See `docs/v0.4.1.md` for the release notes.

v0.5.0 moves the default CLI repair into a temporary Git worktree, adds checkpoints and regression rollback, exports a reviewable final patch, and introduces policy-checked configurable pytest commands. See `docs/v0.5.0.md` for the release notes.

v0.5.1 moves semantic retry decisions into `RetryPolicy`: partial progress is checkpointed, while no-progress attempts and regressions are rolled back before retrying with bounded expanded context. Its `qwen3.6-max-preview` release qualification reached 100% visible-test success and 86.7% external-holdout success across 60 runs. See `docs/v0.5.1.md` for the release notes and `docs/results/v0.5.1-qwen3.6-max-preview-repeat4.md` for the sanitized report.

v0.6.0 separates visible-test success from final semantic acceptance. An independent reviewer can accept a candidate, request a bounded evidence-driven revision, or return `needs_review`; external holdouts remain inaccessible to the agent. Its one-run `qwen3.6-max-preview` qualification passed all 15 visible suites and all 15 external holdouts with zero false accepts or false rejects. See `docs/v0.6.0.md` for the release notes and `docs/results/v0.6.0-qwen3.6-max-preview.md` for the sanitized report.

v0.6.1 adds an execution-free Python repository index, direct import/importer expansion, symbol-range selection, content-addressed cache invalidation, and deterministic token budgeting shared by repair and review context. Its one-run `qwen3.6-max-preview` qualification again passed all 15 visible suites and external holdouts. See `docs/v0.6.1.md` for the release notes and `docs/results/v0.6.1-qwen3.6-max-preview.md` for the sanitized report.

v0.6.2 expands the benchmark to 24 cases, adds nine multi-module context-ground-truth fixtures, paired repository-on/off runs, separate repair/review costs, bounded reviewer generation, documented-contract checks, and trace privacy modes. Its final-code qualification completed 19/19 full successes, including all nine new cases; five additional existing cases remain explicitly incomplete after provider quota exhaustion. See `docs/v0.6.2.md` for the release notes and `docs/results/v0.6.2-qwen3.6-max-preview.md` for the sanitized evidence.

## Limitations

- Not a production-grade sandbox.
- Designed for small local Python projects.
- pytest is the main validation signal.
- Repository understanding is static, Python-only, and bounded.
- No vector database or RAG.
- No dynamic call graph or cross-language dependency graph.
- No GitHub PR or issue integration.
- LLM output reliability is not guaranteed.
- Path-only traces can still contain sensitive source code; safe mode is not a complete secret scanner.

See `docs/limitations.md` for the full boundary statement.

## Roadmap

Completed v0.2.x work includes the test-driven repair loop, replacement and patch modes, traceback-driven context selection, structured traces, CLI/config polish, resettable examples, and lightweight benchmark documentation.

Future work is listed in `docs/roadmap.md`. Items there are not implemented unless marked completed.

## Project Status

PyFixAgent v0.6.2 is a transactional local repair baseline with constrained edits, temporary-worktree execution, semantic rollback/retry, bounded static repository context, independently budgeted candidate review, paired context evaluation, holdout validation, cost accounting, and configurable trace privacy. It remains intended for trusted Python projects: a Git worktree protects the selected checkout from repair mutations but is not a security sandbox, and container isolation is the next major boundary.
