# Week 6 — LLM API 연동 (docpilot에 `/chat` 붙이기)

> 이번 주 한 줄: 지금까지 만든 docpilot에 **진짜 LLM**을 연결해, 문서 도우미가 사람 말로 대답하게 만든다.
> docpilot 진화: `/chat` 엔드포인트 추가 — OpenAI(기본)/Gemini(대안) 호출 + **스트리밍 응답** + **시스템 프롬프트** 구성. (무료 대안 Ollama 스니펫 포함)

여기서부터 Block 2 (AI 서비스)가 시작된다. week01~05에서 만든 것은 "그릇"이었고, 이제부터 그 그릇에 지능을 담는다.

---

## 학습 목표

- [ ] LLM API의 동작 원리(인증 → 요청 → 응답, 토큰·비용, 스트리밍)를 설명할 수 있다.
- [ ] system / user / assistant 역할과 `temperature` 등 핵심 파라미터의 효과를 예를 들어 설명할 수 있다.
- [ ] API 키를 **환경변수**로 안전하게 로드한다(하드코딩 금지).
- [ ] docpilot에 `/chat` 엔드포인트를 추가해 OpenAI를 호출한다.
- [ ] `StreamingResponse`(SSE)로 토큰을 실시간으로 흘려보낸다.
- [ ] Gemini / Ollama로 **프로바이더를 교체**할 수 있는 구조를 만든다.

---

## 사전 준비

- 지난주(week05)까지의 docpilot 코드베이스(프로젝트 루트의 `main.py`·`db.py`).
  - 아직 없다면 [week01](./week01-오리엔테이션과-클라우드네이티브개론.md)~[week05](./week05-kubernetes-심화와-배포.md)를 먼저 완료할 것.

> **⚠️ 0단계 — 프로젝트 구조 전환 (이번 주 최초 1회만)**
>
> week05까지는 루트에 `main.py`·`db.py`를 두었다. week06부터 파일이 빠르게 늘어나므로(설정·LLM·RAG·에이전트) `app/` 패키지로 승격한다. **이 전환을 하지 않으면 이후 모든 주차의 `from app.xxx import ...`가 실패한다.**
>
> ```bash
> cd ~/projects/docpilot
> mkdir -p app && touch app/__init__.py
> git mv main.py app/main.py        # 루트 main.py → app/main.py
> git mv db.py app/db.py            # 루트 db.py → app/db.py
> # app/main.py 안의 `from db import ...` 를 `from app.db import ...` 로 수정
> sed -i 's/^from db import/from app.db import/' app/main.py
> ```
>
> Dockerfile도 `COPY main.py .` / `COPY db.py .` 두 줄을 `COPY app ./app` 한 줄로 바꾼다(최종 정리는 [week12](./week12-통합배포와-프로젝트킥오프.md)에서). CI 워크플로우가 있다면 트리거 `paths`도 `app/**` 로 맞춘다.
>
> **확인**: `uvicorn app.main:app --reload` 로 서버가 뜨고 다른 터미널에서 `curl -s localhost:8000/health` 가 `{"status":"ok"}`(week01 정의값)를 반환하면 전환 완료. 이제부터 실행 명령은 항상 `uvicorn app.main:app` 이다.
- Python 3.12, 가상환경(venv 또는 uv).
- **OpenAI API 키** 1개. ([platform.openai.com](https://platform.openai.com) → API keys → Create). 최초 가입 시 소액 크레딧이 있거나, 결제 수단 등록 후 소액($5) 충전이면 이 실습에 충분하다.
- (선택) **Gemini API 키**: [aistudio.google.com](https://aistudio.google.com) → Get API key (무료 티어 있음).
- (선택, 완전 무료) **Ollama**: 로컬에서 소형 모델 구동. [ollama.com](https://ollama.com).

> 계정·키 준비는 [../02-실습환경과-기술스택.md](../02-실습환경과-기술스택.md) 참고.

---

## 개념 (요약)

### 1) LLM API란 무엇인가

LLM(Large Language Model)은 "지금까지의 대화"를 입력받아 "다음에 올 말"을 확률적으로 이어 쓰는 모델이다. 우리는 이 모델을 직접 돌리지 않고, **HTTP API**로 호출한다.

```
[우리 서버(docpilot)]  --HTTPS 요청(messages + 파라미터)-->  [LLM 제공자]
                       <--응답(생성된 텍스트 + 사용 토큰)--
```

- **인증**: `Authorization: Bearer <API_KEY>` 헤더(또는 SDK가 대신 처리). 키는 곧 "돈"이므로 절대 코드/깃에 넣지 않는다.
- **요청**: 모델 이름 + `messages` 배열(역할별 메시지) + 파라미터(temperature 등).
- **응답**: 생성 텍스트 + `usage`(입력/출력 토큰 수).

### 2) 토큰과 비용

- **토큰**: 모델이 텍스트를 자르는 단위. 영어는 대략 1토큰 ≈ 4글자, 한국어는 글자당 토큰이 더 든다(경험적으로 한글 1글자 ≈ 1~2토큰).
- **비용**: 대부분 `(입력 토큰 수 × 입력 단가) + (출력 토큰 수 × 출력 단가)`. 모델마다 단가가 다르다(소형 모델이 훨씬 저렴).
- 실무 팁: **컨텍스트(입력)를 길게 넣을수록 매 호출 비용이 커진다.** RAG(week08)에서 "필요한 조각만 넣는" 이유가 여기에 있다.

### 3) 스트리밍(streaming)

- 기본 호출은 **완성된 답 전체**를 한 번에 받는다. 답이 길면 사용자는 몇 초간 빈 화면을 본다.
- 스트리밍은 모델이 토큰을 만들 때마다 **조각조각** 내려준다. ChatGPT가 글자를 타이핑하듯 보여주는 그것.
- 서버→브라우저 전달은 흔히 **SSE(Server-Sent Events)** 를 쓴다: `text/event-stream` 응답으로 `data: ...\n\n` 라인을 계속 흘려보낸다.

### 4) 프롬프트 엔지니어링 기초

`messages`는 **역할(role)** 을 가진 메시지의 배열이다.

| role | 의미 | 예 |
|---|---|---|
| `system` | 모델의 정체성·규칙·톤을 정한다. 대화 맨 앞 1개. | "너는 docpilot, 문서 기반 도우미다. 모르면 모른다고 답한다." |
| `user` | 사용자의 실제 입력. | "이 프로젝트 배포 방법 알려줘" |
| `assistant` | 모델의 이전 답변(대화 히스토리를 이어줄 때 넣는다). | (이전 응답) |

주요 파라미터:

| 파라미터 | 역할 | 감 잡기 |
|---|---|---|
| `temperature` | 무작위성/창의성. 0=결정적, 높을수록 다양. | 사실 답변 0~0.3, 브레인스토밍 0.7~1.0 |
| `max_tokens` | 출력 길이 상한. | 비용·응답시간 제어에 필수 |
| `top_p` | 누적확률 샘플링. temperature 대안. | 보통 temperature만 조절 |

핵심 원칙: **지시는 구체적으로, 형식은 명시적으로, 예시를 곁들이면 더 안정적.**

---

## 실습: 단계별 따라하기

이번 주 흐름(4교시 기준):
- **1부**: 패키지 설치 + 키를 환경변수로 안전하게 로드 + 최초 호출(스크립트).
- **2부**: docpilot에 `/chat` 엔드포인트(비스트리밍) 추가.
- **3부**: 스트리밍(`/chat/stream`) + 프로바이더 교체(Gemini/Ollama).

작업 디렉터리는 docpilot 프로젝트 루트라고 가정한다.

### 1부. 환경 준비

#### 1단계. 패키지 설치

무엇을/왜: LLM SDK와 설정/환경변수 로딩 도구를 설치한다.

```bash
# 가상환경이 활성화된 상태에서
pip install "openai>=1.40" "google-genai>=1.0" "pydantic-settings>=2.0" "python-dotenv>=1.0" "sse-starlette>=2.0"
```

`requirements.txt`에도 추가한다(컨테이너 재빌드 시 반영되도록).

```text
# requirements.txt (기존 항목 + 아래 추가)
openai>=1.40
google-genai>=1.0
pydantic-settings>=2.0
python-dotenv>=1.0
sse-starlette>=2.0
```

**확인**: 설치 로그 마지막에 `Successfully installed ... openai-1.xx.x ...`가 보이면 성공.

```bash
python -c "import openai, google.genai; print('sdk ok')"
```

**확인**: `sdk ok` 출력.

#### 2단계. API 키를 환경변수로 로드 (하드코딩 금지)

무엇을/왜: 키는 소스코드가 아니라 **환경**에 둔다. 로컬은 `.env` 파일, 배포는 K8s Secret(week05에서 배운 것)으로 주입한다.

프로젝트 루트에 `.env`를 만든다:

```bash
# .env  (절대 git에 커밋하지 말 것)
OPENAI_API_KEY=sk-...여기에_본인_키...
OPENAI_MODEL=gpt-4o-mini

# (선택) Gemini
GEMINI_API_KEY=...여기에_본인_키...
GEMINI_MODEL=gemini-2.0-flash

# 프로바이더 선택: openai | gemini | ollama
LLM_PROVIDER=openai

# (선택) Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

`.gitignore`에 `.env`가 있는지 반드시 확인한다:

```bash
grep -qxF ".env" .gitignore || echo ".env" >> .gitignore
cat .gitignore | grep .env
```

**확인**: 출력에 `.env`가 있으면 OK. (없으면 위 명령이 추가해 준다.)

이제 설정을 코드로 읽는 `app/config.py`를 만든다. `pydantic-settings`는 `.env`와 실제 환경변수를 자동으로 읽는다.

```python
# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM provider selection
    llm_provider: str = "openai"  # openai | gemini | ollama

    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Gemini
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # Ollama (local, free)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (read .env / env vars once)."""
    return Settings()
```

**확인**:

```bash
python -c "from app.config import get_settings; s=get_settings(); print('provider=', s.llm_provider, '| key set:', bool(s.openai_api_key))"
```

기대 출력: `provider= openai | key set: True` (키가 `.env`에 있으면 `True`).

#### 3단계. 최초 호출 — 스크립트로 손맛 보기

무엇을/왜: 엔드포인트를 붙이기 전에, SDK가 실제로 응답하는지 최소 스크립트로 확인한다.

```python
# scratch_openai.py  (실습용 임시 스크립트, 확인 후 삭제해도 됨)
from openai import OpenAI
from app.config import get_settings

settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)

resp = client.chat.completions.create(
    model=settings.openai_model,
    messages=[
        {"role": "system", "content": "You are docpilot, a concise document assistant. Answer in Korean."},
        {"role": "user", "content": "LLM API가 뭔지 한 문장으로 설명해줘."},
    ],
    temperature=0.3,
    max_tokens=200,
)

print("답변:", resp.choices[0].message.content)
print("토큰 usage:", resp.usage)  # prompt_tokens / completion_tokens / total_tokens
```

```bash
python scratch_openai.py
```

**확인**: 한국어 한 문장 답변과 함께 `토큰 usage: CompletionUsage(prompt_tokens=..., completion_tokens=..., total_tokens=...)`가 출력된다. → 인증·요청·응답·토큰을 눈으로 확인한 것.

> 에러가 난다면 아래 [트러블슈팅](#트러블슈팅)의 401/429 항목을 먼저 볼 것.

---

### 2부. docpilot에 `/chat` 붙이기

이제 LLM 호출 로직을 **재사용 가능한 모듈**로 분리하고, FastAPI 라우트로 노출한다. 프로바이더 교체가 쉽도록 얇은 추상화 계층을 둔다.

#### 4단계. LLM 클라이언트 모듈 (`app/llm.py`)

무엇을/왜: OpenAI/Gemini/Ollama를 하나의 인터페이스(`complete`, `stream`)로 감싼다. `/chat`은 이 모듈만 알면 된다(프로바이더 세부는 몰라도 됨).

```python
# app/llm.py
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
from openai import AsyncOpenAI
from google import genai
from google.genai import types as genai_types

from app.config import Settings, get_settings

# messages 형식: [{"role": "system"|"user"|"assistant", "content": "..."}]
Messages = list[dict[str, str]]

DEFAULT_SYSTEM_PROMPT = (
    "You are docpilot, a helpful document assistant for a cloud engineering course. "
    "Be concise and accurate. Answer in Korean unless the user writes in another language. "
    "If you are not sure, say you are not sure rather than guessing."
)


def build_messages(user_text: str, system: str | None = None, history: Messages | None = None) -> Messages:
    """system → (history) → user 순서로 messages 배열을 구성한다."""
    messages: Messages = [{"role": "system", "content": system or DEFAULT_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    return messages


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
async def _openai_complete(messages: Messages, settings: Settings, temperature: float) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


async def _openai_stream(messages: Messages, settings: Settings, temperature: float) -> AsyncIterator[str]:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    stream = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ---------------------------------------------------------------------------
# Gemini (google-genai SDK)
# ---------------------------------------------------------------------------
def _to_gemini(messages: Messages) -> tuple[str, list[genai_types.Content]]:
    """OpenAI 스타일 messages를 Gemini의 system_instruction + contents로 변환."""
    system = ""
    contents: list[genai_types.Content] = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
            continue
        role = "user" if m["role"] == "user" else "model"  # assistant -> model
        contents.append(genai_types.Content(role=role, parts=[genai_types.Part(text=m["content"])]))
    return system, contents


async def _gemini_complete(messages: Messages, settings: Settings, temperature: float) -> str:
    client = genai.Client(api_key=settings.gemini_api_key)
    system, contents = _to_gemini(messages)
    resp = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=genai_types.GenerateContentConfig(system_instruction=system, temperature=temperature),
    )
    return resp.text or ""


async def _gemini_stream(messages: Messages, settings: Settings, temperature: float) -> AsyncIterator[str]:
    client = genai.Client(api_key=settings.gemini_api_key)
    system, contents = _to_gemini(messages)
    stream = await client.aio.models.generate_content_stream(
        model=settings.gemini_model,
        contents=contents,
        config=genai_types.GenerateContentConfig(system_instruction=system, temperature=temperature),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text


# ---------------------------------------------------------------------------
# Ollama (local, free) — OpenAI 호환 X, 자체 /api/chat 사용
# ---------------------------------------------------------------------------
async def _ollama_complete(messages: Messages, settings: Settings, temperature: float) -> str:
    async with httpx.AsyncClient(base_url=settings.ollama_host, timeout=120) as client:
        r = await client.post(
            "/api/chat",
            json={"model": settings.ollama_model, "messages": messages,
                  "stream": False, "options": {"temperature": temperature}},
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


async def _ollama_stream(messages: Messages, settings: Settings, temperature: float) -> AsyncIterator[str]:
    async with httpx.AsyncClient(base_url=settings.ollama_host, timeout=120) as client:
        async with client.stream(
            "POST", "/api/chat",
            json={"model": settings.ollama_model, "messages": messages,
                  "stream": True, "options": {"temperature": temperature}},
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                piece = data.get("message", {}).get("content", "")
                if piece:
                    yield piece


# ---------------------------------------------------------------------------
# Public API — 프로바이더 디스패치
# ---------------------------------------------------------------------------
async def complete(messages: Messages, temperature: float = 0.3) -> str:
    settings = get_settings()
    if settings.llm_provider == "openai":
        return await _openai_complete(messages, settings, temperature)
    if settings.llm_provider == "gemini":
        return await _gemini_complete(messages, settings, temperature)
    if settings.llm_provider == "ollama":
        return await _ollama_complete(messages, settings, temperature)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")


async def stream(messages: Messages, temperature: float = 0.3) -> AsyncIterator[str]:
    settings = get_settings()
    if settings.llm_provider == "openai":
        gen = _openai_stream(messages, settings, temperature)
    elif settings.llm_provider == "gemini":
        gen = _gemini_stream(messages, settings, temperature)
    elif settings.llm_provider == "ollama":
        gen = _ollama_stream(messages, settings, temperature)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
    async for piece in gen:
        yield piece
```

**확인**: 파일 저장 후 import 에러가 없는지 본다.

```bash
python -c "import app.llm; print('llm module ok')"
```

기대 출력: `llm module ok`.

#### 5단계. `/chat` 라우트 (비스트리밍) 추가

무엇을/왜: 먼저 **한 번에 답 받는** 단순 버전으로 파이프라인이 도는지 확인한다. 요청 본문은 Pydantic으로 검증(입력 검증은 시스템 경계에서 필수).

`app/main.py`에 다음을 추가한다(기존 `app = FastAPI(...)` 아래).

```python
# app/main.py  (기존 import 아래에 추가)
from pydantic import BaseModel, Field

from app import llm


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="사용자 질문")
    system: str | None = Field(default=None, description="시스템 프롬프트 재정의(선택)")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    reply: str
    provider: str


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """문서 도우미에게 한 번에 답을 받는다(비스트리밍)."""
    from app.config import get_settings

    messages = llm.build_messages(req.message, system=req.system)
    reply = await llm.complete(messages, temperature=req.temperature)
    return ChatResponse(reply=reply, provider=get_settings().llm_provider)
```

> `app/main.py`에 이미 `from fastapi import FastAPI`와 `app = FastAPI(...)`가 있다고 가정한다. 없으면 week01 산출물을 확인.

서버를 켠다:

```bash
uvicorn app.main:app --reload
```

다른 터미널에서 호출:

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "docpilot이 뭐 하는 서비스인지 두 문장으로 설명해줘.", "temperature": 0.2}' | python -m json.tool
```

**확인**: 아래와 비슷한 JSON.

```json
{
    "reply": "docpilot은 문서를 올리면 그 내용을 바탕으로 질문에 답해 주는 AI 도우미입니다. ...",
    "provider": "openai"
}
```

브라우저에서 `http://localhost:8000/docs`를 열면 `/chat`이 Swagger UI에 나타난다. **확인**: "Try it out"으로도 같은 응답을 받을 수 있다.

---

### 3부. 스트리밍 + 프로바이더 교체

#### 6단계. 스트리밍 엔드포인트 (`/chat/stream`, SSE)

무엇을/왜: 답이 길어도 사용자가 즉시 첫 글자를 보게 한다. `StreamingResponse`로 `text/event-stream`을 내려보낸다.

`app/main.py`에 추가:

```python
# app/main.py  (추가)
from fastapi.responses import StreamingResponse


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """토큰을 SSE(data: ...)로 실시간 전송한다."""
    messages = llm.build_messages(req.message, system=req.system)

    async def event_generator():
        try:
            async for piece in llm.stream(messages, temperature=req.temperature):
                # SSE 프레임: 'data: <내용>\n\n'
                yield f"data: {piece}\n\n"
        except Exception as exc:  # noqa: BLE001 - 스트림 도중 에러도 클라이언트에 전달
            yield f"event: error\ndata: {exc}\n\n"
        finally:
            yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

> 주의: SSE는 데이터에 줄바꿈(`\n`)이 있으면 프레임이 깨진다. 여기서는 토큰 조각이 대개 짧아 실습에는 충분하지만, 프로덕션에서는 각 조각을 `json.dumps`로 감싸 보내는 것이 안전하다(과제 참고). `sse-starlette`의 `EventSourceResponse`를 쓰면 이 처리를 자동화할 수 있다.

`curl`로 스트리밍을 눈으로 확인한다(`-N`은 버퍼링 없이 즉시 출력):

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "클라우드 네이티브의 핵심 개념 3가지를 설명해줘."}'
```

**확인**: `data: 클`, `data: 라`, `data: 우드` ... 처럼 조각이 **연달아** 찍히고 마지막에 `event: done` / `data: [DONE]`이 나온다. 완성본을 한 번에 받는 게 아니라 흘러 내려오면 성공.

#### 7단계. 브라우저에서 스트리밍 받아보기 (선택, 프론트 확인)

무엇을/왜: SSE를 실제 웹에서 소비하는 최소 예제. `fetch` 스트림을 읽어 한 글자씩 그린다.

`static/chat.html` (프로젝트에 `static/` 디렉터리를 두고 FastAPI에 mount했다면):

```html
<!doctype html>
<meta charset="utf-8" />
<h3>docpilot chat (streaming)</h3>
<input id="q" size="60" value="RAG가 뭔지 쉽게 설명해줘" />
<button onclick="ask()">보내기</button>
<pre id="out" style="white-space:pre-wrap"></pre>
<script>
async function ask() {
  const out = document.getElementById("out");
  out.textContent = "";
  const res = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: document.getElementById("q").value }),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    // 'data: ...' 라인만 추려서 붙인다
    decoder.decode(value).split("\n").forEach((line) => {
      if (line.startsWith("data: ")) {
        const text = line.slice(6);
        if (text !== "[DONE]") out.textContent += text;
      }
    });
  }
}
</script>
```

정적 파일 마운트가 없다면 `app/main.py`에 한 줄 추가:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")
```

**확인**: `http://localhost:8000/static/chat.html`에서 "보내기"를 누르면 답변이 타이핑되듯 그려진다.

#### 8단계. 프로바이더 교체 — Gemini

무엇을/왜: 코드는 그대로 두고 **환경변수만** 바꿔 다른 회사 모델로 전환한다(추상화의 이점).

`.env`에서:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=...본인_키...
GEMINI_MODEL=gemini-2.0-flash
```

서버 재시작 후 동일하게 호출:

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕? 너 지금 어떤 모델이야?"}' | python -m json.tool
```

**확인**: 응답 JSON의 `"provider": "gemini"`. `/chat`, `/chat/stream` 둘 다 코드 변경 없이 동작한다.

#### 9단계. 완전 무료 대안 — Ollama (로컬)

무엇을/왜: API 키·비용 없이 노트북에서 소형 모델로 개발/테스트하고 싶을 때. 크레딧이 떨어져도 실습을 이어갈 수 있다.

```bash
# 1) 설치: https://ollama.com 에서 OS별 설치 (또는 아래)
curl -fsSL https://ollama.com/install.sh | sh

# 2) 소형 모델 받기 (약 2GB)
ollama pull llama3.2

# 3) 데몬은 보통 자동 실행. 수동 실행이 필요하면:
#    ollama serve
# 4) 동작 확인
ollama run llama3.2 "say hello in korean"
```

`.env`:

```bash
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

서버 재시작 후:

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "docker와 kubernetes 차이를 두 문장으로."}'
```

**확인**: (첫 호출은 모델 로딩으로 몇 초 지연될 수 있음) 로컬 모델이 스트리밍으로 답한다. 인터넷/키 없이 동작.

> Docker로 docpilot을 돌리는 경우 컨테이너 안에서 `localhost`는 호스트가 아니다. `OLLAMA_HOST=http://host.docker.internal:11434`(Mac/Win) 또는 호스트 IP를 쓴다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `AuthenticationError` / HTTP 401 | 키가 없거나 오타/만료 | `.env`의 `OPENAI_API_KEY` 확인. `echo $OPENAI_API_KEY`로 셸에 로드됐는지 확인. 새 키 발급 후 교체 |
| HTTP 429 `insufficient_quota` | 크레딧 소진/결제 미등록 | OpenAI 대시보드에서 잔액·결제수단 확인. 급하면 `LLM_PROVIDER=ollama`로 전환 |
| HTTP 429 `rate limit` (요청 과다) | 짧은 시간 너무 많은 호출 | 잠시 대기 후 재시도. 코드에 지수 백오프(재시도 간격을 늘려가며 재시도) 추가 |
| `model_not_found` | 모델명 오타/미지원 | `OPENAI_MODEL=gpt-4o-mini` 등 유효한 이름으로. 계정이 접근 가능한 모델인지 확인 |
| 스트리밍이 한 번에 몰려서 옴 | 프록시/서버 버퍼링 | 응답 헤더에 `X-Accel-Buffering: no` 유지, `curl -N` 사용. Nginx/Ingress면 버퍼링 off |
| SSE에서 줄바꿈 답이 깨짐 | `data:` 프레임에 `\n` 포함 | 조각을 `json.dumps`로 감싸 전송(과제), 또는 `sse-starlette` 사용 |
| 한글이 `\uXXXX`로 보임 | JSON ensure_ascii 기본값 | 확인용일 뿐 실제 문자열은 정상. 굳이 보려면 `json.dumps(..., ensure_ascii=False)` |
| Ollama `connection refused` | 데몬 미실행/주소 오류 | `ollama serve` 실행, `OLLAMA_HOST` 확인. 컨테이너면 `host.docker.internal` |
| 키가 git에 커밋될 뻔함 | `.gitignore` 누락 | `.env`가 `.gitignore`에 있는지 확인. 이미 커밋했다면 **키 즉시 폐기·재발급** |

---

## 이번 주 과제

제출물(리포지토리 커밋 + 짧은 실행 로그/스크린샷):

1. **필수** — docpilot에 `/chat`과 `/chat/stream`을 추가하고, OpenAI(또는 Gemini)로 실제 응답을 받는 스크린샷/로그.
2. **필수** — `.env`가 `.gitignore`에 포함되어 **키가 커밋되지 않았음**을 보이기(`git log`/`git show`에 키가 없어야 함).
3. **도전** — SSE 프레임을 `data: {json.dumps({"delta": piece}, ensure_ascii=False)}` 형태로 바꿔 줄바꿈 안전하게 만들기. `chat.html`도 JSON 파싱하도록 수정.
4. **도전** — `system` 프롬프트를 바꿔 docpilot의 "성격"을 2가지로 만들어 비교(예: 친절한 튜터 vs 깐깐한 시니어). `temperature`도 0.0과 1.0을 비교해 차이를 한 문단으로 서술.
5. **분석** — 같은 질문을 OpenAI / Gemini / Ollama로 각각 호출해 응답 품질·속도·(대략의) 비용을 표로 비교.

---

## 체크리스트

- [ ] `openai`, `google-genai`, `pydantic-settings`, `sse-starlette` 설치 및 `requirements.txt` 반영
- [ ] `.env`로 키 로드, `.gitignore`에 `.env` 포함(하드코딩 0건)
- [ ] `app/config.py`(Settings) 작성 및 import 확인
- [ ] `app/llm.py`로 프로바이더 추상화(`build_messages`/`complete`/`stream`)
- [ ] `/chat`(비스트리밍) 동작 확인 (`/docs`에서도)
- [ ] `/chat/stream`(SSE) 스트리밍 확인 (`curl -N`)
- [ ] `LLM_PROVIDER`만 바꿔 Gemini/Ollama로 교체 성공
- [ ] system 프롬프트/temperature로 응답이 바뀌는 것을 관찰

---

## 다음 주 예고

[Week 7 — 멀티모달과 Hugging Face](./week07-멀티모달과-huggingface.md): 텍스트를 넘어 **이미지·음성**을 다루고, Hugging Face 생태계(Hub, `transformers`, Inference API)를 도입한다. 특히 **텍스트 임베딩 모델**을 붙이는데, 이 임베딩이 [Week 8의 RAG](./week08-rag-검색증강생성.md)에서 문서 검색의 핵심 재료가 된다. 이번 주의 `/chat`(생성)과 다음 주의 임베딩이 만나 week08에서 `/ask`(검색증강 답변)로 완성된다.
