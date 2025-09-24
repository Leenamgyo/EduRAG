# ai-search-web

Streamlit 기반의 리포트 뷰어입니다. Elasticsearch에 저장된 'ai-search' 분석 리포트를 웹 브라우저에서 탐색할 수 있습니다.

## 실행 방법

```bash
cd ai-search-web
uv run streamlit run ai_search_web/app.py
```

기본적으로 Elasticsearch에 연결해 저장된 보고서를 조회합니다. 새 보고서를 생성하려면 `AI_SEARCH_API` 환경 변수에 백엔드(예: `ai-search`) 주소를 지정하세요. 값을 지정하지 않으면 조회 기능만 사용할 수 있습니다.
