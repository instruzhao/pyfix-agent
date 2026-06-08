# PyFixAgent

PyFixAgent is a small, beginner-friendly Coding Agent for test-driven repair in local Python projects. It is a prototype, not a production-grade Coding Agent.

Current capabilities:

- run pytest in a configured local workspace
- read the workspace file tree
- select traceback-driven Python context snippets, or fall back to full Python source context
- call a LiteLLM-backed model
- ask the model for either JSON old/new replacements or a unified diff patch
- save patches under `outputs/patches`
- check unified diff patches with `git apply --check -`
- apply valid unified diff patches with `git apply -`
- apply JSON replacements with exact string matching
- rerun pytest after each applied repair
- retry with model feedback for a limited number of iterations
- save full run traces under `outputs/traces`, including context selection metadata
- provide a small `patch_eval` package for patch parsing, normalization, validation, and `git apply --check` evaluation

The project intentionally has no Web UI, Docker support, multi-agent workflow, vector database, GitHub issue integration, or full benchmark/evaluation suite.

## Install

```bash
python -m pip install -e .
```

## Configure Model Access

Copy `.env.example` to `.env` and set the API key required by your model provider. The default config uses an OpenAI-compatible DashScope endpoint:

```bash
DASHSCOPE_API_KEY=your_api_key_here
```

Model settings, timeouts, context strategy, and `agent.max_iterations` are configured in `configs/default.yaml`.
The default workspace and task are also configured there.

## Run The Agent

```bash
python -u -m pyfixagent.main
```

v0.2.1 adds a small argparse-based CLI so common run settings can be overridden without editing `configs/default.yaml`:

```bash
python -m pyfixagent.main --help
python -m pyfixagent.main --workspace workspaces/demo_project
python -m pyfixagent.main --mode replacement
python -m pyfixagent.main --mode patch
python -m pyfixagent.main --context-strategy traceback
python -m pyfixagent.main --context-strategy full
python -m pyfixagent.main --max-iterations 3
python -m pyfixagent.main --config configs/default.yaml
```

Configuration priority is:

```text
CLI arguments > configs/default.yaml > code defaults
```

The command scans the workspace configured in `configs/default.yaml`. In the current default config this is:

```text
workspaces/sklearn_iris_tree_project
```

It runs pytest, sends the pytest output and selected Python context to the model, applies the requested repair, reruns pytest, and writes a trace JSON such as:

```text
outputs/traces/run_20260607_195745.json
```

By default, PyFixAgent parses pytest failures and selects a small window around relevant traceback files instead of sending every Python file. The default context settings are:

```yaml
context:
  strategy: traceback
  line_window: 40
  max_files: 6
  fallback_to_full_context: true
  include_tests: true
```

Set `context.strategy: full` to use the older behavior that includes all `*.py` files in the configured workspace. Test files may be read as context so the model can understand expected behavior, but replacement mode still rejects modifications under `tests/`. The traceback strategy may also include modules directly imported by a failing test as `direct_test_import`; this is a lightweight context expansion, not a full import graph or dependency analysis.

Trace JSON records structured diagnostics for each iteration:

```json
{
  "test_summary_before": {
    "total": 6,
    "passed": 3,
    "failed": 3,
    "skipped": 0,
    "failed_tests": ["tests/test_data.py::test_load_data"]
  },
  "failure_delta": {
    "fixed": [],
    "remaining": ["tests/test_data.py::test_load_data"],
    "new": []
  },
  "iteration_result": {
    "status": "test_failed_after_apply",
    "failure_type": "incomplete_fix",
    "reason": "Repair was applied successfully, but pytest still failed."
  },
  "model_output": {
    "mode": "replacement",
    "parsed_success": true
  },
  "apply": {
    "method": "replacement",
    "success": true,
    "generated_diff": "diff --git ..."
  },
  "context": {
    "strategy": "traceback",
    "dependency_analysis": false,
    "stats": {
      "selected_file_count": 2,
      "selected_snippet_count": 2,
      "selected_context_chars": 5120,
      "pytest_output_chars": 7250,
      "prompt_chars": 21438
    },
    "selected_files": [
      {
        "path": "tests/test_data.py",
        "reason": "failing_test_file",
        "selection_rule": "failing_test_file",
        "dependency_analysis": false,
        "line_range": [1, 45]
      }
    ]
  }
}
```

## Reset Example Workspaces

The example workspaces are committed as ordinary directories and are intentionally kept as failing baselines for Agent repair tests. To restore them:

```bash
python scripts/reset_demo.py --workspace demo
python scripts/reset_demo.py --workspace sklearn
python scripts/reset_demo.py --all
```

To also remove generated patches and traces:

```bash
python scripts/reset_demo.py --all --clean-outputs
```

A typical local demo run is:

```bash
python scripts/reset_demo.py --all
python -m pyfixagent.main --workspace workspaces/demo_project --mode replacement --context-strategy traceback
```

## Repair Strategy

PyFixAgent uses an incremental repair strategy. If a repair applies successfully but pytest still fails, the Agent does not roll back the workspace. It keeps the current modification, feeds the new pytest failure back to the model, and asks for an incremental repair. This is recorded in traces as:

```json
"workspace_strategy": "incremental_repair"
```

### Patch And Replacement Fallback

PyFixAgent has two model output modes:

- `patch` mode: the model outputs a unified diff patch.
- `replacement` mode: the model outputs JSON old/new replacement objects.

The current `DefaultAgent` constructor defaults to `replacement` mode:

```python
initial_mode: str = "replacement"
```

`pyfixagent.main` reads `agent.initial_mode` from `configs/default.yaml`, and `--mode replacement` or `--mode patch` can override it for a single run. If an agent starts with `initial_mode="patch"`, then patch mode is used first; after two consecutive patch check failures, the agent switches to `replacement` mode for the rest of that run.

The replacement strategy is more stable for small, exact edits because the program performs precise string replacement instead of trusting model-written hunk line numbers. It is only intended for narrow changes. Replacement mode rejects edits under `tests/`, rejects absolute paths or paths that escape the workspace, rejects non-`.py` files, and requires each `old` text fragment to match exactly once unless `start_line` disambiguates repeated matches.

In trace JSON, `raw_model_output` always means the raw model response. When `mode` or `model_output_type` is `patch`, it should be a unified diff. When `mode` or `model_output_type` is `replacement`, it should be a JSON array. Replacement traces also include `replacement_raw_output`, `replacement_edits`, `replacement_success`, and `replacement_error`. New v0.2.0 traces prefer the structured `model_output`, `apply`, and `generated_diff` fields so replacement-mode workspace diffs are not confused with model-generated patches. Top-level traces also include `environment` and `final_summary` for quick reading.

Debug traces may contain source code, model output, and pytest logs. Do not commit them to a public repository. This is still not a production-grade security sandbox.

## Sandbox Limits

The local sandbox is not a production security sandbox. It is a small command runner with a command policy and subprocess timeout. It can block obvious dangerous commands, but it does not provide container isolation, filesystem isolation, network isolation, CPU limits, or memory limits.

Use it only for local demo projects and trusted code.
