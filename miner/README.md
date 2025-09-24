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
