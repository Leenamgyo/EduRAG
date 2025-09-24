import importlib
import sys
import types
from pathlib import Path


def _install_engine_stub(monkeypatch, *, init_exception=None, run_result=None, run_exception=None):
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

    if "langchain" not in sys.modules:
        monkeypatch.setitem(sys.modules, "langchain", types.ModuleType("langchain"))

    if "langchain.globals" not in sys.modules:
        globals_module = types.ModuleType("langchain.globals")

        def _noop(_value=None):
            return None

        globals_module.set_debug = _noop
        globals_module.set_verbose = _noop
        monkeypatch.setitem(sys.modules, "langchain.globals", globals_module)

    if "dotenv" not in sys.modules:
        dotenv_module = types.ModuleType("dotenv")

        def _load_dotenv(*_args, **_kwargs):
            return None

        dotenv_module.load_dotenv = _load_dotenv
        monkeypatch.setitem(sys.modules, "dotenv", dotenv_module)

    module = types.ModuleType("ai_search.core.analysis_engine")

    class StubAnalysisError(RuntimeError):
        """Stub AnalysisError used for testing."""

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
            return run_result or StubAnalysisResult({})

    module.AnalysisEngine = StubEngine
    module.AnalysisError = StubAnalysisError
    module.AnalysisResult = StubAnalysisResult
    module.SearchResult = object
    module.StepResult = object
    module.ToolSearchResult = object

    monkeypatch.setitem(sys.modules, "ai_search.core.analysis_engine", module)

    if "ai_search.cli.app" in sys.modules:
        importlib.reload(sys.modules["ai_search.cli.app"])
    else:
        importlib.import_module("ai_search.cli.app")

    return sys.modules["ai_search.cli.app"]


def test_run_cli_handles_initialisation_error(monkeypatch, capsys):
    cli_app = _install_engine_stub(monkeypatch, init_exception=ValueError("missing key"))

    cli_app.run_cli([])

    output = capsys.readouterr().out
    assert "초기화" in output
    assert "missing key" in output
