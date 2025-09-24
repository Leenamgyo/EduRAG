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

### Tavily 기반 검색 모드 활용하기

AI-SEARCH 프로젝트에서 사용하던 다국어 Tavily 검색 전략을 Miner에도 도입했습니다.
`--mode search`와 `--search-query` 옵션을 사용하면 교육·학술 분야에 특화된 웹 검색을
실행해 수집할 만한 문서를 빠르게 파악할 수 있습니다. 검색 결과는 중복 URL을 제거한
마크다운 형식으로 출력됩니다.

```bash
export TAVILY_API_KEY=...  # Tavily API 키 필요

uv run python -m miner.main \
  --mode search \
  --search-query "디지털 교육 정책 동향"
```

검색 모드는 Tavily API 사용량에 따라 비용이 발생할 수 있으며, `deep-translator`
패키지가 설치되어 있다면 쿼리를 영어로 번역해 글로벌 검색도 함께 수행합니다.

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

### AI ?? ??? ?? ???

Miner ?? ??? ?? Tavily ?? ??? ??? AI? ?? ???? ???? ?? ??? ???? ??????.
?? ???? ?? ??? ??? ? ????.

- `--search-related-limit`: ??? ??? ?? ??? ?? (?? 5?).
- `--search-crawl-limit`: ???? URL ?? ?? (?? 5?).
- `--search-results-per-query`: ? ???? ??? ?? ?? ?? (?? 5?).

```bash
uv run python -m miner.main   --mode search   --search-query "?? ??? ????"   --search-related-limit 3   --search-crawl-limit 6
```

?? ?? ???? AI? ??? ?? ???? ???? ?? ??? ?? ???? ?? ??? ??? ?? ??????.
Gemini ?? ?? ??? ??? ????? `GEMINI_API_KEY` ?? ??? ???? ???. ??? ????? `gemini-1.5-flash`?? `--search-ai-model` ?? `MINER_SEARCH_AI_MODEL` ??? ??? ? ????.
???? ??? ????? 500? ??? ???? `--search-chunk-size` ?? `MINER_SEARCH_CHUNK_SIZE` ?? ??? ??? ??? ? ????.

### Gemini Agent 모드로 자동 수집

`--mode agent` 를 사용하면 Gemini 에이전트가 기준 질의와 연관 질의를 생성하고 Tavily 검색 → 크롤링 → 500자 청킹 → 임베딩 → Qdrant 저장까지 자동으로 수행합니다.

```bash
export TAVILY_API_KEY=...
export GEMINI_API_KEY=...

uv run python -m miner.main \
  --mode agent \
  --search-query "스마트러닝 정책 동향" \
  --search-related-limit 4 \
  --search-crawl-limit 8 \
  --search-results-per-query 5 \
  --agent-embedding-model models/text-embedding-004 \
  --agent-embedding-model-secondary models/text-embedding-003 \
  --collection edu-agent \
  --distance cosine
```

Gemini 임베딩을 두 개 지정하면 Qdrant 컬렉션에 `primary`, `secondary` 벡터가 함께 저장됩니다. 초기 실행 시 컬렉션이 없으면 첫 실행에서 벡터 크기에 맞춰 자동 생성되며, 이미 존재하는 컬렉션과 벡터 크기가 다르면 에러가 발생합니다. 각 청크는 `doc_id`, `content`, `url`, `title`, `chunk_index`, `search_query`, `base_query` 메타데이터와 사용한 임베딩 모델 목록을 포함합니다.

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
