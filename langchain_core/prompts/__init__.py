"""Simple chat prompt template stub."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from langchain_core.messages import HumanMessage, SystemMessage


class ChatPromptTemplate:
    """Very small formatter for chat messages."""

    def __init__(self, messages: Sequence[Tuple[str, str]]) -> None:
        self._messages = list(messages)

    @classmethod
    def from_messages(cls, messages: Sequence[Tuple[str, str]]) -> "ChatPromptTemplate":
        return cls(messages)

    def format_messages(self, **kwargs) -> List[object]:
        formatted: List[object] = []
        for role, template in self._messages:
            content = template.format(**kwargs)
            if role == "system":
                formatted.append(SystemMessage(content))
            else:
                formatted.append(HumanMessage(content))
        return formatted


__all__ = ["ChatPromptTemplate"]
