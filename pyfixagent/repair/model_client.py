import time

from pyfixagent.models.base import BaseModel
from pyfixagent.trace import model_call_metadata


class ModelGenerationError(RuntimeError):
    def __init__(self, error: Exception, metadata: dict):
        super().__init__(str(error))
        self.metadata = metadata


class ModelClient:
    """Captures model timing and token metadata behind one boundary."""

    def __init__(self, model: BaseModel):
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        started = time.perf_counter()
        try:
            output = self.model.generate_patch(system_prompt, user_prompt)
        except Exception as exc:
            duration = time.perf_counter() - started
            raise ModelGenerationError(exc, model_call_metadata(self.model, duration)) from exc
        return output, model_call_metadata(self.model, time.perf_counter() - started)

    def metadata(self, duration_seconds: float | None = None) -> dict:
        return model_call_metadata(self.model, duration_seconds)
