"""Minimal runnable implementations."""

from __future__ import annotations

from typing import Any, Callable, Dict


class RunnableLambda:
    def __init__(self, func: Callable[[Any], Any]) -> None:
        self._func = func

    def invoke(self, input_data: Any) -> Any:
        return self._func(input_data)


class RunnablePassthrough:
    def invoke(self, input_data: Any) -> Any:
        return input_data


class RunnableParallel:
    def __init__(self, **runnables: Any) -> None:
        self._runnables = runnables

    def invoke(self, input_data: Any) -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for key, runnable in self._runnables.items():
            if hasattr(runnable, "invoke"):
                output[key] = runnable.invoke(input_data)
            else:
                output[key] = runnable(input_data)
        return output


__all__ = ["RunnableLambda", "RunnableParallel", "RunnablePassthrough"]
