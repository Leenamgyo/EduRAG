"""Unit tests for the Gemini data pipeline scaffolding."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def load_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_query_generator_build_queries() -> None:
    module = load_module("query_generator", "docker/query-generator/main.py")
    topics = [" AI ", "RAG", ""]
    queries = module.build_queries(topics)
    assert queries == [
        "AI education research insights",
        "RAG education research insights",
    ]


def test_crawler_simulate_crawl() -> None:
    module = load_module("crawler", "docker/crawler/main.py")
    urls = module.build_search_urls(["rag pipeline"])
    documents = module.simulate_crawl(urls)
    assert documents[0]["url"].endswith("rag+pipeline")
    assert "Content for" in documents[0]["html"]


def test_parser_extract_text() -> None:
    module = load_module("parser", "docker/parser/main.py")
    html = "<html><body><h1>Title</h1><p>Paragraph</p></body></html>"
    text = module.extract_text(html)
    assert "Title" in text and "Paragraph" in text


def test_embedder_creates_deterministic_vectors() -> None:
    module = load_module("embedder", "docker/embedder/main.py")
    vector_one = module.embed_text("hello")
    vector_two = module.embed_text("hello")
    assert vector_one == vector_two
    assert len(vector_one) == module.EMBEDDING_DIMENSIONS


def test_loader_persist_records(tmp_path: Path) -> None:
    module = load_module("loader", "docker/loader/main.py")
    records = module.build_records([
        {"url": "https://example.com", "embedding": [0.1, 0.2], "text": "sample"}
    ], "dataset")
    output_file = tmp_path / "embeddings.json"
    module.persist_records(records, str(output_file))
    saved = json.loads(output_file.read_text(encoding="utf-8"))
    assert saved[0]["dataset"] == "dataset"


@pytest.mark.usefixtures("configure_pipeline_env")
def test_embedding_pipeline_dag_structure() -> None:
    pytest.importorskip("airflow")
    module = load_module("embedding_dag", "dags/embedding_pipeline_dag.py")
    dag = module.dag
    task_ids = [task.task_id for task in dag.tasks]
    assert task_ids == [
        "generate_queries",
        "crawl_sources",
        "parse_documents",
        "embed_documents",
        "load_embeddings",
    ]
    assert str(dag.schedule_interval) == "6:00:00"


@pytest.fixture()
def configure_pipeline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OUTPUT_BUCKET", "gs://bucket")
    monkeypatch.setenv("EMBEDDINGS_TABLE", "dataset")
    monkeypatch.setenv("SEED_TOPICS", "ai,education")
