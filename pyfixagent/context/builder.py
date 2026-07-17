from pyfixagent.context.selector import SelectedContext


def render_selected_context(context: SelectedContext) -> str:
    selected_files = "\n".join(
        (
            f"{index}. {snippet.path}\n"
            f"   reason: {snippet.reason}\n"
            f"   lines: {snippet.start_line}-{snippet.end_line}"
        )
        for index, snippet in enumerate(context.snippets, start=1)
    )
    if not selected_files:
        selected_files = "(none)"

    code_snippets = "\n\n".join(
        f"--- {snippet.path}:{snippet.start_line}-{snippet.end_line} ---\n{snippet.content}"
        for snippet in context.snippets
    )
    if not code_snippets:
        code_snippets = "(no Python snippets selected)"

    fallback = "true" if context.fallback_used else "false"
    return (
        f"Selected context strategy:\n{context.strategy}\n\n"
        f"Context fallback used:\n{fallback}\n\n"
        f"Selected files:\n{selected_files}\n\n"
        f"Code snippets:\n{code_snippets}"
    )


def context_trace_metadata(context: SelectedContext) -> dict:
    selected_paths = [snippet.path for snippet in context.snippets]
    selected_context_chars = sum(len(snippet.content) for snippet in context.snippets)
    dependency_analysis = bool(context.repository_metadata)
    metadata = {
        "strategy": context.strategy,
        "fallback_used": context.fallback_used,
        "prompt_chars": context.prompt_chars,
        "dependency_analysis": dependency_analysis,
        "stats": {
            "selected_file_count": len(set(selected_paths)),
            "selected_snippet_count": len(context.snippets),
            "selected_context_chars": selected_context_chars,
            "pytest_output_chars": None,
            "prompt_chars": context.prompt_chars,
            "fallback_used": context.fallback_used,
        },
        "selected_files": [
            {
                "path": snippet.path,
                "reason": snippet.reason,
                "selection_rule": snippet.reason,
                "dependency_analysis": dependency_analysis,
                "line_range": [snippet.start_line, snippet.end_line],
                **({"score": snippet.score} if snippet.score is not None else {}),
                **(
                    {"graph_distance": snippet.graph_distance}
                    if snippet.graph_distance is not None
                    else {}
                ),
                **({"symbol": snippet.symbol} if snippet.symbol else {}),
            }
            for snippet in context.snippets
        ],
    }
    if context.repository_metadata:
        metadata["repository"] = context.repository_metadata
        metadata["stats"]["estimated_selected_tokens"] = context.repository_metadata.get(
            "estimated_selected_tokens"
        )
        metadata["stats"]["budget_truncated"] = context.repository_metadata.get("budget_truncated")
    return metadata
