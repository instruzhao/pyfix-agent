from __future__ import annotations

from pyfixagent.repair.model_client import ModelClient, ModelGenerationError
from pyfixagent.review.context import validate_review_evidence
from pyfixagent.review.contracts import ReviewExecution, ReviewRequest
from pyfixagent.review.parser import ReviewParseError, ReviewParser
from pyfixagent.review.prompting import (
    REVIEW_SYSTEM_PROMPT,
    build_parse_retry_prompt,
    build_review_prompt,
)


class SemanticReviewer:
    """Calls and validates a semantic reviewer without making workflow decisions."""

    def __init__(
        self,
        model_client: ModelClient,
        parser: ReviewParser,
        max_parse_retries: int = 1,
    ):
        self.model_client = model_client
        self.parser = parser
        self.max_parse_retries = max(0, max_parse_retries)

    def review(self, request: ReviewRequest, workspace) -> ReviewExecution:
        base_prompt = build_review_prompt(request)
        prompt = base_prompt
        execution = ReviewExecution(prompt=base_prompt, context=request.context.metadata)
        for attempt in range(self.max_parse_retries + 1):
            try:
                raw, metadata = self.model_client.generate(REVIEW_SYSTEM_PROMPT, prompt)
            except ModelGenerationError as exc:
                execution.model_error = str(exc)
                execution.model_calls.append(exc.metadata)
                return execution
            execution.raw_output = raw
            execution.model_calls.append(metadata)
            try:
                outcome = self.parser.parse(raw)
                evidence_errors = validate_review_evidence(workspace, outcome)
                if evidence_errors:
                    raise ReviewParseError("; ".join(evidence_errors))
                execution.outcome = outcome
                execution.parse_error = None
                return execution
            except ReviewParseError as exc:
                execution.parse_error = str(exc)
                if attempt >= self.max_parse_retries:
                    return execution
                prompt = build_parse_retry_prompt(base_prompt, execution.parse_error)
        return execution
