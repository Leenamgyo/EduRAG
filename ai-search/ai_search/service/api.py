from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ai_search.core.analysis_engine import AnalysisEngine, AnalysisError


class QuestionRequest(BaseModel):
    """Incoming payload for analysis requests."""

    question: str = Field(..., description="사용자가 던진 연구 질문")


class ToolResultModel(BaseModel):
    tool: str
    content: str


class SearchResultModel(BaseModel):
    query: str
    results: list[ToolResultModel]


class StepResultModel(BaseModel):
    step: str
    prompt: str
    output: str


class AnalysisResponse(BaseModel):
    """Structured response returned to the caller."""

    question: str
    analysis_plan: str
    search_results: list[SearchResultModel]
    step_results: list[StepResultModel]
    final_answer: str
    report_id: str | None = None


app = FastAPI(title="AI Search Backend", version="1.0.0")


@app.get("/health", summary="서비스 상태 확인")
def health_check() -> dict[str, str]:
    """Simple health endpoint used for readiness checks."""

    return {"status": "ok"}


@app.post("/query", response_model=AnalysisResponse, summary="질문 분석")
def run_query(payload: QuestionRequest) -> AnalysisResponse:
    """Execute the analysis pipeline for the supplied question."""

    try:
        engine = AnalysisEngine()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - expose unexpected server errors
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        result = engine.run(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - expose unexpected server errors
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AnalysisResponse(**result.to_dict())


__all__ = ["app"]

