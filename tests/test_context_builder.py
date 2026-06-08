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
    prompt_chars = 123
    snippet = SelectedSnippet(
        path="app.py",
        reason="fallback_full_context",
        start_line=1,
        end_line=2,
        content="x = 1\n",
    )
    context = SelectedContext(
        strategy="traceback",
        fallback_used=True,
        prompt_chars=prompt_chars,
        snippets=[snippet],
    )

    metadata = context_trace_metadata(context)

    assert metadata == {
        "strategy": "traceback",
        "fallback_used": True,
        "prompt_chars": prompt_chars,
        "dependency_analysis": False,
        "stats": {
            "selected_file_count": 1,
            "selected_snippet_count": 1,
            "selected_context_chars": len(snippet.content),
            "pytest_output_chars": None,
            "prompt_chars": prompt_chars,
            "fallback_used": True,
        },
        "selected_files": [
            {
                "path": snippet.path,
                "reason": snippet.reason,
                "selection_rule": snippet.reason,
                "dependency_analysis": False,
                "line_range": [snippet.start_line, snippet.end_line],
            }
        ],
    }
