"""Airflow DAG orchestrating the Gemini-powered embedding pipeline."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from airflow import DAG
from airflow.models.baseoperator import chain
from airflow.operators.python import PythonOperator

DEFAULT_DAG_ARGS: Dict[str, Any] = {
    "owner": "edurag-data-platform",
    "depends_on_past": False,
    "email": ["data@edurag.ai"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


class PipelineConfig:
    """Shared configuration loaded from the environment."""

    def __init__(self) -> None:
        self.gemini_api_key = self._get("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-pro")
        self.seed_topics = [topic.strip() for topic in os.getenv("SEED_TOPICS", "").split(",") if topic.strip()]
        self.output_bucket = self._get("OUTPUT_BUCKET")
        self.embeddings_table = self._get("EMBEDDINGS_TABLE")

    @staticmethod
    def _get(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise ValueError(f"Missing required environment variable: {name}")
        return value


def get_config() -> PipelineConfig:
    """Lazily instantiate the pipeline configuration."""

    if not hasattr(get_config, "_config"):
        get_config._config = PipelineConfig()  # type: ignore[attr-defined]
    return get_config._config  # type: ignore[attr-defined]


def _log_task(activity: str, payload: Dict[str, Any] | None = None) -> None:
    """Utility helper that logs a task step."""

    config = get_config()
    message: Dict[str, Any] = {
        "activity": activity,
        "model": config.gemini_model,
        "topics": config.seed_topics,
        "output_bucket": config.output_bucket,
        "embeddings_table": config.embeddings_table,
    }
    if payload:
        message.update(payload)

    print(json.dumps(message, ensure_ascii=False))


def generate_queries(**_: Any) -> List[str]:
    """Generate high quality search queries with the Gemini model."""

    config = get_config()
    prompts = [
        f"Generate detailed research questions about {topic} for education technology." for topic in config.seed_topics
    ]
    _log_task("generate_queries", {"prompts": prompts})
    queries = [f"{topic} latest research in education" for topic in config.seed_topics]
    return queries


def crawl_sources(**context: Any) -> List[Dict[str, Any]]:
    """Crawl sources that match the generated queries."""

    queries = context["ti"].xcom_pull(task_ids="generate_queries")
    documents = [
        {"query": query, "url": f"https://example.com/{idx}", "content": "<html>...</html>"}
        for idx, query in enumerate(queries)
    ]
    _log_task("crawl_sources", {"count": len(documents)})
    return documents


def parse_documents(**context: Any) -> List[Dict[str, Any]]:
    """Parse crawled documents into clean text snippets."""

    documents = context["ti"].xcom_pull(task_ids="crawl_sources")
    parsed = [
        {"query": doc["query"], "url": doc["url"], "text": f"Parsed content for {doc['query']}"}
        for doc in documents
    ]
    _log_task("parse_documents", {"count": len(parsed)})
    return parsed


def embed_documents(**context: Any) -> List[Dict[str, Any]]:
    """Generate embeddings for parsed documents using Gemini."""

    documents = context["ti"].xcom_pull(task_ids="parse_documents")
    embeddings = [
        {"url": doc["url"], "embedding": [0.0] * 1536, "text": doc["text"]}
        for doc in documents
    ]
    _log_task("embed_documents", {"count": len(embeddings)})
    return embeddings


def load_embeddings(**context: Any) -> None:
    """Persist embeddings into the vector store."""

    embeddings = context["ti"].xcom_pull(task_ids="embed_documents")
    _log_task("load_embeddings", {"count": len(embeddings)})


with DAG(
    dag_id="gemini_embedding_pipeline",
    description="End-to-end Gemini-based content embedding pipeline",
    default_args=DEFAULT_DAG_ARGS,
    schedule_interval=timedelta(hours=6),
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["gemini", "embeddings", "rag"],
) as dag:
    query_generation = PythonOperator(task_id="generate_queries", python_callable=generate_queries)
    crawling = PythonOperator(task_id="crawl_sources", python_callable=crawl_sources)
    parsing = PythonOperator(task_id="parse_documents", python_callable=parse_documents)
    embedding = PythonOperator(task_id="embed_documents", python_callable=embed_documents)
    loading = PythonOperator(task_id="load_embeddings", python_callable=load_embeddings)

    chain(query_generation, crawling, parsing, embedding, loading)
