# Changelog

This file is the concise change index. Detailed historical release records and qualification evidence remain under `docs/`.

## 0.7.3 — local working version

This local version has not published a package or runner image.

- Split repair, benchmark, container, configuration, and metric orchestration into focused units with AST architecture checks that guard their entrypoints.
- Replaced the default configured model with `qwen3.7-plus` on the existing DashScope OpenAI-compatible endpoint.
- Added rootless Podman bind-mount UID preservation with `--userns keep-id` for `workspace_owner`.
- Replaced silent broad exception handling with specific error boundaries or stack-bearing logs; CLI report and approval output remains stdout by design.
- Added runner-profile validation for Dockerfile CPython, profile metadata, lock-file hashes, and explicit CPython wheel tags.

The existing `pyfixagent-runner:0.7.2` image remains the configured reviewed runner until a separately qualified v0.7.3 image exists.

## 0.7.2

- Added runner portability and reproducible benchmark evidence, including Docker and Linux Podman CI coverage, reviewed finite profiles, and schema-5 report metadata.
- See [the detailed v0.7.2 record](docs/v0.7.2.md) and [runner qualification](docs/results/v0.7.2-runner-qualification.md).

## Earlier releases

- [v0.7.1](docs/v0.7.1.md), [v0.7.0](docs/v0.7.0.md), and [v0.6.3](docs/v0.6.3.md)
- [v0.6.2](docs/v0.6.2.md), [v0.6.1](docs/v0.6.1.md), [v0.6.0](docs/v0.6.0.md)
- [v0.5.1](docs/v0.5.1.md), [v0.5.0](docs/v0.5.0.md), [v0.4.1](docs/v0.4.1.md), and [v0.4.0](docs/v0.4.0.md)
