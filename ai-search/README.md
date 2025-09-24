# EduRAG AI Search

EduRAG AI Search는 Gemini 기반의 학술 탐색 에이전트를 제공하는 도구 모음입니다. LangChain과 다양한 학술 검색 API를 결합하여 질문에 대한 조사 계획을 세우고, 검색 결과를 수집·정리하며, Markdown 혹은 텍스트 보고서를 자동으로 생성합니다. CLI와 Streamlit 기반 웹 뷰어를 모두 제공하므로, 콘솔에서 에이전트를 실행하거나 이미 생성된 보고서를 시각적으로 탐색할 수 있습니다.

## 주요 기능

- **계획형 분석 에이전트**: Google Gemini 모델을 사용해 질문을 분석하고 단계별 실행 계획을 세운 뒤, 각 단계에 맞는 답변을 생성합니다.
- **다중 검색 도구 통합**: Tavily, Semantic Scholar, CrossRef, OpenAlex 검색을 순차적으로 호출해 참고 자료를 수집합니다.
- **자동 보고서 저장**: 질의와 최종 분석 결과를 Markdown(`reports/*.md`) 또는 일반 텍스트(`reports/*.txt`) 파일로 보존합니다.
- **보고서 대시보드**: Streamlit 앱에서 저장된 보고서를 목록으로 확인하고, 본문을 LaTeX 수식과 함께 렌더링합니다.

## 설치 방법

프로젝트는 Python 3.13 이상을 요구합니다. [uv](https://github.com/astral-sh/uv) 또는 표준 가상 환경을 사용해 의존성을 설치할 수 있습니다.

```bash
# uv 사용 시
uv venv
uv pip install -e .

# 또는 표준 가상 환경과 pip 사용 시
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 환경 변수 설정

에이전트는 여러 외부 API 키를 필요로 합니다. `.env` 파일을 프로젝트 루트(예: `ai-search/.env`)에 생성하거나, 환경 변수로 직접 지정해 주세요.

| 환경 변수        | 설명 | 필수 여부 |
|------------------|------|-----------|
| `GOOGLE_API_KEY` | Gemini 모델 호출에 사용되는 Google Generative AI 키입니다. `GENAI_API_KEY`로도 인식합니다. | ✅ |
| `OPENAI_API_KEY` | OpenAI 도구를 사용할 경우에 필요합니다. | ⛏️ (선택) |
| `TAVILY_API_KEY` | Tavily 웹 검색 도구에 필요합니다. | ⛏️ (선택) |
| `GEMINI_MODEL`   | 사용할 Gemini 모델 이름입니다. 미지정 시 `gemini-2.0-flash-thinking-exp`가 기본값입니다. | ⛏️ (선택) |
| `REPORTS_DIR`    | 보고서를 저장할 디렉터리 경로입니다. 기본값은 `reports/` 입니다. | ⛏️ (선택) |

> ℹ️ `.env` 파일이 존재하면 자동으로 로드됩니다.

## 사용 방법

### 1. CLI에서 에이전트 실행

```bash
python -m ai_search.main --report-format md
```

- 실행 후 질의를 입력하면 단계별 분석 계획과 각 단계의 결과, 최종 답변이 출력됩니다.
- `--report-format`으로 `md` 또는 `txt`를 선택할 수 있으며, 각 실행마다 고유한 파일명이 생성됩니다.
- `--debug` 옵션을 추가하면 LangChain의 디버그 로그를 활성화합니다.

### 2. Streamlit 보고서 뷰어 실행

CLI로 생성된 보고서를 웹에서 탐색하고 싶다면 Streamlit 앱을 실행하세요.

```bash
streamlit run ai_search/web/app.py
```

- 사이드바에서 보고서를 선택하면 질문과 생성 시각, 본문 내용을 확인할 수 있습니다.
- 보고서에 포함된 LaTeX 수식은 자동으로 변환되어 표시됩니다.

## 프로젝트 구조

```
ai_search/
├── agents/        # Gemini 기반 플래너 및 분석 에이전트 체인
├── cli/           # CLI 진입점과 실행 루프
├── config/        # 환경 변수 로딩 및 설정
├── core/          # 분석 계획 파서 등 핵심 유틸리티
├── storage/       # 보고서 저장 로직
├── tools/         # Tavily, Semantic Scholar, CrossRef, OpenAlex 도구
└── web/           # Streamlit 기반 보고서 뷰어
```

## 보고서 예시

기본 설정에서는 `reports/` 디렉터리에 다음과 같은 Markdown 형식의 파일이 생성됩니다.

```markdown
# (질문)

---

# 분석 결과

(에이전트가 작성한 최종 답변)
```

## 문제 해결

- `GOOGLE_API_KEY environment variable is not set.` 오류가 발생하면 Google API 키가 누락된 것입니다.
- 보고서가 생성되지 않을 경우 `REPORTS_DIR` 경로의 쓰기 권한을 확인하세요.
- Streamlit 앱이 빈 목록을 표시한다면 아직 생성된 Markdown 보고서가 없는 것입니다.

## 라이선스

이 저장소의 라이선스 정보는 개별 폴더 또는 상위 프로젝트의 지침을 따릅니다.
