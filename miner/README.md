# Miner

Miner는 RAG(Retrieval-Augmented Generation) 저장소를 생성하기 위한 실험용 프로젝트입니다. `uv`로 관리되는 Python 패키지로 시작되었으며, 앞으로 데이터 수집과 인덱싱, 프롬프트 템플릿 등을 구성하는 기능을 추가해 나갈 예정입니다.

## 요구 사항
- [uv](https://github.com/astral-sh/uv) 0.5.0 이상
- Python 3.11 이상
- [Docker](https://www.docker.com/) 및 Docker Compose

## 시작하기
```bash
# 저장소 루트에서 의존성 설치 후 실행
uv run python -m miner.main --help
```

> 기본적으로 Miner CLI는 디버그 로그를 활성화합니다. `--no-debug` 옵션이나
> `MINER_DEBUG=0` 환경 변수를 사용하면 비활성화할 수 있습니다.

## Minor Search와의 연동

웹 검색 및 크롤링 파이프라인은 별도 프로젝트인 [Minor Search](../minor_search/README.md)로
분리되었습니다. Minor Search는 Tavily + Gemini 조합으로 수집한 결과를 자동으로
MinIO에 업로드하며, Miner 에이전트는 해당 객체를 불러와 임베딩 후 Qdrant에 저장합니다.

1. Minor Search 실행 후 출력에 표시된 `s3://버킷/객체` 값을 확인합니다.
2. Miner 에이전트를 실행할 때 `--search-object` 옵션으로 해당 객체 키를 전달합니다.

## Qdrant 벡터 DB 실행하기
Miner는 [Qdrant](https://qdrant.tech/)를 기본 벡터 데이터베이스로 사용합니다. 저장소 루트에 있는 `docker-compose.yml`을 사용하여 손쉽게 로컬 개발용 인스턴스를 실행할 수 있습니다.

```bash
# Qdrant 컨테이너 실행
docker compose up -d qdrant

# 컨테이너 종료
docker compose down
```

## 벡터 컬렉션 초기화
벡터 데이터베이스가 실행 중이라면 다음 명령으로 기본 컬렉션을 생성하거나 존재 여부를 확인할 수 있습니다.

```bash
uv run python -m miner.main \
  --collection miner-documents \
  --vector-size 1536 \
  --distance cosine
```

환경 변수 `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY`를 사용하여 접속 정보를 구성할 수 있으며, `MINER_COLLECTION`, `MINER_VECTOR_SIZE`, `MINER_DISTANCE` 값으로 기본 설정을 재정의할 수 있습니다.


Minor Search CLI에서 사용할 수 있는 세부 옵션과 예시는 해당 프로젝트의 README를 참고하세요.

### Gemini Agent 모드로 자동 수집

`--mode agent` 는 MinIO에 저장된 Minor Search 결과(JSON)를 불러와 임베딩을 생성하고 Qdrant에 저장합니다.

```bash
export TAVILY_API_KEY=...
export GEMINI_API_KEY=...

uv run python -m miner.main \
  --mode agent \
  --search-object search-results/스마트러닝-정책-동향-<UUID>.json \
  --agent-embedding-model models/text-embedding-004 \
  --agent-embedding-model-secondary models/text-embedding-003 \
  --collection edu-agent \
  --distance cosine
```

MinIO 연결 정보는 `MINOR_SEARCH_MINIO_*` 환경 변수 또는 CLI 옵션 (`--minio-endpoint`,
`--minio-access-key`, `--minio-secret-key`, `--minio-bucket`, `--minio-region`,
`--minio-secure`)으로 지정할 수 있습니다. Gemini 임베딩을 두 개 지정하면 Qdrant 컬렉션에
`primary`, `secondary` 벡터가 함께 저장됩니다. 초기 실행 시 컬렉션이 없으면 첫 실행에서
벡터 크기에 맞춰 자동 생성되며, 이미 존재하는 컬렉션과 벡터 크기가 다르면 에러가 발생합니다.
각 청크는 `doc_id`, `content`, `url`, `title`, `chunk_index`, `search_query`, `base_query`
메타데이터와 사용한 임베딩 모델 목록을 포함합니다.

에이전트가 수집한 청크는 `miner.docmodel.DocModel` 또는 `DocModel.to_document()` 를 통해 LangChain `Document` 객체로 변환해 추가 파이프라인에 활용할 수 있습니다.


## Postgres 실행 기록 저장하기

`MINER_DATABASE_URL` 환경 변수를 설정하면 Miner가 검색/에이전트 실행 기록과 크롤링된 청크 내용을 PostgreSQL에 자동으로 저장합니다.
`psycopg` 드라이버가 사용되므로 표준 DSN 형식을 그대로 지정할 수 있습니다.

```bash
export MINER_DATABASE_URL="postgresql://user:password@localhost:5432/miner"
```

실행 시 생성되는 테이블은 다음과 같습니다.

- `miner_runs`: 실행 모드, 기준 질의, 생성된 연관 질의, 실패 내역, 저장된 청크 수 등을 포함한 요약 정보.
- `miner_crawled_chunks`: 각 실행에서 수집된 청크의 URL, 제목, 인덱스, 본문 내용을 저장.

CLI 출력에는 저장이 성공했을 경우 실행 ID가 함께 노출되며, 해당 ID는 `miner_runs.id`와 동일합니다.
