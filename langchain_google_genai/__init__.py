"""Stub implementation of the Gemini chat model for offline testing."""

from __future__ import annotations

from typing import List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ChatGoogleGenerativeAI(BaseChatModel):
    """A deterministic stub that mirrors the LangChain Gemini wrapper."""

    def __init__(self, model: str, temperature: float = 0.0, api_key: str | None = None) -> None:
        super().__init__()
        self.model = model
        self.temperature = temperature
        self.api_key = api_key

    @property
    def _llm_type(self) -> str:
        return "chat-google-generative-ai-stub"

    def _generate(self, messages: List[BaseMessage], stop=None, **kwargs) -> ChatResult:
        user_message = next((msg.content for msg in reversed(messages) if msg.type == "human"), "")
        content = f"[Gemini:{self.model}] {user_message}".strip()
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


__all__ = ["ChatGoogleGenerativeAI"]
