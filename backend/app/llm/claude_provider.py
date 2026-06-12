import json
import anthropic

from app.config import settings
from app.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = model

    async def generate(self, prompt: str, system: str | None = None, temperature: float = 0.7) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)
        return response.content[0].text

    async def generate_structured(self, prompt: str, schema: dict, system: str | None = None) -> dict:
        schema_instruction = f"Respond with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
        full_system = f"{system}\n\n{schema_instruction}" if system else schema_instruction

        response = await self.generate(prompt, system=full_system, temperature=0.0)
        return json.loads(response)
