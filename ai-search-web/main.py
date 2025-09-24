from __future__ import annotations

from pathlib import Path

from streamlit.runtime.scriptrunner import get_script_run_ctx
from streamlit.web.bootstrap import run as bootstrap_run

from ai_search_web.app import main as app_main


def launch() -> None:
    """Provide a CLI-friendly entry point for Streamlit."""

    if get_script_run_ctx() is not None:
        app_main()
        return

    script_path = Path(__file__).resolve().parent / "ai_search_web" / "app.py"
    bootstrap_run(str(script_path), "", [], {})


if __name__ == "__main__":
    launch()
