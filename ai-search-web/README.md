# ai-search-web

Streamlit 기반의 리포트 뷰어이자 생성 UI입니다. Elasticsearch에 저장된 `ai-search` 분석 리포트를 탐색하고, 필요 시 백엔드 API를 호출해 새 보고서를 생성할 수 있습니다.

## 준비 사항

필요한 환경 변수:

- `ES_HOST`: Elasticsearch 엔드포인트(예: `http://localhost:9200`).
- `ES_USERNAME`, `ES_PASSWORD`: 보안이 활성화된 경우 인증 정보.
- `ES_INDEX`: 리포트를 저장한 인덱스 이름(기본값 `ai-search-reports`).
- `AI_SEARCH_API`: 보고서 생성을 담당하는 백엔드 서비스 주소. 지정하지 않으면 조회 기능만 동작합니다.
- `ES_PAGE_SIZE`: 조회할 최대 문서 수(선택, 기본 200).

`.env` 파일을 사용해도 되고, 실행 전에 환경 변수로 지정해도 됩니다.

## 실행 방법

```bash
cd ai-search-web
uv run streamlit run ai_search_web/app.py
```

실행 후 브라우저에서 사이드바를 통해 저장된 보고서를 탐색하고, 상단 폼을 이용해 새로운 분석 요청을 전달할 수 있습니다.
