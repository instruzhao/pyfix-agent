from pathlib import Path

from pyfixagent.context.provider import ContextProvider
from pyfixagent.context.repository import RepositoryContextExpander
from pyfixagent.context.selector import SelectedContext, SelectedSnippet
from pyfixagent.repository.cache import RepositoryIndexStore
from pyfixagent.repository.indexer import RepositoryIndexer
from pyfixagent.repository.service import RepositoryIndexService
from pyfixagent.review.context import ReviewContextProvider
from pyfixagent.benchmarking.manifest import load_manifest


def make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "pkg").mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "pkg" / "rules.py").write_text(
        "RAISED_IF_IMPORTED = True\n"
        "if RAISED_IF_IMPORTED:\n"
        "    raise RuntimeError('repository code must not execute')\n\n"
        "def apply_discount(value, rate):\n"
        "    return value * (1 - rate)\n",
        encoding="utf-8",
    )
    (workspace / "pkg" / "service.py").write_text(
        "from pkg.rules import apply_discount\n\n"
        "def calculate_total(value, rate):\n"
        "    return apply_discount(value, rate)\n",
        encoding="utf-8",
    )
    (workspace / "tests" / "test_service.py").write_text(
        "from pkg.service import calculate_total\n\n"
        "def test_total():\n"
        "    assert calculate_total(100, 0.2) == 80\n",
        encoding="utf-8",
    )
    return workspace


def make_service(tmp_path: Path) -> RepositoryIndexService:
    return RepositoryIndexService(
        RepositoryIndexer(),
        RepositoryIndexStore(tmp_path / "index-cache"),
    )


def test_static_index_records_symbols_and_import_edges_without_execution(tmp_path):
    workspace = make_workspace(tmp_path)

    index = RepositoryIndexer().build(workspace)

    assert {item.path for item in index.files} == {
        "pkg/__init__.py",
        "pkg/rules.py",
        "pkg/service.py",
        "tests/test_service.py",
    }
    assert "pkg/rules.py:apply_discount" in {item.symbol_id for item in index.symbols}
    assert ("pkg/service.py", "pkg/rules.py") in {
        (edge.source_path, edge.target_path) for edge in index.edges
    }
    assert ("tests/test_service.py", "pkg/service.py") in {
        (edge.source_path, edge.target_path) for edge in index.edges
    }


def test_index_cache_hits_and_content_change_invalidates_fingerprint(tmp_path):
    workspace = make_workspace(tmp_path)
    cache_dir = tmp_path / "index-cache"
    first_service = RepositoryIndexService(RepositoryIndexer(), RepositoryIndexStore(cache_dir))

    first, first_meta = first_service.get(workspace)
    second_service = RepositoryIndexService(RepositoryIndexer(), RepositoryIndexStore(cache_dir))
    second, second_meta = second_service.get(workspace)
    (workspace / "pkg" / "service.py").write_text(
        "from pkg.rules import apply_discount\n\ndef calculate_total(value, rate):\n    return value\n",
        encoding="utf-8",
    )
    changed, changed_meta = second_service.get(workspace)

    assert first_meta["cache_hit"] is False
    assert second_meta["cache_source"] == "disk"
    assert first == second
    assert changed.fingerprint != first.fingerprint
    assert changed_meta["cache_hit"] is False


def test_cache_inside_workspace_is_bypassed(tmp_path):
    workspace = make_workspace(tmp_path)
    cache_dir = workspace / "outputs" / "index"
    service = RepositoryIndexService(RepositoryIndexer(), RepositoryIndexStore(cache_dir))

    _, metadata = service.get(workspace)

    assert metadata["cache_bypassed_inside_workspace"] is True
    assert not cache_dir.exists()


def test_repository_expander_adds_ranked_symbol_dependency_under_budget(tmp_path):
    workspace = make_workspace(tmp_path)
    service = make_service(tmp_path)
    base = SelectedContext(
        strategy="traceback",
        fallback_used=False,
        snippets=[
            SelectedSnippet(
                path="tests/test_service.py",
                reason="failing_test_file",
                start_line=1,
                end_line=4,
                content=(workspace / "tests" / "test_service.py").read_text(encoding="utf-8"),
            ),
            SelectedSnippet(
                path="pkg/service.py",
                reason="direct_test_import",
                start_line=1,
                end_line=4,
                content=(workspace / "pkg" / "service.py").read_text(encoding="utf-8"),
            ),
        ],
    )
    expander = RepositoryContextExpander(
        service,
        max_selected_tokens=200,
        max_graph_depth=2,
        max_related_files=3,
    )

    expanded = expander.expand(workspace, base, "calculate_total apply_discount")

    related = next(item for item in expanded.snippets if item.path == "pkg/rules.py")
    assert related.reason == "repository_import_dependency"
    assert related.graph_distance == 1
    assert related.symbol == "pkg/rules.py:apply_discount"
    assert "def apply_discount" in related.content
    assert expanded.repository_metadata["edge_count"] == 2
    assert expanded.repository_metadata["estimated_selected_tokens"] <= 200


def test_context_provider_exposes_repository_trace_metadata(tmp_path):
    workspace = make_workspace(tmp_path)
    pytest_output = (
        "FAILED tests/test_service.py::test_total - assert 70 == 80\n"
        f"{workspace / 'tests' / 'test_service.py'}:4: AssertionError\n"
    )
    provider = ContextProvider(
        strategy="traceback",
        line_window=2,
        max_files=3,
        repository_expander=RepositoryContextExpander(make_service(tmp_path)),
    )

    bundle = provider.build(workspace, pytest_output)

    assert bundle.metadata["dependency_analysis"] is True
    assert bundle.metadata["repository"]["schema_version"] == "1"
    assert any(
        item["reason"] == "repository_import_dependency"
        for item in bundle.metadata["selected_files"]
    )
    assert "pkg/rules.py" in bundle.rendered


def test_review_context_reuses_repository_graph_without_holdout_inputs(tmp_path):
    workspace = make_workspace(tmp_path)
    provider = ReviewContextProvider(
        repository_expander=RepositoryContextExpander(make_service(tmp_path)),
    )
    candidate_diff = (
        "diff --git a/pkg/service.py b/pkg/service.py\n"
        "--- a/pkg/service.py\n"
        "+++ b/pkg/service.py\n"
    )

    bundle = provider.build(workspace, candidate_diff)

    assert bundle.metadata["repository"]["edge_count"] == 2
    assert any(
        item["path"] == "pkg/rules.py" and item["reason"] == "repository_import_dependency"
        for item in bundle.metadata["selected_files"]
    )
    assert "holdout" not in bundle.rendered.casefold()


def test_syntax_errors_are_recorded_without_aborting_index(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (workspace / "healthy.py").write_text("def healthy():\n    return True\n", encoding="utf-8")

    index = RepositoryIndexer().build(workspace)

    assert len(index.parse_errors) == 1
    assert index.parse_errors[0].path == "broken.py"
    assert "healthy.py:healthy" in {item.symbol_id for item in index.symbols}


def test_file_limit_still_fingerprints_skipped_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.py").write_text("A = 1\n", encoding="utf-8")
    indexer = RepositoryIndexer(max_files=1)

    before = indexer.snapshot(workspace)
    (workspace / "z.py").write_text("Z = 1\n", encoding="utf-8")
    after = indexer.snapshot(workspace)

    assert before.fingerprint != after.fingerprint
    assert after.skipped_files == 1


def test_v062_multifile_fixtures_retrieve_required_paths_without_distractors(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    cases = [
        case
        for case in load_manifest(project_root / "benchmarks" / "cases.yaml", project_root)
        if "v0.6.2" in case.tags
    ]

    assert len(cases) == 9
    for case in cases:
        service = RepositoryIndexService(
            RepositoryIndexer(),
            RepositoryIndexStore(tmp_path / case.case_id),
        )
        provider = ContextProvider(
            strategy="traceback",
            line_window=2,
            max_files=6,
            repository_expander=RepositoryContextExpander(service, max_graph_depth=2),
        )
        pytest_output = (
            "FAILED tests/test_visible.py::test_failure - AssertionError\n"
            "tests/test_visible.py:1: AssertionError\n"
        )

        bundle = provider.build(case.fixture, pytest_output)
        selected = {item["path"] for item in bundle.metadata["selected_files"]}

        assert set(case.context_required_paths).issubset(selected), case.case_id
        assert not (set(case.context_distractor_paths) & selected), case.case_id
