# Week 09 — AI Agent 기초 (Tool/Function Calling · ReAct)

> 이번 주 한 줄: 답만 하던 `docpilot`이 **스스로 도구를 골라 호출**하고 그 결과로 최종 답을 만든다.
> docpilot 진화: `/agent` 엔드포인트 추가 — 계산기·현재시각·(week08) RAG 검색을 **도구(tool)** 로 노출하고, LLM이 도구를 선택·호출하는 **행동 루프**를 raw로 구현(+ LangGraph 버전).

블록 3(AI Agent)의 첫 주다. [블록 2](./README.md)에서 만든 RAG 서비스(week08)의 검색 기능을 **도구 하나로 재사용**하는 것이 이번 주의 연결 고리다.

---

## 학습 목표

- [ ] AI Agent가 무엇인지(LLM + 추론 + 행동 루프), 단순 LLM 호출과 무엇이 다른지 설명할 수 있다.
- [ ] ReAct(Reasoning + Acting) 패턴의 `Thought → Action → Observation` 사이클을 이해한다.
- [ ] OpenAI 스타일 **function calling** 의 원리(도구 스키마 → 모델의 tool_call → 실행 → 결과 반환)를 안다.
- [ ] 프레임워크 없이 **raw Python으로 agent 루프**를 손으로 구현한다.
- [ ] 같은 agent를 **LangGraph** 로도 만들어 본다.
- [ ] week08 RAG 검색을 **도구로 등록**해 agent가 문서 지식을 활용하게 한다.
- [ ] 도구 호출 로그로 추론 과정을 관찰한다.

## 사전 준비

- **지난주 산출물**: week08 RAG 서비스 (`docpilot`의 `/ask`, `app/vectorstore.py`의 `search`). 이번 주는 그 `search`를 `from app.vectorstore import search`로 그대로 가져와 도구로 감싼다. week08을 먼저 완료해 문서가 인덱싱되어 있어야 한다(더미 fallback에 의존하지 않는다).
- **도구·계정**: Python 3.12, OpenAI API 키. 환경 세팅은 [실습 환경과 기술 스택](../02-실습환경과-기술스택.md) 참고.
- **API 키는 환경변수로만** 다룬다. 코드에 하드코딩 금지.
- **키 로딩**: `.env` + `get_settings()`를 기준으로 한다. 아래처럼 shell `export`를 써도 python-dotenv가 `.env`를 읽어 호환된다.

```bash
# docpilot 프로젝트 루트에서 실행. 이번 주 의존성 설치.
cd docpilot
python -m venv .venv && source .venv/bin/activate   # 이미 있으면 activate만
pip install "openai>=1.40" "fastapi>=0.110" "uvicorn[standard]>=0.29" python-dotenv
```

**확인**: `python -c "import openai, fastapi; print(openai.__version__)"` 실행 시 `1.40` 이상 버전 문자열이 출력된다.

```bash
# API 키를 환경변수로 등록 (셸 세션 한정). .env 파일을 쓰면 python-dotenv가 로드한다.
export OPENAI_API_KEY="sk-..."          # 본인 키로 교체
export OPENAI_MODEL="gpt-4o-mini"       # 저비용 모델 기본값
```

**확인**: `echo "${OPENAI_API_KEY:0:3}"` → `sk-` 가 출력되면 키가 설정된 것이다(전체 키는 절대 출력하지 말 것).

---

## 개념 (요약)

### 1. Agent = LLM + 추론 + 행동 루프

단순 LLM 호출은 **한 번 물어보고 한 번 답 받는다**. 모델은 자기 파라미터 안의 지식만으로 답하며, 외부 세계에 손을 뻗지 못한다.

Agent는 여기에 **도구(tool)** 와 **루프**를 더한다. 모델이 "지금은 계산기가 필요하다"고 판단하면 계산기를 호출하고, 그 결과를 다시 모델에게 돌려주어 다음 행동을 결정하게 한다. 이 사이클을 목표가 끝날 때까지 반복한다.

```
[단순 LLM 호출]
  질문 ─▶ LLM ─▶ 답  (한 방)

[Agent]
  질문 ─▶ LLM ─(도구 필요?)─▶ 도구 호출 ─▶ 결과 관찰 ─▶ LLM ─▶ ... ─▶ 최종 답
              └───────────────── 루프 ──────────────────┘
```

| 구분 | 단순 LLM 호출 | AI Agent |
|---|---|---|
| 외부 행동 | 없음 (텍스트만) | 도구로 계산·검색·API·DB 접근 |
| 반복 | 1회 | 목표 달성까지 다단계 루프 |
| 최신/사실 정보 | 학습 시점에 고정 | 도구로 실시간 조회 |
| 추론 관찰 | 답만 보임 | 도구 호출 로그로 과정 관찰 |
| 예시 | "파리 인구는?" → 암기 답 | "이 문서에서 X를 찾아 Y와 곱해줘" → 검색+계산 |

### 2. ReAct 패턴 (Reasoning + Acting)

ReAct는 모델이 **생각(Thought) → 행동(Action) → 관찰(Observation)** 을 번갈아 하며 문제를 푸는 패턴이다.

```
Thought:  세금 포함 가격을 알려면 먼저 문서에서 세율을 찾아야겠다.
Action:   rag_search(query="부가세율")
Observation: "부가세율은 10%입니다."
Thought:  이제 50000 * 1.10 을 계산하면 된다.
Action:   calculator(expression="50000 * 1.10")
Observation: 55000.0
Thought:  답을 만들 수 있다.
Answer:   세금 포함 가격은 55,000원입니다.
```

Function calling은 이 ReAct 루프를 **구조화된 JSON**으로 구현한 것이다. 모델이 자연어로 "Action: calculator(...)"를 쓰는 대신, API가 정한 `tool_calls` 필드에 함수 이름과 인자를 JSON으로 채워 돌려준다. 우리는 그걸 실행해 결과를 `role:"tool"` 메시지로 다시 넣어준다.

### 3. Function/Tool calling 원리 (4단계)

1. **도구 스키마 전달**: 각 도구의 이름·설명·파라미터(JSON Schema)를 `tools` 인자로 모델에 넘긴다.
2. **모델이 도구 선택**: 모델이 필요하다고 판단하면, 텍스트 답 대신 `tool_calls`(함수명 + JSON 인자)를 반환한다.
3. **우리가 실제 실행**: 모델은 함수를 직접 실행하지 못한다. **우리 코드**가 인자를 파싱해 진짜 파이썬 함수를 호출한다.
4. **결과를 되돌려줌**: 실행 결과를 `role:"tool"` 메시지로 대화에 추가하고 다시 모델을 호출한다. 모델은 결과를 보고 다음 행동(또 다른 도구 호출) 또는 최종 답을 낸다.

> 핵심: **모델은 "무엇을 호출할지" 만 정한다. 실제 실행과 안전은 전부 우리 몫이다.** 이 원리가 week10의 가드레일로 이어진다.

---

## 실습: 단계별 따라하기

프로젝트 구조는 다음과 같이 만든다(기존 docpilot에 `agent/` 패키지 추가).

```
docpilot/
├── app/
│   └── main.py            # 기존 FastAPI 앱 (week01~08). 여기에 /agent 라우터를 붙인다.
├── agent/
│   ├── __init__.py
│   ├── tools.py           # 1부: 도구 함수 + JSON 스키마 + 레지스트리
│   ├── raw_agent.py       # 2부: 프레임워크 없는 raw agent 루프
│   ├── graph_agent.py     # 4부: LangGraph 버전
│   └── api.py             # 3부: FastAPI /agent 엔드포인트
└── .env                   # OPENAI_API_KEY 등 (git에 커밋 금지)
```

```bash
# 패키지 디렉터리 생성
mkdir -p agent && touch agent/__init__.py
```

**확인**: `ls agent/` → `__init__.py` 가 보인다.

---

### 1부 · 도구 정의와 등록

#### 1단계. 도구 함수 3개 만들기 (계산기 · 현재시각 · RAG 검색)

`agent/tools.py`를 만든다. 도구는 **순수 파이썬 함수**이고, 여기에 **모델에게 넘길 JSON Schema**를 함께 정의한다. RAG 검색은 week08 함수를 import하되, 없으면 fallback을 쓴다.

```python
# agent/tools.py
"""docpilot agent가 사용할 도구 정의 + 스키마 + 레지스트리."""
from __future__ import annotations

import ast
import datetime as dt
import operator
from zoneinfo import ZoneInfo

# --- 도구 1: 안전한 계산기 -------------------------------------------------
# eval()은 임의 코드 실행 위험이 있으므로, AST를 직접 walk 하며
# 산술 연산자만 허용한다. (입력 검증의 기본기 — week10 가드레일로 이어진다.)
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("허용되지 않은 수식입니다.")


def calculator(expression: str) -> float:
    """산술 수식 문자열을 계산해 숫자를 돌려준다. 예: '50000 * 1.1'."""
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


# --- 도구 2: 현재 시각 -----------------------------------------------------
def current_time(timezone: str = "Asia/Seoul") -> str:
    """지정한 타임존의 현재 시각을 ISO 8601 문자열로 돌려준다."""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("Asia/Seoul")
    return dt.datetime.now(tz).isoformat(timespec="seconds")


# --- 도구 3: RAG 검색 (week08 재사용) --------------------------------------
# week08 app/vectorstore.py의 search를 그대로 도구로 승격한다(재사용은 이 경로로 통일).
# 반환형은 list[dict](keys: text, source, score) — week08의 표준 검색 인터페이스.
from app.vectorstore import search as _rag_search


def rag_search(query: str, top_k: int = 3) -> list[dict]:
    """docpilot 문서 지식베이스에서 질의와 관련된 문단을 검색한다(week08 RAG)."""
    return _rag_search(query, top_k=top_k)


# --- 레지스트리: 이름 -> 실제 함수 -----------------------------------------
TOOL_REGISTRY = {
    "calculator": calculator,
    "current_time": current_time,
    "rag_search": rag_search,
}

# --- 스키마: 모델에게 넘길 도구 명세 (OpenAI tools 포맷) --------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "산술 수식을 계산한다. 덧셈/뺄셈/곱셈/나눗셈/거듭제곱만 지원.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "계산할 수식. 예: '50000 * 1.1'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "지정 타임존의 현재 시각을 ISO 8601로 반환.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 타임존 이름. 기본 'Asia/Seoul'",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "docpilot 문서 지식베이스를 검색한다. 문서 내용에 근거해 답해야 할 때 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색할 자연어 질의"},
                    "top_k": {"type": "integer", "description": "가져올 문단 수(기본 3)"},
                },
                "required": ["query"],
            },
        },
    },
]
```

**확인**: 도구가 단독으로 동작하는지 먼저 검증한다(모델 없이).

```bash
python -c "from agent.tools import calculator, current_time, rag_search; \
print(calculator('50000 * 1.1')); print(current_time()); print(rag_search('부가세'))"
```

기대 출력(시각·검색 결과는 실행 환경에 따라 다름 — `rag_search`는 week08 인덱싱이 되어 있어야 실제 조각을 돌려준다):

```
55000.00000000001
2026-09-07T10:30:00+09:00
[{'text': 'docpilot의 부가세율은 10%로 계산합니다.', 'source': 'docpilot.md', 'score': 0.71}]
```

> **왜 스키마와 함수를 나눠 두나?** 스키마는 "모델에게 도구를 설명하는 문서"이고, 레지스트리는 "실제 실행 대상"이다. 모델은 스키마만 보고 이름·인자를 정하고, 우리는 레지스트리로 진짜 실행한다. 이 분리가 도구 추가를 쉽게 만든다.

---

### 2부 · Raw Agent 루프 (프레임워크 없이)

#### 2단계. 손으로 짠 행동 루프

`agent/raw_agent.py`를 만든다. **이것이 이번 주의 핵심**이다. 프레임워크가 뒤에서 무엇을 하는지 직접 보기 위해 raw로 짠다.

```python
# agent/raw_agent.py
"""프레임워크 없이 구현한 OpenAI function-calling agent 루프."""
from __future__ import annotations

import json
import os

from openai import OpenAI

from agent.tools import TOOL_REGISTRY, TOOL_SCHEMAS

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_STEPS = 6  # 무한 루프 방지: 도구 호출 왕복 최대 횟수

SYSTEM_PROMPT = (
    "너는 docpilot의 assistant다. 필요하면 제공된 도구를 사용해라. "
    "문서 내용에 근거해야 하는 질문은 rag_search를 먼저 사용하고, "
    "계산이 필요하면 calculator를 사용해라. 근거 없이 지어내지 마라."
)

client = OpenAI()  # OPENAI_API_KEY 환경변수를 자동으로 읽는다.


def run_agent(user_query: str, verbose: bool = True) -> dict:
    """agent 루프를 돌려 최종 답과 도구 호출 로그(trace)를 반환한다."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]
    trace: list[dict] = []  # 추론 과정 관찰용 로그

    for step in range(1, MAX_STEPS + 1):
        # (1) 모델 호출: 도구를 쓸지 말지는 모델이 결정(tool_choice="auto")
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # (2) 도구 호출이 없으면 최종 답이다 → 종료
        if not msg.tool_calls:
            if verbose:
                print(f"[step {step}] 최종 답 생성")
            return {"answer": msg.content, "trace": trace, "steps": step}

        # (3) 어시스턴트의 tool_calls를 대화에 그대로 추가 (규격 준수)
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # (4) 각 tool_call을 실제로 실행하고 결과를 role:"tool"로 되돌린다
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                if name not in TOOL_REGISTRY:
                    raise KeyError(f"알 수 없는 도구: {name}")
                result = TOOL_REGISTRY[name](**args)
                ok = True
            except Exception as exc:  # 도구 오류도 모델에게 알려 회복시킨다
                result = f"도구 실행 오류: {exc}"
                ok = False

            if verbose:
                print(f"[step {step}] Action: {name}({args}) -> {result!r}")
            trace.append({"step": step, "tool": name, "args": args, "result": result, "ok": ok})

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    # MAX_STEPS를 넘기면 안전하게 중단
    return {"answer": "최대 스텝을 초과했습니다.", "trace": trace, "steps": MAX_STEPS}


if __name__ == "__main__":
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "지금 서울 시각을 알려주고, 프리미엄 요금제 3개월치 총액을 계산해줘."
    out = run_agent(query)
    print("\n=== 최종 답 ===")
    print(out["answer"])
    print(f"\n(도구 {len(out['trace'])}회 호출, {out['steps']} 스텝)")
```

**확인**: 도구 호출 로그와 함께 최종 답이 나온다.

```bash
python -m agent.raw_agent "지금 서울 시각을 알려주고, 프리미엄 요금제 3개월치 총액을 계산해줘."
```

기대 출력(형태 예시 — 값은 달라질 수 있다):

```
[step 1] Action: current_time({}) -> '2026-09-07T10:30:00+09:00'
[step 2] Action: rag_search({'query': '프리미엄 요금제 가격'}) -> ['docpilot 프리미엄 요금제는 월 29,000원입니다.']
[step 3] Action: calculator({'expression': '29000 * 3'}) -> 87000.0
[step 4] 최종 답 생성

=== 최종 답 ===
현재 서울 시각은 2026-09-07 10:30입니다. 프리미엄 요금제(월 29,000원) 3개월치 총액은 87,000원입니다.
(도구 3회 호출, 4 스텝)
```

> **관찰 포인트**: 모델이 **스스로 순서를 정했다** — 시각 조회 → 문서 검색 → 계산 → 답. 이것이 ReAct의 `Thought→Action→Observation` 사이클이 function calling으로 구현된 모습이다. `trace`가 곧 추론 과정의 기록이다.

---

### 3부 · docpilot에 `/agent` 엔드포인트 붙이기

#### 3단계. FastAPI 라우터 작성

`agent/api.py`를 만든다.

```python
# agent/api.py
"""docpilot /agent 엔드포인트."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent.raw_agent import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="사용자 질의")


class AgentResponse(BaseModel):
    answer: str
    steps: int
    trace: list[dict]


@router.post("", response_model=AgentResponse)
def ask_agent(req: AgentRequest) -> AgentResponse:
    out = run_agent(req.query, verbose=False)
    return AgentResponse(answer=out["answer"], steps=out["steps"], trace=out["trace"])
```

#### 4단계. 기존 앱에 라우터 등록

`app/main.py`(week01부터 자라온 FastAPI 앱)에 아래 두 줄을 추가한다.

```python
# app/main.py (기존 파일에 추가)
from agent.api import router as agent_router

# app = FastAPI(...) 아래에
app.include_router(agent_router)
```

> 아직 `app/main.py`가 없다면, 이번 주 실습용 최소 앱으로 시작할 수 있다:
>
> ```python
> # app/main.py (최소 예시)
> from fastapi import FastAPI
> from agent.api import router as agent_router
>
> app = FastAPI(title="docpilot")
>
> @app.get("/health")
> def health() -> dict:
>     return {"status": "ok"}
>
> app.include_router(agent_router)
> ```

**확인**: 서버를 띄우고 호출한다.

```bash
# 터미널 1: 서버 실행
uvicorn app.main:app --reload --port 8000
```

```bash
# 터미널 2: 호출
curl -s -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"query": "환불 정책 알려주고, 29000원의 10% 부가세 포함 금액도 계산해줘"}' | python -m json.tool
```

기대 출력(요약):

```json
{
    "answer": "환불 정책은 구매 후 7일 이내 전액 환불이 가능합니다. 29,000원에 10% 부가세를 포함하면 31,900원입니다.",
    "steps": 3,
    "trace": [
        {"step": 1, "tool": "rag_search", "args": {"query": "환불 정책"}, "result": ["환불 정책: 구매 후 7일 이내 전액 환불이 가능합니다."], "ok": true},
        {"step": 2, "tool": "calculator", "args": {"expression": "29000 * 1.1"}, "result": 31900.0, "ok": true}
    ]
}
```

> `trace` 필드로 **어떤 도구를 어떤 인자로 호출했는지**가 API 응답에 그대로 드러난다. 디버깅과 신뢰성 확보의 출발점이다.

---

### 4부 · LangGraph 버전 (같은 agent를 프레임워크로) — **선택/도전**

> **선택/도전**: 필수 경로는 2~3부(raw agent + `/agent`)에서 끝난다. 이 4부는 프레임워크 비교용 심화이며, 단일 세션 부담을 줄이려면 건너뛰어도 무방하다.

raw 루프를 이해했으니, 같은 것을 **LangGraph**로 짧게 만들어 본다. 프레임워크는 우리가 손으로 짠 "모델 호출 → 도구 실행 → 되돌리기" 루프를 대신 관리해 준다.

```bash
pip install "langgraph>=0.2" "langchain-openai>=0.2"
```

**확인**: `python -c "import langgraph, langchain_openai; print('ok')"` → `ok`.

#### 5단계. `create_react_agent`로 구현

`agent/graph_agent.py`를 만든다.

```python
# agent/graph_agent.py
"""LangGraph 프리빌트 ReAct agent 버전."""
from __future__ import annotations

import os

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agent import tools as t

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# 기존 순수 함수를 LangChain 도구로 감싼다. docstring이 곧 도구 설명이 된다.
@tool
def calculator(expression: str) -> float:
    """산술 수식을 계산한다. 예: '50000 * 1.1'."""
    return t.calculator(expression)


@tool
def current_time(timezone: str = "Asia/Seoul") -> str:
    """지정 타임존의 현재 시각을 ISO 8601로 반환한다."""
    return t.current_time(timezone)


@tool
def rag_search(query: str, top_k: int = 3) -> list[str]:
    """docpilot 문서 지식베이스를 검색한다(week08 RAG)."""
    return t.rag_search(query, top_k=top_k)


llm = ChatOpenAI(model=MODEL, temperature=0)
graph_agent = create_react_agent(llm, [calculator, current_time, rag_search])


def run_graph_agent(user_query: str) -> str:
    result = graph_agent.invoke({"messages": [("user", user_query)]})
    # 마지막 메시지가 최종 답. 중간 메시지에 도구 호출 기록이 남는다.
    for m in result["messages"]:
        m.pretty_print()   # 추론 과정(도구 호출 포함) 전체 출력
    return result["messages"][-1].content


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "프리미엄 요금제 6개월치 총액은?"
    print("\n=== 최종 답 ===")
    print(run_graph_agent(q))
```

**확인**:

```bash
python -m agent.graph_agent "프리미엄 요금제 6개월치 총액은 얼마야?"
```

`pretty_print()`가 `Human → Ai(tool_calls) → Tool → Ai(최종답)` 흐름을 순서대로 보여준다. raw 버전의 `trace`와 **같은 사이클**이 프레임워크 내부에서 돈다는 것을 눈으로 확인한다.

> **raw vs LangGraph**: raw는 루프·에러·중단 조건을 전부 우리가 통제한다(학습·디버깅에 최적). LangGraph는 상태 관리·체크포인트·스트리밍을 제공해 복잡한 그래프(week11 Multi-Agent)로 확장하기 좋다. **원리는 동일**하다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `AuthenticationError` / 401 | `OPENAI_API_KEY` 미설정·오타 | `echo "${OPENAI_API_KEY:0:3}"`로 확인 후 `export` 재실행. `.env` 사용 시 `load_dotenv()` 호출 여부 확인 |
| 모델이 도구를 안 쓰고 지어냄 | system 프롬프트가 약함 / 도구 description 모호 | "근거 없이 지어내지 마라", "rag_search를 먼저" 등 지시 강화, 도구 설명을 구체적으로 |
| `KeyError: name` | 스키마의 함수명과 `TOOL_REGISTRY` 키 불일치 | 이름을 정확히 일치시킨다 (예: `rag_search`) |
| 무한/과다 루프 | 모델이 같은 도구 반복 호출 | `MAX_STEPS`로 상한 유지, 도구 결과를 명확히 반환 |
| `TypeError: unexpected keyword argument` | 모델이 스키마에 없는 인자를 생성 | `parameters`의 `properties`/`required`를 실제 함수 시그니처와 일치 |
| tool 결과 직렬화 오류 | 반환값이 JSON 불가 타입 | `json.dumps(..., default=str)` 사용(이미 코드에 반영) |
| `rag_search`가 빈 결과/`ImportError` | week08 미완성·미인덱싱, 또는 import 경로 오타 | `from app.vectorstore import search`로 통일하고 week08 인덱싱(문서 저장)을 먼저 완료 |

---

## 이번 주 과제

**제출물**: `docpilot` 저장소에 아래를 포함한 커밋/PR.

1. **새 도구 1개 추가**: `word_count`(문자열의 단어 수 반환) 또는 `unit_convert`(예: km↔mile) 중 하나를 골라 `agent/tools.py`에 함수 + 스키마 + 레지스트리 등록까지 완성한다.
2. 새 도구를 실제로 호출하게 만드는 질의 1개로 `/agent`를 호출하고, **응답 JSON의 `trace`에 새 도구가 찍힌 스크린샷/로그**를 제출한다.
3. `README`에 "raw agent와 LangGraph agent의 차이"를 3줄 이상으로 정리한다.
4. (선택) `MAX_STEPS`를 2로 낮췄을 때 어떤 질의가 "최대 스텝 초과"로 실패하는지 하나 찾아 보고한다.

**채점 포인트**: 스키마-함수-레지스트리 3곳이 일치하는가 / 모델이 새 도구를 실제로 선택했는가(trace 근거) / 하드코딩된 키가 없는가.

---

## 체크리스트

- [ ] `agent/tools.py`의 세 도구가 모델 없이 단독 실행된다.
- [ ] `python -m agent.raw_agent`가 도구 호출 로그와 최종 답을 출력한다.
- [ ] `/agent` 엔드포인트가 `answer` + `trace`를 반환한다.
- [ ] LangGraph 버전이 같은 질의에 대해 동작한다.
- [ ] week08 RAG 검색(`from app.vectorstore import search`)이 도구로 연결됐다.
- [ ] API 키가 코드에 없고 환경변수로만 주입된다.
- [ ] 새 도구 1개를 추가하고 trace로 호출을 확인했다.

---

## 다음 주 예고

week10에서는 이 도구들이 **장난감을 벗어난다**. 외부 REST API·PostgreSQL·파일 시스템에 실제로 연결하고, **타임아웃/재시도/입력검증** 가드레일을 두른다. 그리고 docpilot의 도구들을 **MCP(Model Context Protocol) 서버**로 노출해, 표준 프로토콜로 어떤 MCP 클라이언트든 우리 도구를 호출할 수 있게 만든다. 여기서부터 docpilot은 진짜 **Agentic 서비스**가 된다. → [week10 — 도구·데이터 연동과 MCP](./week10-도구데이터연동과-mcp.md)
