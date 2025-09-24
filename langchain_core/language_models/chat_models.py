"""Base chat model abstraction used by tests."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class BaseChatModel:
    """Extremely small subset of the LangChain BaseChatModel API."""

    def __init__(self) -> None:
        pass

    @property
    def _llm_type(self) -> str:  # pragma: no cover - to be overridden
        return "base-chat-model"

    def invoke(self, messages: Iterable[BaseMessage]) -> BaseMessage:
        chat_result = self._generate(list(messages))
        return chat_result.generations[0].message

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError


__all__ = ["BaseChatModel"]
