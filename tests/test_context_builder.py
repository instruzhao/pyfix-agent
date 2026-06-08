from pyfixagent.context.builder import context_trace_metadata, render_selected_context
from pyfixagent.context.selector import SelectedContext, SelectedSnippet


def test_render_selected_context_includes_reasons_and_ranges():
    context = SelectedContext(
        strategy="traceback",
        fallback_used=False,
        snippets=[
            SelectedSnippet(
                path="pkg/app.py",
                reason="traceback_source_file",
                start_line=1,
                end_line=3,
                content="def value():\n    return 1\n",
            )
        ],
    )

    rendered = render_selected_context(context)

    assert "Selected context strategy:" in rendered
    assert "reason: traceback_source_file" in rendered
    assert "lines: 1-3" in rendered
    assert "--- pkg/app.py:1-3 ---" in rendered


def test_context_trace_metadata_is_serializable_shape():
    context = SelectedContext(
        strategy="traceback",
        fallback_used=True,
        prompt_chars=123,
        snippets=[
            SelectedSnippet(
                path="app.py",
                reason="fallback_full_context",
                start_line=1,
                end_line=2,
                content="x = 1\n",
            )
        ],
    )

    metadata = context_trace_metadata(context)

    assert metadata == {
        "strategy": "traceback",
        "fallback_used": True,
        "prompt_chars": 123,
        "dependency_analysis": False,
        "stats": {
            "selected_file_count": 1,
            "selected_snippet_count": 1,
            "selected_context_chars": 6,
            "pytest_output_chars": None,
            "prompt_chars": 123,
            "fallback_used": True,
        },
        "selected_files": [
            {
                "path": "app.py",
                "reason": "fallback_full_context",
                "selection_rule": "fallback_full_context",
                "dependency_analysis": False,
                "line_range": [1, 2],
            }
        ],
    }
