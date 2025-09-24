# Miner

Miner는 RAG(Retrieval-Augmented Generation) 저장소를 생성하기 위한 실험용 프로젝트입니다. `uv`로 관리되는 Python 패키지로 시작되었으며, 앞으로 데이터 수집과 인덱싱, 프롬프트 템플릿 등을 구성하는 기능을 추가해 나갈 예정입니다.

## 요구 사항
- [uv](https://github.com/astral-sh/uv) 0.5.0 이상
- Python 3.11 이상

## 시작하기
```bash
# 저장소 루트에서 의존성 설치 후 실행
uv run python miner/main.py
```

현재는 초기화 메시지를 출력하는 간단한 스켈레톤 상태이며, 추후 RAG 파이프라인을 구성하는 명령형 도구로 확장될 예정입니다.
