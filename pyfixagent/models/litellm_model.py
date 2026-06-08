from dataclasses import dataclass
from typing import Any

from litellm import completion

from pyfixagent.models.base import BaseModel


@dataclass
class LiteLLMModel(BaseModel):
    model_name: str
    api_base: str | None = None
    api_key: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2000
    timeout_seconds: int = 60
    extra_body: dict | None = None

    def generate_patch(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response: Any = completion(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout_seconds,
                api_base=self.api_base,
                api_key=self.api_key,
                extra_body=self.extra_body,
            )
            content = response["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("model returned an empty patch")
            return content
        except Exception as exc:
            raise RuntimeError(f"LiteLLM patch generation failed: {exc}") from exc
