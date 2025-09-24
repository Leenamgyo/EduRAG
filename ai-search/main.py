from __future__ import annotations

import os

import uvicorn


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Interpret common truthy strings for environment toggles."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    """Launch the FastAPI service using uvicorn."""
    host = os.getenv("HOST", "0.0.0.0")
    port_raw = os.getenv("PORT", "8000")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("PORT environment variable must be an integer") from exc

    uvicorn.run(
        "ai_search.service.api:app",
        host=host,
        port=port,
        reload=_as_bool(os.getenv("UVICORN_RELOAD")),
        factory=False,
    )


if __name__ == "__main__":
    main()
