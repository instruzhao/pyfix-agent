# PyFixAgent

PyFixAgent is a test-driven repair prototype for small local Python projects. It runs configured pytest commands, selects bounded failure-related context, requests a constrained edit from an LLM, verifies the edit with pytest, and writes a structured trace and an exported patch.

The default CLI repairs a temporary Git worktree. It does not change the selected checkout until a user reviews an exported patch and approves its SHA-256 digest. This is an engineering prototype, not a production coding service or a VM-grade sandbox.

## What v0.7.3 provides locally

- Replacement edits by default; unified-diff patch edits are optional.
- Traceback-based context with bounded static Python import/importer expansion.
- Checkpoints for partial progress and rollback after regressions or no progress.
- A separate, bounded semantic-review step after visible tests pass.
- Local or container test execution. The configured default is an ephemeral Docker container.
- JSON traces, a standalone trace viewer, benchmark reports, and matched-report comparison.
- Exported patch approval bound to the exact cleaned-patch SHA-256.

The included benchmark fixtures and release records are local, curated evidence. They are useful for repeatable comparisons, not evidence of general repair performance.

## Requirements

- Python 3.10 or later
- Git; the selected workspace needs a `HEAD` commit and must be clean unless `--allow-dirty` is supplied
- An API key for the configured model provider
- Docker or Podman plus a reviewed runner image for the default container backend

The checked-in configuration uses DashScope's OpenAI-compatible endpoint and `qwen3.7-plus`. Select another compatible provider by changing configuration; provider-specific parameters remain the operator's responsibility.

This local v0.7.3 source snapshot continues to use the separately reviewed `pyfixagent-runner:0.7.2` image. It does not claim that a v0.7.3 runner image has been built or qualified.

## Quick start

Install the project:

    python -m pip install -e .

Install optional scientific dependencies for the bundled Iris demo and full benchmark validation:

    python -m pip install -e ".[benchmark]"

Copy `.env.example` to `.env` and set the provider key expected by `configs/default.yaml`:

    DASHSCOPE_API_KEY=your_api_key_here

Build the configured scientific runner locally:

    docker build --pull=false -f containers/Dockerfile -t pyfixagent-runner:0.7.2 .

Reset a demo and run it through the default container backend:

    python scripts/reset_demo.py --all
    python -m pyfixagent.main --workspace workspaces/demo_project --mode replacement --context-strategy traceback

Container execution requires a running Docker or Podman daemon and never installs dependencies at runtime. For a trusted project that cannot use a container, choose the host-process compatibility backend explicitly:

    python -m pyfixagent.main --sandbox-backend local

## Common commands

Show available CLI options:

    python -m pyfixagent.main --help

Run the project tests without external-service integration tests:

    python -m pytest -m "not integration"

List or validate the benchmark protocol without calling a model:

    pyfixagent-benchmark --list
    pyfixagent-benchmark --validate

Run the default benchmark protocol (five repetitions per selected case):

    pyfixagent-benchmark

Run paired repository-context variants:

    pyfixagent-benchmark --tag v0.6.2 --repository-mode off --repository-mode on --repeat 4

Compare two report-schema-5 runs. It exits with status 2 for protocol drift and status 3 for unmatched trials unless the corresponding override is supplied:

    pyfixagent-benchmark-compare outputs/baseline/report.json outputs/candidate/report.json --output-dir outputs/comparison

Audit and render a trace before sharing it:

    pyfixagent-trace-viewer outputs/traces/run_xxx.json --redaction safe --fail-on-audit

Check an already-built runner image against the local reviewed-CVE allowlist. This command uses Docker Scout and therefore requires that Docker Scout is available:

    pyfixagent-verify-container --image pyfixagent-runner:0.7.2

Measure one local runner's startup and persistent write-limit behavior without making a model call:

    pyfixagent-qualify-container --image pyfixagent-runner:0.7.2 --repeat 5 --probe-limits

## Repair, outputs, and approval

Configuration priority is:

    CLI arguments > configs/default.yaml > code defaults

The CLI normally requires a clean selected workspace, creates a detached temporary worktree, and writes patches under `outputs/patches/` plus traces under `outputs/traces/`. `--in-place` is a host-only compatibility option and cannot be combined with the container backend.

To apply an exported patch, first preview it. This validates the clean workspace, edit policy, and patch, then prints a digest without changing files:

    pyfixagent-apply --workspace workspaces/demo_project --patch outputs/patches/final_xxx.patch --allowed-path src

After reviewing the patch, repeat the command with that exact digest:

    pyfixagent-apply --workspace workspaces/demo_project --patch outputs/patches/final_xxx.patch --allowed-path src --approve <SHA-256>

The application leaves changes uncommitted for normal review.

## Execution boundary

The container backend mounts only the disposable worktree and applies network, privilege, resource, output, file-size, and workspace-growth policies. It is defense in depth: containers share the host kernel, daemon configuration and bind-mount behavior remain relevant, and sampled workspace-growth monitoring can miss an immediate create/delete burst. The local backend is not a security sandbox.

The reviewed `minimal`, `scientific`, and `web` Linux/amd64 images use a digest-pinned base and hash-locked Python wheels. They are finite dependency profiles, not universal Python environments. See [runner-image instructions](containers/README.md) for profiles, derived images, and tag-publication behavior.

## Documentation

- [Design and architecture](docs/design.md)
- [Limits and operating boundaries](docs/limitations.md)
- [Trace schema guide](docs/trace.md)
- [Benchmark protocol and historical observations](docs/benchmark.md)
- [Changelog](CHANGELOG.md)
- [v0.7.2 runner qualification record](docs/results/v0.7.2-runner-qualification.md)
- [Roadmap](docs/roadmap.md)

The CI workflow tests supported Python versions, validates the benchmark protocol, and exercises Docker and Linux Podman container paths. Version-tag publication is defined in `.github/workflows/release-runner.yml`; it builds and smoke-tests each profile before publishing the corresponding GHCR image and attaching provenance/SBOM attestations.
