from abc import ABC, abstractmethod


class BaseModel(ABC):
    @abstractmethod
    def generate_patch(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a unified diff patch."""
