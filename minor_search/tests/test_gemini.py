"""Tests for the Gemini helper utilities."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

stub_package = ModuleType("minor_search")
stub_package.__path__ = [str(PACKAGE_DIR)]
sys.modules.setdefault("minor_search", stub_package)

gemini_module = importlib.import_module("minor_search.gemini")


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Ensure the Gemini client cache is reset before each test."""

    gemini_module._configure_client.cache_clear()
    yield
    gemini_module._configure_client.cache_clear()


def test_generate_related_queries_returns_empty_for_non_positive_limit(monkeypatch):
    """When limit is zero or negative the helper should return an empty list."""

    sentinel = object()
    monkeypatch.setattr(gemini_module, "genai", sentinel, raising=False)

    assert gemini_module.generate_related_queries("seed", limit=0) == []
    assert gemini_module.generate_related_queries("seed", limit=-1) == []


def test_generate_related_queries_uses_gemini_and_filters_duplicates(monkeypatch):
    """The helper should call Gemini once and normalise the output lines."""

    class DummyGenAI:
        def __init__(self) -> None:
            self.configured_with: str | None = None
            self.last_model: str | None = None
            self.last_prompt: str | None = None

        def configure(self, api_key: str) -> None:  # pragma: no cover - simple setter
            self.configured_with = api_key

    dummy = DummyGenAI()

    def make_model(model_name: str):
        dummy.last_model = model_name

        class _Model:
            def generate_content(self, prompt: str):  # pragma: no cover - simple store
                dummy.last_prompt = prompt
                return SimpleNamespace(
                    text="seed query\nRelated Topic\nRelated Topic\nFresh Idea  "
                )

        return _Model()

    dummy.GenerativeModel = make_model  # type: ignore[attr-defined]

    monkeypatch.setattr(gemini_module, "genai", dummy, raising=False)

    related = gemini_module.generate_related_queries(
        "seed query",
        limit=5,
        api_key="test-key",
        context_samples=["ctx-1", "ctx-2"],
    )

    assert related == ["Related Topic", "Fresh Idea"]
    assert dummy.configured_with == "test-key"
    assert dummy.last_model == gemini_module.DEFAULT_MODEL
    assert dummy.last_prompt is not None
    assert "seed query" in dummy.last_prompt
    assert "ctx-1" in dummy.last_prompt
