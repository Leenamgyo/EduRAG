import importlib
import sys
import types
from pathlib import Path

import pytest


def _ensure_fastapi_stubs(monkeypatch):
    if "fastapi" not in sys.modules:
        fastapi_module = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = {}

            def get(self, path: str, **kwargs):
                def decorator(func):
                    self.routes[("GET", path)] = func
                    return func

                return decorator

            def post(self, path: str, **kwargs):
                def decorator(func):
                    self.routes[("POST", path)] = func
                    return func

                return decorator

        fastapi_module.FastAPI = FastAPI
        fastapi_module.HTTPException = HTTPException
        monkeypatch.setitem(sys.modules, "fastapi", fastapi_module)

    if "pydantic" not in sys.modules:
        pydantic_module = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **data):
                for key, value in data.items():
                    setattr(self, key, value)

        def Field(default=..., **kwargs):
            return default

        pydantic_module.BaseModel = BaseModel
        pydantic_module.Field = Field
        monkeypatch.setitem(sys.modules, "pydantic", pydantic_module)


def _install_engine_stub(monkeypatch, *, init_exception=None, run_exception=None, run_payload=None):
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

    _ensure_fastapi_stubs(monkeypatch)

    module = types.ModuleType("ai_search.core.analysis_engine")

    class StubAnalysisError(RuntimeError):
        """Stub error used by the fake analysis engine."""

    class StubAnalysisResult:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self):
            return dict(self._payload)

    class StubEngine:
        def __init__(self):
            if init_exception is not None:
                raise init_exception

        def run(self, question):
            if run_exception is not None:
                raise run_exception
            payload = run_payload or {
                "question": question,
                "analysis_plan": "",
                "search_results": [],
                "step_results": [],
                "final_answer": "",
            }
            return StubAnalysisResult(payload)

    module.AnalysisEngine = StubEngine
    module.AnalysisError = StubAnalysisError
    module.AnalysisResult = StubAnalysisResult
    module.SearchResult = object
    module.StepResult = object
    module.ToolSearchResult = object

    monkeypatch.setitem(sys.modules, "ai_search.core.analysis_engine", module)

    if "ai_search.service.api" in sys.modules:
        importlib.reload(sys.modules["ai_search.service.api"])
    else:
        importlib.import_module("ai_search.service.api")

    return sys.modules["ai_search.service.api"]


def test_run_query_returns_500_when_engine_initialisation_fails(monkeypatch):
    api_module = _install_engine_stub(monkeypatch, init_exception=ValueError("missing key"))

    with pytest.raises(api_module.HTTPException) as exc_info:
        api_module.run_query(api_module.QuestionRequest(question="테스트"))

    assert exc_info.value.status_code == 500
    assert "missing key" in str(exc_info.value.detail)
