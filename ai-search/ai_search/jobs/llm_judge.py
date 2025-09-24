"""LLM-as-a-judge evaluation utilities for RAG quality control."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


class LLMJudgeError(RuntimeError):
    """Raised when an evaluation cannot be completed."""


@dataclass(slots=True)
class EvaluationSample:
    """Input payload describing a single RAG evaluation example."""

    question: str
    answer: str
    reference: str
    context: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvaluationSample":
        """Create a sample from a dictionary payload."""

        if not isinstance(payload, dict):
            raise ValueError("Sample payload must be a dictionary.")

        question = _pick_first(
            payload,
            ["question", "query", "prompt"],
        )
        answer = _pick_first(
            payload,
            ["answer", "response", "rag_answer", "generated_answer"],
        )
        reference = _pick_first(
            payload,
            ["reference", "ground_truth", "expected", "reference_answer"],
        )
        if not question or not answer or not reference:
            raise ValueError("Sample must include question, answer, and reference fields.")

        context_raw = payload.get("context")
        if context_raw is None:
            context_raw = payload.get("retrieved_context")
        context = _normalise_context(context_raw)

        metadata: dict[str, Any] | None = None
        if isinstance(payload.get("metadata"), dict):
            metadata = dict(payload["metadata"])
        else:
            extras = {key: payload[key] for key in ("id", "doc_id", "example_id") if key in payload}
            if extras:
                metadata = extras

        return cls(
            question=question,
            answer=answer,
            reference=reference,
            context=context,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the sample into a serialisable dictionary."""

        payload: dict[str, Any] = {
            "question": self.question,
            "answer": self.answer,
            "reference": self.reference,
        }
        if self.context is not None:
            payload["context"] = self.context
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(slots=True)
class JudgeDecision:
    """Decision returned by the LLM judge."""

    score: float
    verdict: str
    rationale: str
    raw_response: str
    threshold: float
    raw_label: str | None = None

    @property
    def passed(self) -> bool:
        """Determine whether the example meets the passing criteria."""

        label = (self.verdict or "").strip().lower()
        if label in {"pass", "yes", "true", "correct", "accepted", "good"}:
            return True
        if label in {"fail", "no", "false", "incorrect", "rejected", "bad"}:
            return False
        return self.score >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        """Serialise the decision into a dictionary."""

        return {
            "score": self.score,
            "verdict": self.verdict,
            "rationale": self.rationale,
            "raw_response": self.raw_response,
            "threshold": self.threshold,
            "raw_label": self.raw_label,
            "passed": self.passed,
        }


@dataclass(slots=True)
class EvaluationResult:
    """Pair a sample with its corresponding judge decision."""

    sample: EvaluationSample
    decision: JudgeDecision

    def to_record(self) -> dict[str, Any]:
        """Combine sample and decision data for reporting."""

        record = self.sample.to_dict()
        record.update(self.decision.to_dict())
        return record


@dataclass(slots=True)
class JudgeJobReport:
    """Aggregate the outcome of a full evaluation run."""

    results: list[EvaluationResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.decision.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def average_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(result.decision.score for result in self.results) / self.total

    def to_summary(self) -> dict[str, Any]:
        """Generate a concise summary dictionary."""

        pass_rate = (self.passed / self.total) if self.total else 0.0
        threshold = self.results[0].decision.threshold if self.results else None
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(pass_rate, 4),
            "average_score": round(self.average_score, 4),
            "threshold": threshold,
        }

    def to_records(self) -> list[dict[str, Any]]:
        """Return all evaluation records as dictionaries."""

        return [result.to_record() for result in self.results]


class LLMJudge:
    """Helper that builds prompts and interprets judge responses."""

    def __init__(self, llm_callable: Callable[[str], str], *, passing_threshold: float = 0.65):
        if passing_threshold <= 0 or passing_threshold >= 1:
            raise ValueError("passing_threshold must be between 0 and 1.")
        self._llm_callable = llm_callable
        self._threshold = passing_threshold

    def evaluate(self, sample: EvaluationSample) -> JudgeDecision:
        """Evaluate a single sample using the configured LLM callable."""

        prompt = self._build_prompt(sample)
        response_text = self._llm_callable(prompt)
        data = self._parse_response(response_text)

        score = _normalise_score(data.get("score"))
        raw_label = _pick_first(data, ["verdict", "label", "decision"])
        passed = _interpret_label(raw_label, score, self._threshold)
        verdict = "pass" if passed else "fail"
        rationale = _pick_first(
            data,
            ["rationale", "reason", "explanation", "analysis"],
        ) or ""

        return JudgeDecision(
            score=score,
            verdict=verdict,
            rationale=rationale.strip(),
            raw_response=response_text,
            threshold=self._threshold,
            raw_label=raw_label,
        )

    def _build_prompt(self, sample: EvaluationSample) -> str:
        sections = [
            "You are an impartial judge that verifies the quality of a Retrieval-Augmented Generation (RAG) answer.",
            (
                "Compare the RAG answer to the authoritative reference answer using the retrieved context. "
                "Score the answer between 0 and 1 where higher is better."
            ),
            (
                f"Return a JSON object with the keys: score (float 0-1), verdict ('pass' or 'fail'), "
                "rationale (short explanation)."
            ),
            (
                f"Consider the answer a pass when the score is at least {self._threshold:.2f}. "
                "Respond with JSON only."
            ),
            f"Question:\n{sample.question.strip()}",
            f"Reference Answer:\n{sample.reference.strip()}",
            f"RAG Answer:\n{sample.answer.strip()}",
        ]
        if sample.context:
            sections.append(f"Retrieved Context:\n{sample.context.strip()}")
        if sample.metadata:
            metadata_json = json.dumps(sample.metadata, ensure_ascii=False)
            sections.append(f"Metadata:\n{metadata_json}")
        return "\n\n".join(sections)

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        try:
            return _extract_json_object(response_text)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise LLMJudgeError(f"Failed to parse judge response: {exc}") from exc


def _pick_first(payload: dict[str, Any] | None, keys: Iterable[str]) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _normalise_context(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                snippet = item.strip()
                if snippet:
                    parts.append(snippet)
            elif isinstance(item, dict):
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n\n".join(parts) or None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Empty response from judge.")
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        lines = cleaned.splitlines()
        if lines and lines[0].strip().lower() == "json":
            lines = lines[1:]
        cleaned = "\n".join(lines)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Could not locate JSON object in judge response.")
    json_text = cleaned[start : end + 1]
    parsed = json.loads(json_text)
    if not isinstance(parsed, dict):
        raise ValueError("Judge response must be a JSON object.")
    return parsed


def _normalise_score(value: Any) -> float:
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise LLMJudgeError("Score value is empty.")
        if stripped.endswith("%"):
            stripped = stripped[:-1]
            numeric = float(stripped) / 100.0
        else:
            numeric = float(stripped)
    else:
        raise LLMJudgeError("Score value must be numeric.")

    if numeric > 1.0:
        if numeric <= 100.0:
            numeric = numeric / 100.0
        else:
            raise LLMJudgeError("Score value is outside the expected range.")
    if numeric < 0:
        raise LLMJudgeError("Score cannot be negative.")
    return min(numeric, 1.0)


def _interpret_label(label: str | None, score: float, threshold: float) -> bool:
    if isinstance(label, str):
        lowered = label.strip().lower()
        if lowered in {"pass", "yes", "true", "correct", "accepted", "good"}:
            return True
        if lowered in {"fail", "no", "false", "incorrect", "rejected", "bad"}:
            return False
    return score >= threshold


def run_llm_judge_job(samples: Sequence[EvaluationSample], judge: LLMJudge) -> JudgeJobReport:
    """Execute the judge over a batch of samples."""

    results: list[EvaluationResult] = []
    for sample in samples:
        decision = judge.evaluate(sample)
        results.append(EvaluationResult(sample=sample, decision=decision))
    return JudgeJobReport(results)


def load_samples(path: Path) -> list[EvaluationSample]:
    """Load evaluation samples from JSON or JSON Lines files."""

    if not path.exists():
        raise FileNotFoundError(f"Sample file not found: {path}")
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    records: list[dict[str, Any]]

    if suffix in {".jsonl", ".ndjson"}:
        records = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError("Each JSONL line must be an object.")
            records.append(payload)
    else:
        payload = json.loads(content)
        if isinstance(payload, dict):
            if "samples" in payload and isinstance(payload["samples"], list):
                records = list(payload["samples"])
            elif "data" in payload and isinstance(payload["data"], list):
                records = list(payload["data"])
            else:
                raise ValueError("JSON file must contain a list of samples.")
        elif isinstance(payload, list):
            records = list(payload)
        else:
            raise ValueError("Unsupported JSON structure for samples.")

    return [EvaluationSample.from_dict(item) for item in records]


def dump_report(report: JudgeJobReport, path: Path) -> None:
    """Persist evaluation results to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open("w", encoding="utf-8") as stream:
            for record in report.to_records():
                stream.write(json.dumps(record, ensure_ascii=False))
                stream.write("\n")
        return

    payload = {
        "summary": report.to_summary(),
        "results": report.to_records(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_openai_callable(model: str, *, temperature: float = 0.0) -> Callable[[str], str]:
    """Create a callable that queries the OpenAI Responses API."""

    try:
        from openai import OpenAI  # type: ignore import-not-found
    except ModuleNotFoundError as exc:  # pragma: no cover - handled in tests
        raise LLMJudgeError("The 'openai' package is required to call the OpenAI judge.") from exc

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMJudgeError("OPENAI_API_KEY environment variable is required for OpenAI judge calls.")

    client = OpenAI(api_key=api_key)

    def _invoke(prompt: str) -> str:
        response = client.responses.create(
            model=model,
            temperature=temperature,
            input=[{"role": "user", "content": prompt}],
        )
        return response.output_text

    return _invoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the LLM-as-a-judge evaluation job over stored RAG answers.",
    )
    parser.add_argument("--input", required=True, help="Path to a JSON or JSONL file with evaluation samples.")
    parser.add_argument("--output", help="Optional path to save the detailed evaluation report.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.65,
        help="Passing threshold applied to judge scores (default: 0.65).",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_JUDGE_MODEL", "gpt-4o-mini"),
        help="OpenAI model identifier used for judging (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for the judge model (default: 0.0).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip external LLM calls and assume every answer passes with score 1.0.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    samples = load_samples(Path(args.input))
    if not samples:
        parser.error("No samples available for evaluation.")

    if args.dry_run:
        def _dry_run_callable(_: str) -> str:
            return json.dumps({"score": 1.0, "verdict": "pass", "rationale": "Dry run placeholder."})

        llm_callable = _dry_run_callable
    else:
        llm_callable = create_openai_callable(args.model, temperature=args.temperature)

    judge = LLMJudge(llm_callable, passing_threshold=args.threshold)
    report = run_llm_judge_job(samples, judge)

    summary = report.to_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.output:
        dump_report(report, Path(args.output))

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
