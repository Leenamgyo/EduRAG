"""Simplified agent executor for offline testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from langchain_core.messages import BaseMessage


@dataclass
class _SimpleAgent:
    llm: Any
    prompt: Any
    tools: List[Any]


def create_tool_calling_agent(llm: Any, tools: Iterable[Any], prompt: Any) -> _SimpleAgent:
    return _SimpleAgent(llm=llm, prompt=prompt, tools=list(tools))


class AgentExecutor:
    def __init__(self, *, agent: _SimpleAgent, tools: Iterable[Any], verbose: bool = False) -> None:
        self._agent = agent
        self._tools = list(tools)
        self._verbose = verbose

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        messages = self._agent.prompt.format_messages(**inputs)
        response = self._agent.llm.invoke(messages)
        return {"output": response}


__all__ = ["AgentExecutor", "create_tool_calling_agent"]
