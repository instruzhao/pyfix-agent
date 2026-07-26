from __future__ import annotations

import time

from pyfixagent.repair.model_client import ModelClient, ModelGenerationError
from pyfixagent.review.context import validate_review_evidence
from pyfixagent.review.contracts import ReviewExecution, ReviewRequest
from pyfixagent.review.parser import ReviewParseError, ReviewParser
from pyfixagent.review.prompting import (
    REVIEW_SYSTEM_PROMPT,
    build_parse_retry_prompt,
    build_review_prompt,
)
from pyfixagent.utils.logger import get_logger

logger = get_logger(__name__)


class SemanticReviewer:
    """Calls and validates a semantic reviewer without making workflow decisions."""

    def __init__(
        self,
        model_client: ModelClient,
        parser: ReviewParser,
        max_parse_retries: int = 1,
        max_model_retries: int = 2,
        model_retry_backoff_seconds: float = 1.0,
    ):
        self.model_client = model_client
        self.parser = parser
        self.max_parse_retries = max(0, max_parse_retries)
        self.max_model_retries = max(0, max_model_retries)
        self.model_retry_backoff_seconds = max(0.0, model_retry_backoff_seconds)

    def _generate_with_retry(self, system_prompt: str, prompt: str, execution: ReviewExecution):
        """Call the reviewer model, retrying transient generation errors before failing closed.

        A single API hiccup must not discard an otherwise correct candidate: the call is
        retried with a short linear backoff, and only an exhausted retry budget is recorded
        as a model error.
        """
        last_error: ModelGenerationError | None = None
        for model_attempt in range(self.max_model_retries + 1):
            try:
                raw, metadata = self.model_client.generate(system_prompt, prompt)
            except ModelGenerationError as exc:
                last_error = exc
                execution.model_calls.append(exc.metadata)
                if model_attempt < self.max_model_retries:
                    logger.warning(
                        "semantic review model call failed (attempt %d/%d); retrying: %s",
                        model_attempt + 1,
                        self.max_model_retries + 1,
                        exc,
                    )
                    if self.model_retry_backoff_seconds:
                        time.sleep(self.model_retry_backoff_seconds * (model_attempt + 1))
                    continue
                execution.model_error = str(exc)
                return None
            execution.model_calls.append(metadata)
            return raw
        if last_error is not None:
            execution.model_error = str(last_error)
        return None

    def review(self, request: ReviewRequest, workspace) -> ReviewExecution:
        base_prompt = build_review_prompt(request)
        prompt = base_prompt
        execution = ReviewExecution(prompt=base_prompt, context=request.context.metadata)
        for attempt in range(self.max_parse_retries + 1):
            raw = self._generate_with_retry(REVIEW_SYSTEM_PROMPT, prompt, execution)
            if raw is None:
                return execution
            execution.raw_output = raw
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
