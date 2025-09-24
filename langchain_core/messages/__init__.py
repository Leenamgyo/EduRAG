"""Message primitives used by the stubbed LLM."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BaseMessage:
    content: str
    type: str


class HumanMessage(BaseMessage):
    def __init__(self, content: str) -> None:
        super().__init__(content=content, type="human")


class SystemMessage(BaseMessage):
    def __init__(self, content: str) -> None:
        super().__init__(content=content, type="system")


class AIMessage(BaseMessage):
    def __init__(self, content: str) -> None:
        super().__init__(content=content, type="ai")


__all__ = ["AIMessage", "BaseMessage", "HumanMessage", "SystemMessage"]
