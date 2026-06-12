from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None, temperature: float = 0.7) -> str:
        ...

    @abstractmethod
    async def generate_structured(self, prompt: str, schema: dict, system: str | None = None) -> dict:
        ...
