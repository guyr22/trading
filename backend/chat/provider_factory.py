"""Factory — maps provider name → BaseChatProvider instance."""
from fastapi import HTTPException

from chat.providers.base import BaseChatProvider
from chat.providers.claude_provider import ClaudeProvider
from chat.providers.gemini_provider import GeminiProvider
from chat.providers.openai_provider import OpenAIProvider

_PROVIDERS: dict[str, BaseChatProvider] = {
    "claude":   ClaudeProvider(),
    "openai":   OpenAIProvider(),
    "gemini":   GeminiProvider("gemini"),
    "gemini25": GeminiProvider("gemini25"),
    "gemini35": GeminiProvider("gemini35"),
}


def get_provider(name: str) -> BaseChatProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {name}")
    return provider
