# PyFixAgent

PyFixAgent is a lightweight test-driven repair agent for small local Python projects. It runs pytest, collects failure output, selects relevant source context, asks an LLM for a small code edit, applies the edit, reruns pytest, and records a structured trace of the repair attempt.

It is a prototype for demonstrating the repair loop and traceability. It is not a production-grade coding agent, sandbox, benchmark platform, or general automated software engineering system.

## Overview

The default v0.2.x workflow is intentionally small:

    run pytest
    collect failure output
    select traceback-driven context
    prompt the model through LiteLLM
    apply replacement or patch edits
    rerun pytest
    record structured trace
    iterate until tests pass or max iterations is reached

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
- Reset script for restoring demo workspaces to their committed failing baselines.

## Quick Start

Install the project in editable mode:

    python -m pip install -e .

Copy `.env.example` to `.env` and set the API key required by your model provider. The default config uses an OpenAI-compatible DashScope endpoint:

    DASHSCOPE_API_KEY=your_api_key_here

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

    pytest

Reset generated demo state and remove temporary patches/traces:

    python scripts/reset_demo.py --all --clean-outputs

Configuration priority is:

    CLI arguments > configs/default.yaml > code defaults

## Repair Modes

`replacement` is the default mode. The model returns a JSON array of small edits with `path`, `old`, `new`, and optional `start_line`. PyFixAgent validates workspace paths, rejects edits outside the workspace, rejects test-file modifications, and requires exact old-text matching. This mode is designed for reliable small-scope edits.

`patch` is optional. The model returns a unified diff patch. PyFixAgent cleans the patch text, checks it with `git apply --check -`, applies it with `git apply -`, and then reruns pytest. If patch mode repeatedly fails validation, the agent can fall back to replacement mode.

## Context Strategy

The default context strategy is `traceback`. It selects files from:

- failing test files
- traceback source files
- modules directly imported by failing tests

This is intentionally lightweight. It is not a full import graph, repository index, vector database, or RAG system. For very small workspaces, `--context-strategy full` can include all Python files instead.

## Structured Trace

Structured trace is the main v0.2.x visibility feature. Each run records enough structured data to understand what happened without reading the full pytest log:

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

Traces may contain source code, model output, pytest logs, local paths, and environment details. Do not publish traces that contain secrets or private code.

## Demo Benchmark

v0.2.2 includes a small local demo benchmark summary in `docs/benchmark.md`. It covers:

- `workspaces/demo_project`
- `workspaces/sklearn_iris_tree_project`

This is not an academic benchmark and is not comparable to SWE-bench. It is a lightweight demonstration that the local pytest-driven loop can move the included demo workspaces from failing tests to passing tests while recording explainable trace data.

## Limitations

- Not a production-grade sandbox.
- Designed for small local Python projects.
- pytest is the main validation signal.
- Context selection is lightweight.
- No full repository indexing.
- No vector database or RAG.
- No complete dependency graph.
- No GitHub PR or issue integration.
- LLM output reliability is not guaranteed.
- Traces can contain sensitive source code and logs.

See `docs/limitations.md` for the full boundary statement.

## Roadmap

Completed v0.2.x work includes the test-driven repair loop, replacement and patch modes, traceback-driven context selection, structured traces, CLI/config polish, resettable examples, and lightweight benchmark documentation.

Future work is listed in `docs/roadmap.md`. Items there are not implemented unless marked completed.

## Project Status

PyFixAgent v0.2.2 is a local prototype focused on documentation, traceability, benchmark explanation, and resume/interview presentation. The project deliberately avoids Web UI, Docker sandboxing, GitHub automation, RAG, multi-model voting, generated tests, AST editing, complex import graphs, and large-scale benchmark infrastructure.
