# ai-search-web

Streamlit 기반의 리포트 뷰어입니다. 'ai-search' 에이전트가 생성한 분석 리포트를 웹 브라우저에서 탐색할 수 있습니다.

## 실행 방법

```bash
cd ai-search-web
uv run streamlit run ai_search_web/app.py
```

기본적으로 ../ai-search/reports 경로를 바라봅니다. 다른 디렉터리를 사용하려면 REPORTS_DIR 환경 변수를 지정하세요.
