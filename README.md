# PyFixAgent

PyFixAgent is a small, beginner-friendly Coding Agent for test-driven repair in local Python projects. It is a prototype, not a production-grade Coding Agent.

Current capabilities:

- run pytest in a configured local workspace
- read the workspace file tree and all Python source files
- call a LiteLLM-backed model
- ask the model for either JSON old/new replacements or a unified diff patch
- save patches under `outputs/patches`
- check unified diff patches with `git apply --check -`
- apply valid unified diff patches with `git apply -`
- apply JSON replacements with exact string matching
- rerun pytest after each applied repair
- retry with model feedback for a limited number of iterations
- save full run traces under `outputs/traces`
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

Model settings, timeouts, and `agent.max_iterations` are configured in `configs/default.yaml`.
The default workspace and task are also configured there.

## Run The Agent

```bash
python -u -m pyfixagent.main
```

The command scans the workspace configured in `configs/default.yaml`. In the current default config this is:

```text
workspaces/sklearn_iris_tree_project
```

It runs pytest, sends the pytest output and Python source files to the model, applies the requested repair, reruns pytest, and writes a trace JSON such as:

```text
outputs/traces/run_20260607_195745.json
```

The current implementation reads all `*.py` files in the configured workspace and includes them in the model prompt. It does not yet select only the traceback line, enclosing function, enclosing class, or a smaller retrieved context window.

## Reset The Demo

The demo workspace is a git repository. To restore it to the committed failing baseline:

```bash
python scripts/reset_demo.py
```

To also remove generated patches and traces:

```bash
python scripts/reset_demo.py --clean-outputs
```

The reset script is guarded so it only resets `workspaces/demo_project`.

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

`pyfixagent.main` does not currently expose `initial_mode` through `configs/default.yaml`, so the default command-line run starts in `replacement` mode. If an agent is constructed with `initial_mode="patch"`, then patch mode is used first; after two consecutive patch check failures, the agent switches to `replacement` mode for the rest of that run.

The replacement strategy is more stable for small, exact edits because the program performs precise string replacement instead of trusting model-written hunk line numbers. It is only intended for narrow changes. Replacement mode rejects edits under `tests/`, rejects absolute paths or paths that escape the workspace, rejects non-`.py` files, and requires each `old` text fragment to match exactly once unless `start_line` disambiguates repeated matches.

In trace JSON, `raw_model_output` always means the raw model response. When `mode` or `model_output_type` is `patch`, it should be a unified diff. When `mode` or `model_output_type` is `replacement`, it should be a JSON array. Replacement traces also include `replacement_raw_output`, `replacement_edits`, `replacement_success`, and `replacement_error`.

Debug traces may contain source code, model output, and pytest logs. Do not commit them to a public repository. This is still not a production-grade security sandbox.

## Sandbox Limits

The local sandbox is not a production security sandbox. It is a small command runner with a command policy and subprocess timeout. It can block obvious dangerous commands, but it does not provide container isolation, filesystem isolation, network isolation, CPU limits, or memory limits.

Use it only for local demo projects and trusted code.
