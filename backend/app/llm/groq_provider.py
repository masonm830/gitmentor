import json
from groq import AsyncGroq

from app.config import settings
from app.llm.base import LLMProvider


class GroqProvider(LLMProvider):
    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = model

    async def generate(self, prompt: str, system: str | None = None, temperature: float = 0.7) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    async def generate_structured(self, prompt: str, schema: dict, system: str | None = None) -> dict:
        schema_instruction = f"Respond with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
        full_system = f"{system}\n\n{schema_instruction}" if system else schema_instruction

        response = await self.generate(prompt, system=full_system, temperature=0.0)
        return json.loads(response)
