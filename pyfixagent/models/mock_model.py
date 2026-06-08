from dataclasses import dataclass, field

from pyfixagent.models.base import BaseModel


@dataclass
class MockModel(BaseModel):
    outputs: list[str]
    calls: int = 0
    prompts: list[str] = field(default_factory=list)

    def generate_patch(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        if self.calls >= len(self.outputs):
            raise RuntimeError("MockModel has no more outputs")
        output = self.outputs[self.calls]
        self.calls += 1
        return output
