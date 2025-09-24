# Minor Search

Minor Search는 Tavily 검색과 Gemini 기반 관련 질의 생성을 조합해 교육·학습 도메인에 특화된 정보를 수집하는 프로젝트입니다. 실행 결과는 마크다운 요약과 함께 에이전트 친화적인 청크 리스트로 반환되며, 필요에 따라 사용자 정의 핸들러를 통해 저장하거나 추가 파이프라인으로 전달할 수 있습니다.

## 크롤링 아키텍처

Minor Search의 수집기는 Scheduler-Queue-Master-Worker 패턴을 따르며, 확장성과 병렬성을 고려해 설계되었습니다. 수집 작업은 "프로젝트" 단위로 그룹화되며, 동일한 프로젝트에 속한 씨앗들은 공통 메타데이터와 기본 옵션을 공유합니다.

1. **Scheduler**: 수집을 시작할 씨앗(Seed) URL 목록을 생성해 Job Queue에 등록합니다. 프로젝트 정보를 함께 기록해 이후 결과 처리를 쉽게 합니다. 예약된 스케줄에 따라 자동 실행되거나 필요할 때 수동으로 기동합니다.
2. **Job Queue**: 크롤링해야 할 URL이 저장되는 중앙 대기열입니다. Redis의 `LIST` 구조나 AWS SQS로 구현할 수 있으며, Scheduler가 최초 URL을 넣고 Worker가 처리할 URL을 꺼내며, 처리 과정에서 발견한 신규 URL도 다시 큐에 추가합니다.
3. **Master**: Worker 상태와 Job Queue 적재량을 모니터링합니다. Worker가 정상 동작하는지 확인하고 큐 상태에 따라 Worker 수를 조절하는 자동 확장(Auto Scaling)을 담당합니다.
4. **Worker**: 실제 크롤링을 수행합니다. Job Queue에서 URL을 하나 꺼내 콘텐츠를 다운로드한 뒤, HTML은 파싱해 필요한 데이터와 추가 URL을 추출합니다. 추출한 텍스트 데이터와 파일은 호출자가 제공한 핸들러를 통해 원하는 저장소(DB, 데이터 레이크 등)로 보낼 수 있으며, 신규 URL은 다시 Job Queue에 넣습니다.

이 구조를 통해 Worker들은 Job Queue가 비어 있을 때까지 URL을 반복 처리하고, Master는 상황에 맞춰 Worker 수를 조정해 처리량을 유지합니다. 추후에는 Airflow 같은 오케스트레이션 도구와 결합해 프로젝트 단위 작업을 스케줄링할 수 있도록 설계되어 있습니다.

## 요구 사항
- [uv](https://github.com/astral-sh/uv) 0.5.0 이상
- Python 3.11 이상
- Tavily API 키 (`TAVILY_API_KEY`)
- 선택: Gemini API 키 (`GEMINI_API_KEY`) – 연관 질의 생성을 사용할 경우 필요


## 기본 사용법
```bash
uv run python -m minor_search.main "디지털 전환 교육 정책"
```

위 명령은 Tavily 검색과 크롤링을 실행한 뒤 결과를 마크다운으로 출력합니다. 추출된 청크 데이터는 호출 측에서 원하는 방식으로 저장하도록 결과 핸들러를 구현할 수 있습니다.

### 주요 옵션
- `--related-limit`: Gemini가 생성할 연관 질의 수 (기본값 5)
- `--crawl-limit`: 크롤링할 최대 URL 수 (기본값 5)
- `--results-per-query`: Tavily 결과 상위 N건을 유지 (기본값 5)
- `--chunk-size`: 크롤링 텍스트를 분할할 길이 (기본값 500)
- `--ai-model`: 연관 질의를 생성할 Gemini 모델 ID
- `--ai-prompt`: Gemini 연관 질의 생성 프롬프트 오버라이드

## 프로젝트 단위 실행

`minor_search.crawler` 모듈은 `CrawlProject`와 `CrawlJob` 클래스를 제공하여 동일한 주제를 다루는 씨앗들을 묶어 관리할 수 있도록 합니다. 프로젝트는 공통 메타데이터와 기본 검색 파라미터를 지정할 수 있으며, `Scheduler.schedule()`에 프로젝트를 전달하면 내부의 모든 씨앗이 한 번에 큐에 등록됩니다. 이렇게 생성된 메타데이터는 Worker가 생성하는 연관 질의에도 자동으로 전파되어 후속 파이프라인에서 프로젝트 단위 집계를 쉽게 만들 수 있습니다.

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
