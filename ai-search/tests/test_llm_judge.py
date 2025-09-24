import json
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from ai_search.jobs.llm_judge import (
    EvaluationResult,
    EvaluationSample,
    JudgeDecision,
    LLMJudge,
    LLMJudgeError,
    JudgeJobReport,
    dump_report,
    load_samples,
    run_llm_judge_job,
)


def _dummy_response(score: float, verdict: str, rationale: str = "ok") -> str:
    return json.dumps({"score": score, "verdict": verdict, "rationale": rationale})


def test_llm_judge_includes_context_in_prompt():
    captured: dict[str, str] = {}

    def fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return _dummy_response(0.8, "pass", "strong match")

    sample = EvaluationSample(
        question="What is RAG?",
        answer="RAG combines retrieval and generation",
        reference="RAG augments generation with retrieved docs",
        context="Document snippet about retrieval",
    )

    judge = LLMJudge(fake_llm, passing_threshold=0.7)
    decision = judge.evaluate(sample)

    assert isinstance(decision, JudgeDecision)
    assert decision.passed is True
    prompt = captured["prompt"]
    assert "Retrieved Context" in prompt
    assert "Document snippet" in prompt


def test_llm_judge_omits_context_section_when_absent():
    captured: dict[str, str] = {}

    def fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return _dummy_response(0.3, "fail", "missing details")

    sample = EvaluationSample(
        question="Define learning analytics",
        answer="Some vague answer",
        reference="Learning analytics is the measurement and analysis...",
    )

    judge = LLMJudge(fake_llm, passing_threshold=0.6)
    decision = judge.evaluate(sample)

    assert decision.passed is False
    prompt = captured["prompt"]
    assert "Retrieved Context" not in prompt


def test_llm_judge_parses_code_block_response():
    def fake_llm(_: str) -> str:
        return "```json\n{\"score\": 0.91, \"verdict\": \"pass\", \"rationale\": \"clear\"}\n```"

    sample = EvaluationSample(
        question="Q",
        answer="A",
        reference="R",
    )

    judge = LLMJudge(fake_llm, passing_threshold=0.5)
    decision = judge.evaluate(sample)

    assert pytest.approx(decision.score, rel=1e-6) == 0.91
    assert decision.passed is True


def test_run_llm_judge_job_aggregates_results():
    responses = iter([
        _dummy_response(0.9, "pass", "great"),
        _dummy_response(0.4, "fail", "weak"),
    ])

    def fake_llm(_: str) -> str:
        return next(responses)

    samples = [
        EvaluationSample(question="q1", answer="a1", reference="r1"),
        EvaluationSample(question="q2", answer="a2", reference="r2"),
    ]

    judge = LLMJudge(fake_llm, passing_threshold=0.6)
    report = run_llm_judge_job(samples, judge)

    assert isinstance(report, JudgeJobReport)
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    summary = report.to_summary()
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert pytest.approx(summary["pass_rate"], rel=1e-6) == 0.5
    assert "average_score" in summary


def test_load_samples_supports_json_and_jsonl(tmp_path: Path):
    json_payload = {
        "samples": [
            {
                "question": "q1",
                "answer": "a1",
                "reference": "r1",
                "context": "ctx",
            }
        ]
    }
    json_path = tmp_path / "samples.json"
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False), encoding="utf-8")

    samples = load_samples(json_path)
    assert len(samples) == 1
    assert samples[0].context == "ctx"

    jsonl_path = tmp_path / "samples.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(item) for item in json_payload["samples"]), encoding="utf-8")
    samples_jsonl = load_samples(jsonl_path)
    assert len(samples_jsonl) == 1
    assert samples_jsonl[0].question == "q1"


def test_dump_report_writes_jsonl(tmp_path: Path):
    sample = EvaluationSample(question="q", answer="a", reference="r")
    decision = JudgeDecision(
        score=0.7,
        verdict="pass",
        rationale="solid",
        raw_response="{...}",
        threshold=0.6,
        raw_label="pass",
    )
    report = JudgeJobReport([EvaluationResult(sample=sample, decision=decision)])

    output = tmp_path / "report.jsonl"
    dump_report(report, output)

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]
    assert lines and lines[0]["score"] == 0.7
    assert lines[0]["verdict"] == "pass"


def test_create_openai_callable_requires_api_key(monkeypatch):
    from ai_search.jobs import llm_judge

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMJudgeError):
        llm_judge.create_openai_callable("gpt-4o-mini")
