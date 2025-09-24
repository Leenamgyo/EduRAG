"""Minimal StructuredTool implementation compatible with tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class StructuredTool:
    """Simple callable wrapper used by the orchestrator."""

    func: Callable[..., Any]
    name: str
    description: str

    @classmethod
    def from_function(
        cls, func: Callable[..., Any], *, name: str, description: str
    ) -> "StructuredTool":
        return cls(func=func, name=name, description=description)

    def invoke(self, input_data: Any) -> Any:
        if isinstance(input_data, dict):
            return self.func(**input_data)
        return self.func(input_data)


__all__ = ["StructuredTool"]
