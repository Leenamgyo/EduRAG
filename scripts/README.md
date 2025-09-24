# Server run scripts

다음 스크립트는 프로젝트의 각 서버를 실행하기 위한 기본 명령어를 래핑합니다.

- `run_qdrant.sh`: `docker compose up -d qdrant`
- `run_elasticsearch.sh`: `docker compose up -d elasticsearch`
- `run_ai_search_backend.sh`: `uv run uvicorn ai_search.service.api:app --host 0.0.0.0 --port 8000`
- `run_ai_search_web.sh`: `uv run streamlit run ai_search_web/app.py`

필요에 따라 추가 인수나 환경 변수를 지정해 실행할 수 있습니다.
