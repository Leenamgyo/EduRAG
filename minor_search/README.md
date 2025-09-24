# Minor Search

Minor Search는 Tavily 검색과 Gemini 기반 관련 질의 생성을 조합해 교육·학습 도메인에 특화된 정보를 수집하는 프로젝트입니다. 실행 결과는 마크다운 요약과 함께 에이전트 친화적인 청크 리스트로 반환되며, MinIO에 저장해 Minor 에이전트에서 임베딩 파이프라인의 입력으로 사용할 수 있습니다.

## 크롤링 아키텍처

Minor Search의 수집기는 Scheduler-Queue-Master-Worker 패턴을 따르며, 확장성과 병렬성을 고려해 설계되었습니다.

1. **Scheduler**: 수집을 시작할 씨앗(Seed) URL 목록을 생성해 Job Queue에 등록합니다. 예약된 스케줄에 따라 자동 실행되거나 필요할 때 수동으로 기동합니다.
2. **Job Queue**: 크롤링해야 할 URL이 저장되는 중앙 대기열입니다. Redis의 `LIST` 구조나 AWS SQS로 구현할 수 있으며, Scheduler가 최초 URL을 넣고 Worker가 처리할 URL을 꺼내며, 처리 과정에서 발견한 신규 URL도 다시 큐에 추가합니다.
3. **Master**: Worker 상태와 Job Queue 적재량을 모니터링합니다. Worker가 정상 동작하는지 확인하고 큐 상태에 따라 Worker 수를 조절하는 자동 확장(Auto Scaling)을 담당합니다.
4. **Worker**: 실제 크롤링을 수행합니다. Job Queue에서 URL을 하나 꺼내 콘텐츠를 다운로드한 뒤, HTML은 파싱해 필요한 데이터와 추가 URL을 추출하고, PDF/이미지는 객체 저장소(S3/MinIO 등)에 업로드합니다. 추출한 텍스트 데이터는 최종 DB에 저장하며, 신규 URL은 다시 Job Queue에 넣습니다.

이 구조를 통해 Worker들은 Job Queue가 비어 있을 때까지 URL을 반복 처리하고, Master는 상황에 맞춰 Worker 수를 조정해 처리량을 유지합니다.

## 요구 사항
- [uv](https://github.com/astral-sh/uv) 0.5.0 이상
- Python 3.11 이상
- Tavily API 키 (`TAVILY_API_KEY`)
- 선택: Gemini API 키 (`GEMINI_API_KEY`) – 연관 질의 생성을 사용할 경우 필요
- 선택: MinIO 또는 S3 호환 객체 저장소

## 기본 사용법
```bash
uv run python -m minor_search.main "디지털 전환 교육 정책"
```

위 명령은 Tavily 검색과 크롤링을 실행한 뒤 결과를 마크다운으로 출력하고, 기본 설정에 따라 MinIO에 청크 데이터를 저장합니다. 저장된 객체 키는 마지막 줄에서 `s3://<bucket>/<object>` 형식으로 확인할 수 있습니다.

### 주요 옵션
- `--related-limit`: Gemini가 생성할 연관 질의 수 (기본값 5)
- `--crawl-limit`: 크롤링할 최대 URL 수 (기본값 5)
- `--results-per-query`: Tavily 결과 상위 N건을 유지 (기본값 5)
- `--chunk-size`: 크롤링 텍스트를 분할할 길이 (기본값 500)
- `--ai-model`: 연관 질의를 생성할 Gemini 모델 ID
- `--ai-prompt`: Gemini 연관 질의 생성 프롬프트 오버라이드
- `--no-store`: MinIO 업로드를 건너뜀
- `--object-name`: 업로드 시 사용할 사용자 지정 객체 이름

### MinIO 설정
다음 환경 변수 또는 CLI 옵션으로 MinIO 연결 정보를 구성할 수 있습니다.

- `MINOR_SEARCH_MINIO_ENDPOINT`
- `MINOR_SEARCH_MINIO_ACCESS_KEY`
- `MINOR_SEARCH_MINIO_SECRET_KEY`
- `MINOR_SEARCH_MINIO_BUCKET`
- `MINOR_SEARCH_MINIO_REGION`
- `MINOR_SEARCH_MINIO_SECURE` (1/true/on/y 값을 사용하면 HTTPS 활성화)

기본값은 `localhost:9000`, `minioadmin/minioadmin`, `minor-search` 버킷, HTTP 연결입니다.

### 결과 저장 구조
MinIO에 저장되는 객체는 JSON 포맷이며 다음 정보를 포함합니다.
- `base_query`: 기준 질의
- `related_queries`: 생성된 연관 질의 목록
- `chunks`: URL, 제목, 청크 본문 등 에이전트가 사용할 수 있는 데이터 목록
- `failures`: 크롤링 실패 내역

이 JSON은 Minor 프로젝트의 `minor.main --mode agent` 명령에서 `--search-object` 옵션으로 불러와 임베딩 파이프라인을 실행할 수 있습니다.

## 학술 논문 상위 인용 조회
Minor Search에는 주어진 키워드로 상위 인용 논문을 찾는 도구가 포함되어 있습니다. OpenAlex API를 먼저 호출하고, 가능한 경우 Semantic Scholar 결과로 인용 수를 검증합니다.

```bash
uv run python -m minor_search.top_cited "generative ai education" --limit 5
```

출력은 마크다운 표 형식으로 제공되며, 제목, 연도, 인용 수, DOI/URL 정보를 확인할 수 있습니다. `--no-verify` 옵션을 사용하면 Semantic Scholar 검증 단계를 생략합니다.

## 디버그 모드
기본적으로 Minor Search는 디버그 로그를 활성화합니다. `--no-debug` 옵션 또는 `MINOR_SEARCH_DEBUG=0` 환경 변수를 사용하여 비활성화할 수 있습니다.

## 실행 로그 연동
Minor Search에서 반환한 `SearchRunResult`는 `minor.logbook.log_search_run` 함수를 통해 JSON Lines 파일로 기록할 수 있습니다. `MINOR_LOG_PATH` 환경 변수를 사용하면 Minor와 동일한 경로를 공유하도록 설정할 수 있습니다.
