# Changelog

This file is the concise change index. Detailed historical release records and qualification evidence remain under `docs/`.

## 0.7.4.dev0 — in development

- Hardened the semantic reviewer against transient API errors: reviewer model calls now retry (configurable `semantic_review.max_model_retries`, default 2, with a short backoff) before failing closed, so a one-off API error no longer rejects an otherwise correct candidate.
- Widened the deterministic `delimiter_composition` cue to catch regex normalizations that insert a delimiter excluded from its own negated character class (slugify-style repeated separators), while keeping it resolvable and silent on correct code. The numeric rounding cue was intentionally left unchanged to avoid firing on correct `ROUND_HALF_UP` currency cases.
- Injected explicit, evidence-gated domain conventions into the reviewer prompt (banker's rounding for proration/ties vs `ROUND_HALF_UP` for currency, collapsing repeated separators, rejecting non-positive configuration parameters, raising on traversal cycles).
- A targeted real-model re-run of the five v0.7.3 non-success cases improved final success from 0/5 to 3/5 with no regressions on the 22 passing cases. See the [convergence validation record](docs/results/v0.7.3-convergence-validation.md).

## 0.7.3 — Released 2026-07-25

This release has not published a package or runner image.

- Split repair, benchmark, container, configuration, and metric orchestration into focused units with AST architecture checks that guard their entrypoints.
- Replaced the default configured model with `qwen3.7-plus` on the existing DashScope OpenAI-compatible endpoint.
- Added rootless Podman bind-mount UID preservation with `--userns keep-id` for `workspace_owner`.
- Replaced silent broad exception handling with specific error boundaries or stack-bearing logs; CLI report and approval output remains stdout by design.
- Added runner-profile validation for Dockerfile CPython, profile metadata, lock-file hashes, and explicit CPython wheel tags.
- Recorded a one-repetition `qwen3.7-plus` run across all 27 curated cases: 22/27 final successes (81.5%), 27/27 visible-test passes, and 23/27 external-holdout passes. See the versioned result for scope and failure analysis.

The existing `pyfixagent-runner:0.7.2` image remains the configured reviewed runner until a separately qualified v0.7.3 image exists.

Full-suite verification on the release source completed with `python -m pytest -q`: **230 passed, 6 skipped** in 131.30 seconds. The skips are conditional environment or integration coverage; no test failed.

See [the v0.7.3 release record](docs/v0.7.3.md) and [full-model benchmark result](docs/results/v0.7.3-qwen3.7-plus-full-20260726.md) for scope and evidence.

## 0.7.2

- Added runner portability and reproducible benchmark evidence, including Docker and Linux Podman CI coverage, reviewed finite profiles, and schema-5 report metadata.
- See [the detailed v0.7.2 record](docs/v0.7.2.md) and [runner qualification](docs/results/v0.7.2-runner-qualification.md).

## Earlier releases

- [v0.7.1](docs/v0.7.1.md), [v0.7.0](docs/v0.7.0.md), and [v0.6.3](docs/v0.6.3.md)
- [v0.6.2](docs/v0.6.2.md), [v0.6.1](docs/v0.6.1.md), [v0.6.0](docs/v0.6.0.md)
- [v0.5.1](docs/v0.5.1.md), [v0.5.0](docs/v0.5.0.md), [v0.4.1](docs/v0.4.1.md), and [v0.4.0](docs/v0.4.0.md)
