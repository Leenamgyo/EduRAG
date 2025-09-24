"""Simple chat result structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from langchain_core.messages import AIMessage


@dataclass
class ChatGeneration:
    message: AIMessage


@dataclass
class ChatResult:
    generations: List[ChatGeneration]


__all__ = ["ChatGeneration", "ChatResult"]
