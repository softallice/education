# Week 11 — Multi-Agent 시스템

> 이번 주 한 줄: 하나의 에이전트가 다 하던 일을 **역할별 에이전트로 쪼개고**, 오케스트레이터가 이들을 협업시켜 보고서를 만든다.
> docpilot 진화: `researcher`(정보 수집) + `writer`(보고서 작성) 에이전트가 오케스트레이터를 통해 협업하는 `/report` 워크플로우 추가. (Block 3 피날레: 단일 Agent → Agentic → **Multi-Agent**)

## 학습 목표

- [ ] Multi-Agent 협업 패턴(역할 분담, 오케스트레이터/워커, 메시지 전달)을 설명할 수 있다.
- [ ] 에이전트 간 **상태·메모리 공유** 구조를 설계하고 로그로 관찰할 수 있다.
- [ ] week08 RAG + week10 도구를 쓰는 `researcher`와, 그 결과로 글을 쓰는 `writer`를 raw Python으로 오케스트레이션할 수 있다.
- [ ] 같은 워크플로우를 **LangGraph**의 `StateGraph`로 재구성할 수 있다.
- [ ] **실패 복구**(에이전트 실패 시 재시도/폴백)와 **휴먼 인 더 루프**(승인 게이트)를 넣을 수 있다.

## 사전 준비

- **지난주 산출물**: week09 단일 Agent(`/agent`, function/tool calling, ReAct 루프), week10 실제 도구·MCP 연동. week08의 RAG 검색(`app/vectorstore.py`의 `search`, `from app.vectorstore import search`로 재사용).
- **필요 도구·계정**: Python 3.12, OpenAI API 키(`OPENAI_API_KEY`). week08에서 만든 벡터DB(Chroma 또는 pgvector)에 문서가 이미 인덱싱되어 있어야 한다.
- **키 로딩**: `.env` + `get_settings()`를 기준으로 한다. 아래 shell `export`를 써도 python-dotenv가 `.env`를 읽어 호환된다.
- **디렉터리**: 지금까지의 `docpilot/` 프로젝트. 이번 주는 `app/agents/` 아래에 파일을 추가한다.

```bash
# 무엇을/왜: 현재 프로젝트 상태와 지난주 결과물이 도는지 확인
cd docpilot
source .venv/bin/activate           # week01에서 만든 가상환경
python -c "import openai; print('openai', openai.__version__)"
echo "OPENAI_API_KEY set? -> ${OPENAI_API_KEY:+yes}"
```

**확인**: `openai <버전>` 이 출력되고, `OPENAI_API_KEY set? -> yes` 가 보이면 준비 완료. `yes`가 안 나오면 `export OPENAI_API_KEY=sk-...` 로 키를 넣는다.

---

## 개념 (요약)

### 왜 Multi-Agent인가

단일 에이전트에 "검색도 하고, 도구도 쓰고, 길고 잘 다듬어진 보고서도 써라"를 한 프롬프트에 몰아넣으면 두 가지가 무너진다. (1) **프롬프트가 비대해져** 지시가 서로 간섭한다. (2) 한 역할의 실패가 전체를 망친다. 역할을 나누면 각 에이전트의 프롬프트·도구·모델을 **따로 최적화**하고, 실패를 **국소화**할 수 있다.

### 핵심 패턴 4가지

| 패턴 | 설명 | docpilot에서 |
|---|---|---|
| **역할 분담(Role split)** | 에이전트마다 하나의 책임 | `researcher`=수집, `writer`=작성 |
| **오케스트레이터/워커** | 중앙 조정자가 워커를 순서대로 호출·결과 전달 | `run_report()` / LangGraph 그래프 |
| **메시지 전달(Message passing)** | 에이전트 간 입출력을 구조화된 메시지로 주고받음 | `AgentMessage` dataclass |
| **공유 상태(Shared state)** | 워크플로우 전체가 읽고 쓰는 하나의 상태 객체 | `ReportState` dataclass / `TypedDict` |

### 오케스트레이션의 두 가지 결

- **raw 오케스트레이션**: 그냥 Python 함수가 순서대로 에이전트를 호출한다. 흐름이 눈에 다 보여서 **학습·디버깅에 최적**. 조건 분기·재시도도 `if`/`try`로 직접 쓴다.
- **그래프 기반(LangGraph)**: 노드(에이전트)와 엣지(전이)로 워크플로우를 선언한다. 상태 관리·체크포인트·분기·사이클을 프레임워크가 관리해 **복잡해질수록 유리**하다.

먼저 raw로 원리를 손에 익히고, 같은 것을 LangGraph로 다시 만들어 둘을 비교한다.

### 상태·메모리 / 실패 복구 / 휴먼 인 더 루프

- **상태·메모리 공유**: 각 에이전트가 다음 에이전트에게 넘길 산출물을 하나의 상태 객체에 누적한다. "출처(sources)"까지 상태에 담아 writer가 인용할 수 있게 한다.
- **실패 복구**: 워커 호출을 `try/except` + 재시도로 감싸고, 수집 실패 시 "RAG만으로 폴백" 같은 대안 경로를 둔다.
- **휴먼 인 더 루프(HITL)**: writer가 최종본을 내기 전에 사람이 초안을 승인/반려하는 게이트. 이번 주는 `approve=True/False` 플래그로 최소 구현한다.

---

## 실습: 단계별 따라하기

전체 흐름은 3부다. **1부**에서 공용 부품(상태·메시지·도구·로그)을 만들고, **2부**에서 raw 오케스트레이션 `/report`를 완성한다. **3부**에서 같은 워크플로우를 LangGraph로 재구성하고 실패 복구·HITL을 얹는다.

### 목표 아키텍처

```text
                 POST /report {"topic": "..."}
                          │
                          ▼
             ┌────────────────────────┐
             │      Orchestrator       │  상태(ReportState) 소유
             └────────────────────────┘
                 │(1) 수집 지시        ▲ (4) 최종 보고서
                 ▼                     │
        ┌─────────────────┐   findings │
        │   researcher    │────────────┘
        │  (RAG + tools)  │   (2) 수집 결과 + sources
        └─────────────────┘
                 │ (3) findings 전달
                 ▼
        ┌─────────────────┐
        │     writer      │  findings → 마크다운 보고서
        └─────────────────┘
```

---

## 1부 · 공용 부품 만들기

### 1단계. 상태·메시지 자료구조

에이전트들이 주고받을 **메시지**와, 워크플로우 전체가 공유할 **상태**를 정의한다. 관찰(observability)을 위해 모든 단계가 `state.log`에 append된다.

`app/agents/state.py`:

```python
"""Multi-Agent 워크플로우의 공유 상태와 메시지 자료구조."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class AgentMessage:
    """에이전트 간 주고받는 한 건의 메시지(관찰용)."""
    sender: str          # "orchestrator" | "researcher" | "writer"
    recipient: str
    kind: str            # "instruction" | "result" | "error" | "human"
    content: str
    ts: float = field(default_factory=time.time)

    def pretty(self) -> str:
        preview = self.content.replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:117] + "..."
        return f"[{self.sender:>12} -> {self.recipient:<12}] ({self.kind}) {preview}"


@dataclass
class Finding:
    """researcher가 수집한 근거 한 조각. writer가 인용한다."""
    claim: str
    source: str          # 문서명/URL 등 출처


@dataclass
class ReportState:
    """/report 워크플로우 전체가 읽고 쓰는 단일 상태 객체."""
    topic: str
    findings: list[Finding] = field(default_factory=list)
    report: str = ""
    approved: bool = False
    log: list[AgentMessage] = field(default_factory=list)

    def emit(self, msg: AgentMessage) -> None:
        """메시지를 로그에 남기고 즉시 콘솔에 찍는다(실시간 관찰)."""
        self.log.append(msg)
        print(msg.pretty(), flush=True)
```

**확인**: `python -c "from app.agents.state import ReportState; s=ReportState(topic='t'); print(s)"` 실행 시 `ReportState(topic='t', findings=[], ...)` 가 출력된다.

### 2단계. 도구 정의 (week08 RAG + week10 tools 재사용)

`researcher`가 쓸 도구를 함수로 노출한다. **week08의 벡터 검색**과 **week10의 외부 도구** 중 대표로 하나(여기선 간단한 정의 검색)를 가져온다. 실제 프로젝트에선 week10에서 만든 도구 모듈을 import하면 된다.

`app/agents/tools.py`:

```python
"""researcher 에이전트가 사용하는 도구들. week08 RAG + week10 tools를 재사용."""
from __future__ import annotations

# --- week08에서 만든 벡터DB 검색(app/vectorstore.py의 search)을 재사용한다 ---
# 재사용은 항상 이 경로로 통일한다(week09~11 공통). 더미 fallback에 의존하지 않는다.
from app.vectorstore import search as _vector_search  # week08 산출물


def rag_search(query: str, k: int = 4) -> list[dict]:
    """docpilot 벡터DB에서 query와 유사한 문서 조각 k개를 검색한다.

    Returns: [{"text": str, "source": str, "score": float}, ...]
    """
    hits = _vector_search(query, top_k=k)
    # week08 search는 이미 list[dict](keys: text, source, score)를 반환한다.
    return [{"text": h["text"], "source": h.get("source", "unknown")} for h in hits]


def keyword_lookup(term: str) -> dict:
    """(week10 외부 도구 예시) 용어의 짧은 정의를 반환한다.

    실제 수업에서는 week10에서 만든 실제 API/DB/파일 도구로 교체한다.
    """
    glossary = {
        "rag": "Retrieval-Augmented Generation: 외부 지식을 검색해 LLM 응답에 결합하는 기법.",
        "agent": "LLM에 추론+행동 루프를 붙여 도구를 사용하게 만든 시스템.",
    }
    return {"term": term, "definition": glossary.get(term.lower(), "정의 없음")}


# OpenAI function calling에 넘길 스키마 + 실제 파이썬 함수 매핑
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "docpilot 문서 벡터DB에서 주제와 관련된 근거 조각을 검색한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색어"},
                    "k": {"type": "integer", "description": "가져올 조각 수", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "keyword_lookup",
            "description": "용어의 짧은 정의를 조회한다.",
            "parameters": {
                "type": "object",
                "properties": {"term": {"type": "string"}},
                "required": ["term"],
            },
        },
    },
]

TOOL_IMPL = {"rag_search": rag_search, "keyword_lookup": keyword_lookup}
```

**확인**: `python -c "from app.agents.tools import rag_search; print(rag_search('agent', k=2))"` 실행 시 조각 2개가 담긴 리스트가 출력된다(week08을 먼저 완료해 문서가 인덱싱되어 있어야 실제 조각이 나온다).

---

## 2부 · raw 오케스트레이션으로 `/report` 완성

### 3단계. researcher 에이전트 (RAG + tools 루프)

researcher는 **ReAct식 tool-calling 루프**를 돈다: 모델이 도구를 부르면 실행해 결과를 되먹이고, 모델이 더 이상 도구를 안 부르면 최종 findings(JSON)를 파싱해 상태에 담는다.

`app/agents/researcher.py`:

```python
"""researcher 에이전트: RAG + 도구로 근거를 수집한다."""
from __future__ import annotations

import json

from openai import OpenAI

from app.agents.state import AgentMessage, Finding, ReportState
from app.agents.tools import TOOL_IMPL, TOOL_SCHEMAS

client = OpenAI()
MODEL = "gpt-4o-mini"
MAX_TOOL_TURNS = 5  # 무한 루프 방지 상한

SYSTEM = (
    "You are a research agent for docpilot. "
    "Use the provided tools (rag_search, keyword_lookup) to gather evidence "
    "about the user's topic. Prefer rag_search on docpilot's own documents. "
    "When you have enough evidence, STOP calling tools and reply with a JSON object: "
    '{"findings": [{"claim": "...", "source": "..."}, ...]}. '
    "Every claim MUST include a source you actually retrieved."
)


def run_researcher(state: ReportState) -> None:
    """state.topic을 조사해 state.findings를 채운다."""
    state.emit(AgentMessage("orchestrator", "researcher", "instruction",
                            f"'{state.topic}' 근거를 수집하라"))

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"주제: {state.topic}"},
    ]

    for turn in range(MAX_TOOL_TURNS):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.2,
        )
        choice = resp.choices[0].message

        # (a) 도구 호출이 없으면 최종 findings JSON을 파싱하고 종료
        if not choice.tool_calls:
            findings = _parse_findings(choice.content or "{}")
            state.findings = findings
            state.emit(AgentMessage("researcher", "orchestrator", "result",
                                    f"{len(findings)}개 근거 수집 완료"))
            return

        # (b) 도구 호출이 있으면 실행해 결과를 되먹인다
        # week09와 동일하게 tool_calls를 dict로 재구성해 보존한다(SDK 객체 직접 append 금지).
        messages.append({
            "role": "assistant",
            "content": choice.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in choice.tool_calls
            ],
        })
        for call in choice.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            state.emit(AgentMessage("researcher", f"tool:{name}", "instruction",
                                    json.dumps(args, ensure_ascii=False)))
            try:
                result = TOOL_IMPL[name](**args)
            except Exception as exc:  # 도구 실패도 모델에 되먹여 스스로 복구시킴
                result = {"error": str(exc)}
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    # 상한 도달: 지금까지 검색된 것으로 최소 findings라도 만든다(실패 복구)
    state.emit(AgentMessage("researcher", "orchestrator", "error",
                            "도구 턴 상한 도달 — RAG 폴백으로 마무리"))
    _rag_fallback(state)


def _parse_findings(raw: str) -> list[Finding]:
    """모델이 준 JSON 문자열을 Finding 리스트로 변환한다."""
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        data = json.loads(raw)
        return [Finding(claim=f["claim"], source=f.get("source", "unknown"))
                for f in data.get("findings", [])]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def _rag_fallback(state: ReportState) -> None:
    """도구 루프가 실패했을 때 순수 RAG 검색 결과로 findings를 채우는 폴백."""
    from app.agents.tools import rag_search
    hits = rag_search(state.topic, k=4)
    state.findings = [Finding(claim=h["text"], source=h["source"]) for h in hits]
```

**확인**: 아직 단독 실행은 하지 않는다(오케스트레이터에서 호출). 문법 확인만: `python -c "import app.agents.researcher"` 가 에러 없이 끝나야 한다.

### 4단계. writer 에이전트 (findings → 보고서)

writer는 도구를 쓰지 않는다. **오직 researcher가 모은 findings만** 근거로 마크다운 보고서를 쓴다(환각 억제: "주어진 근거 밖 사실은 쓰지 말라").

`app/agents/writer.py`:

```python
"""writer 에이전트: findings로 마크다운 보고서를 작성한다."""
from __future__ import annotations

from openai import OpenAI

from app.agents.state import AgentMessage, ReportState

client = OpenAI()
MODEL = "gpt-4o-mini"

SYSTEM = (
    "You are a writer agent for docpilot. Write a concise Korean report in Markdown "
    "using ONLY the provided findings. Do not invent facts beyond them. "
    "Structure: '# 제목', '## 요약', '## 본문'(근거를 문장으로 엮되 각 문장 끝에 [source] 표기), "
    "'## 참고 출처'(사용한 source 목록). If findings are empty, say so honestly."
)


def run_writer(state: ReportState) -> None:
    """state.findings로 state.report를 채운다."""
    state.emit(AgentMessage("orchestrator", "writer", "instruction",
                            f"{len(state.findings)}개 근거로 '{state.topic}' 보고서 작성"))

    evidence = "\n".join(
        f"- {f.claim} [source: {f.source}]" for f in state.findings
    ) or "(근거 없음)"

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"주제: {state.topic}\n\n근거:\n{evidence}"},
        ],
        temperature=0.4,
    )
    state.report = resp.choices[0].message.content or ""
    state.emit(AgentMessage("writer", "orchestrator", "result",
                            f"보고서 {len(state.report)}자 작성 완료"))
```

**확인**: `python -c "import app.agents.writer"` 가 에러 없이 끝난다.

### 5단계. 오케스트레이터 + 실패 복구 + HITL

오케스트레이터는 상태를 만들고 researcher → (승인 게이트) → writer 순서로 호출한다. 각 워커를 `try/except`로 감싸 **한 워커가 죽어도 워크플로우가 통째로 죽지 않게** 한다.

`app/agents/orchestrator.py`:

```python
"""오케스트레이터: researcher -> (human gate) -> writer 순서로 협업을 지휘한다."""
from __future__ import annotations

from app.agents.researcher import run_researcher
from app.agents.state import AgentMessage, ReportState
from app.agents.writer import run_writer


def run_report(topic: str, require_human_approval: bool = False) -> ReportState:
    """/report 워크플로우의 raw 오케스트레이션 진입점."""
    state = ReportState(topic=topic)
    state.emit(AgentMessage("user", "orchestrator", "instruction", f"주제: {topic}"))

    # (1) 수집 단계 — 실패해도 폴백 findings로 계속 진행
    try:
        run_researcher(state)
    except Exception as exc:
        state.emit(AgentMessage("researcher", "orchestrator", "error", str(exc)))
        from app.agents.researcher import _rag_fallback
        _rag_fallback(state)

    # (2) 휴먼 인 더 루프 — 근거를 사람이 보고 승인해야 작성으로 넘어감
    if require_human_approval:
        state.approved = _ask_human(state)
        if not state.approved:
            state.emit(AgentMessage("human", "orchestrator", "human", "반려 — 작성 중단"))
            return state
    else:
        state.approved = True

    # (3) 작성 단계
    try:
        run_writer(state)
    except Exception as exc:
        state.emit(AgentMessage("writer", "orchestrator", "error", str(exc)))
        state.report = "(보고서 생성 실패 — 로그를 확인하세요)"

    return state


def _ask_human(state: ReportState) -> bool:
    """CLI에서 근거를 보여주고 승인 여부를 묻는다(최소 HITL)."""
    print("\n=== 수집된 근거 (승인 대기) ===")
    for i, f in enumerate(state.findings, 1):
        print(f"  {i}. {f.claim}  [{f.source}]")
    state.emit(AgentMessage("orchestrator", "human", "instruction", "근거 승인 요청"))
    answer = input("이 근거로 보고서를 작성할까요? [y/N] ").strip().lower()
    return answer == "y"
```

이제 CLI로 먼저 굴려 본다:

```bash
# 무엇을/왜: FastAPI 없이 오케스트레이션만 단독 실행해 흐름·로그를 관찰
python -c "
from app.agents.orchestrator import run_report
s = run_report('docpilot의 RAG 구조를 설명하는 보고서')
print('\n===== REPORT =====\n')
print(s.report)
"
```

**확인**: 콘솔에 아래처럼 **에이전트 간 메시지 로그가 순서대로** 찍히고, 마지막에 마크다운 보고서가 나온다.

```text
[        user -> orchestrator] (instruction) 주제: docpilot의 RAG 구조를 설명하는 보고서
[orchestrator -> researcher  ] (instruction) 'docpilot의 RAG 구조...' 근거를 수집하라
[  researcher -> tool:rag_search] (instruction) {"query": "docpilot RAG 구조"}
[  researcher -> orchestrator] (result) 4개 근거 수집 완료
[orchestrator -> writer      ] (instruction) 4개 근거로 ... 보고서 작성
[      writer -> orchestrator] (result) 보고서 812자 작성 완료
===== REPORT =====
# docpilot의 RAG 구조 ...
```

### 6단계. `/report` 엔드포인트 연결

`app/main.py`에 라우트를 추가한다(기존 `/ask`, `/agent` 옆에).

```python
# app/main.py 에 추가
from fastapi import Body
from pydantic import BaseModel

from app.agents.orchestrator import run_report


class ReportRequest(BaseModel):
    topic: str
    require_human_approval: bool = False


class ReportResponse(BaseModel):
    topic: str
    report: str
    findings: list[dict]
    log: list[str]


@app.post("/report", response_model=ReportResponse)
def report(req: ReportRequest = Body(...)) -> ReportResponse:
    """researcher+writer 협업으로 topic에 대한 보고서를 생성한다."""
    state = run_report(req.topic, require_human_approval=req.require_human_approval)
    return ReportResponse(
        topic=state.topic,
        report=state.report,
        findings=[{"claim": f.claim, "source": f.source} for f in state.findings],
        log=[m.pretty() for m in state.log],  # 관측성: 협업 로그를 응답에 포함
    )
```

> 참고: HITL(`require_human_approval=True`)은 `input()`으로 블로킹하므로 **HTTP 요청에는 부적합**하다. API에서는 `False`로 두고, HITL은 CLI 실행(5단계)에서 시연한다. 실서비스형 HITL은 "초안 저장 → 사람이 승인 API 호출 → 이어서 작성" 두 단계로 쪼갠다(과제/응용).

서버를 띄우고 호출한다:

```bash
# 무엇을/왜: docpilot 웹서버 실행
uvicorn app.main:app --reload --port 8000
```

다른 터미널에서:

```bash
# 무엇을/왜: /report 호출 — 협업 로그(log)까지 응답으로 확인
curl -s -X POST http://localhost:8000/report \
  -H "Content-Type: application/json" \
  -d '{"topic": "docpilot의 Agent 아키텍처 요약"}' | python -m json.tool
```

**확인**: `report`에 마크다운 문자열, `findings`에 근거 배열, `log`에 `[orchestrator -> researcher ...]` 형태의 협업 로그 배열이 담긴 JSON이 반환된다.

---

## 3부 · LangGraph 버전 + 실패 복구/HITL — **선택/도전**

> **선택/도전**: 필수 경로는 2부(raw 오케스트레이션 `/report`)에서 끝난다. 실패 복구·HITL은 2부 5단계에서 이미 raw로 시연했다. 이 3부는 같은 워크플로우를 프레임워크로 다시 짜 비교하는 심화이며, 단일 세션 부담을 줄이려면 건너뛰어도 무방하다.

같은 워크플로우를 **LangGraph**로 재구성한다. 상태를 `TypedDict`로 선언하고, 각 에이전트를 노드로, 순서를 엣지로 표현한다. 조건부 엣지로 HITL 분기를 넣는다.

### 7단계. LangGraph 설치

```bash
# 무엇을/왜: 그래프 오케스트레이션 프레임워크 설치 (week09와 동일 버전 핀)
pip install "langgraph>=0.2"
python -c "import langgraph; print('langgraph', langgraph.__version__)"
```

**확인**: `langgraph <버전>` 이 출력된다.

### 8단계. StateGraph로 워크플로우 선언

앞서 만든 `run_researcher`/`run_writer`를 **그대로 재사용**하되, LangGraph 상태(dict)와 우리 `ReportState` 사이를 얇게 어댑팅한다.

`app/agents/graph_report.py`:

```python
"""week11 LangGraph 버전: researcher -> (approval?) -> writer 그래프."""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.researcher import run_researcher
from app.agents.state import Finding, ReportState
from app.agents.writer import run_writer


class GraphState(TypedDict):
    topic: str
    findings: list[dict]
    report: str
    approved: bool
    log: list[str]


def _to_report_state(gs: GraphState) -> ReportState:
    st = ReportState(topic=gs["topic"])
    st.findings = [Finding(**f) for f in gs.get("findings", [])]
    return st


def researcher_node(gs: GraphState) -> GraphState:
    """노드: 근거 수집. 실패 시 예외를 폴백으로 흡수."""
    st = _to_report_state(gs)
    try:
        run_researcher(st)
    except Exception:
        # 수집 실패 시 순수 RAG 검색 결과로 폴백한다(ReportState.log에 이미 기록됨).
        from app.agents.researcher import _rag_fallback
        _rag_fallback(st)
    return {
        **gs,
        "findings": [{"claim": f.claim, "source": f.source} for f in st.findings],
        "log": gs["log"] + [m.pretty() for m in st.log],
    }


def approval_gate(gs: GraphState) -> str:
    """조건부 엣지: 근거가 있으면 write로, 없으면 종료로 분기(휴먼 게이트 자리)."""
    return "write" if gs["findings"] else "skip"


def writer_node(gs: GraphState) -> GraphState:
    """노드: findings로 보고서 작성."""
    st = _to_report_state(gs)
    run_writer(st)
    return {**gs, "report": st.report,
            "log": gs["log"] + [m.pretty() for m in st.log]}


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("research", researcher_node)
    g.add_node("write", writer_node)
    g.add_edge(START, "research")
    g.add_conditional_edges("research", approval_gate,
                            {"write": "write", "skip": END})
    g.add_edge("write", END)
    return g.compile()


GRAPH = build_graph()


def run_report_graph(topic: str) -> GraphState:
    """LangGraph 버전 진입점."""
    init: GraphState = {"topic": topic, "findings": [], "report": "",
                        "approved": False, "log": []}
    return GRAPH.invoke(init)
```

CLI로 실행해 raw 버전과 결과를 비교한다:

```bash
# 무엇을/왜: 같은 주제를 LangGraph 버전으로 실행 — 결과·로그 비교
python -c "
from app.agents.graph_report import run_report_graph
gs = run_report_graph('docpilot의 RAG 구조를 설명하는 보고서')
print('\n===== GRAPH REPORT =====\n')
print(gs['report'])
print('\n----- log -----')
print('\n'.join(gs['log']))
"
```

**확인**: raw 버전(5단계)과 유사한 보고서가 나오고, `log`에 `research -> write` 순서로 협업 흔적이 남는다. 근거가 0개면 `write` 노드를 건너뛰고 바로 종료된다(조건부 엣지 동작 확인).

### 9단계. `/report/graph` 엔드포인트 추가 (버전 선택)

`app/main.py`에 그래프 버전 라우트를 추가해 두 구현을 나란히 제공한다.

```python
# app/main.py 에 추가
from app.agents.graph_report import run_report_graph


@app.post("/report/graph", response_model=ReportResponse)
def report_graph(req: ReportRequest = Body(...)) -> ReportResponse:
    """LangGraph로 오케스트레이션한 /report."""
    gs = run_report_graph(req.topic)
    return ReportResponse(
        topic=gs["topic"], report=gs["report"],
        findings=gs["findings"], log=gs["log"],
    )
```

```bash
# 무엇을/왜: 그래프 엔드포인트 호출 확인
curl -s -X POST http://localhost:8000/report/graph \
  -H "Content-Type: application/json" \
  -d '{"topic": "docpilot Multi-Agent 협업 흐름"}' | python -m json.tool
```

**확인**: `/report`와 동일한 스키마의 JSON이 반환되고, `log`에 `research`/`write` 노드 로그가 담긴다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `ImportError`/빈 검색 결과 (`app.vectorstore.search`) | week08 미완성·미인덱싱, 또는 import 경로 오타 | `from app.vectorstore import search`로 통일하고 week08 인덱싱(문서 저장)을 먼저 완료 |
| researcher가 도구를 안 부르고 바로 JSON을 냄 | 프롬프트가 도구 사용을 강제하지 않음 | SYSTEM에 "Prefer rag_search first" 강화, 또는 첫 턴 `tool_choice={"type":"function","function":{"name":"rag_search"}}` 로 강제 |
| 무한 tool-calling / 비용 폭증 | 종료 조건 부재 | `MAX_TOOL_TURNS` 상한 유지, 도달 시 `_rag_fallback`으로 마무리(이미 구현됨) |
| `_parse_findings`가 빈 리스트 반환 | 모델이 코드펜스/설명을 섞어 응답 | `removeprefix('```json')` 유지 + `response_format={"type":"json_object"}` 옵션 추가 |
| writer가 근거 밖 내용을 지어냄(환각) | 근거 제약이 약함 | SYSTEM의 "ONLY the provided findings" 강조, `temperature` 낮추기 |
| LangGraph `KeyError` on state | 노드가 상태 키를 빠뜨리고 반환 | 노드는 항상 `{**gs, ...}`로 기존 상태를 보존해 반환 |
| API 호출이 HITL `input()`에서 멈춤 | HTTP에서 블로킹 입력 사용 | API는 `require_human_approval=False`, HITL은 CLI에서만 시연 |
| `RateLimitError` / 429 | 짧은 시간 다중 호출 | 재시도 백오프 추가(`tenacity`), 모델을 `gpt-4o-mini`로 유지 |

---

## 이번 주 과제 (블록 3 미니 과제)

> ⚠️ **블록 3 미니 과제**: week11(Multi-Agent) 종료 시점이 블록 3(AI Agent)의 피날레다. week09(단일 Agent) → week10(Agentic) → week11(Multi-Agent)에서 만든 부품을 하나의 협업 워크플로우로 조립한 결과물을 이 과제로 제출한다. 블록 3 평가는 이 결과물을 기준으로 한다.

**`reviewer` 에이전트를 추가해 3-에이전트 협업으로 확장한다.**

1. `app/agents/reviewer.py`에 `run_reviewer(state)` 구현:
   - writer의 `state.report`와 researcher의 `state.findings`를 입력받아,
   - 보고서의 각 주장이 findings로 **뒷받침되는지** 검증하고,
   - 문제점(근거 없는 문장, 누락된 출처)을 목록으로 반환한다.
2. 오케스트레이터를 `researcher → writer → reviewer` 순으로 확장하고,
   - reviewer가 "수정 필요"를 반환하면 **writer를 1회 재호출**(피드백 반영)하는 루프를 넣는다(최대 2회).
3. `/report` 응답에 `review` 결과(통과/수정사항)를 포함한다.
4. **(선택/도전)** LangGraph 버전에도 `review` 노드와 **조건부 엣지**(review → write 재작성 or → END)를 추가한다. (3부가 선택/도전이므로 이 항목도 선택이다.)

**제출물**:
- `app/agents/reviewer.py` + 수정된 `orchestrator.py`, `main.py` (`graph_report.py`는 선택/도전)
- `curl`로 `/report` 호출한 요청/응답 로그(협업 로그 `log` 포함)를 담은 `week11-과제.md`
- 재작성 루프가 동작한 사례(reviewer 지적 → writer 수정) 로그 캡처 1건

---

## 체크리스트

- [ ] `ReportState`/`AgentMessage`로 상태·메시지 전달을 구현했다.
- [ ] researcher가 week08 RAG + 도구를 tool-calling 루프로 사용한다.
- [ ] writer가 findings만 근거로 보고서를 작성한다(환각 억제 프롬프트 포함).
- [ ] 오케스트레이터가 실패 복구(폴백)와 HITL 게이트를 갖췄다.
- [ ] `/report`(raw) 엔드포인트가 동작한다. (선택/도전: `/report/graph` LangGraph 버전)
- [ ] 에이전트 간 협업 로그를 콘솔·응답에서 관찰했다.
- [ ] (과제) reviewer 에이전트로 3-에이전트 협업 + 재작성 루프를 구현했다.

---

## 다음 주 예고

**Week 12 — 통합 배포 & 몰입형 프로젝트 킥오프.** 1~11주에 걸쳐 만든 docpilot 전체(웹 + PostgreSQL + 벡터DB + LLM + Agent/Multi-Agent)를 **컨테이너화하여 Kubernetes에 통합 배포**한다. Secret으로 API 키를 주입하고, 헬스체크·리소스·로깅/모니터링을 설정한 뒤 최종 스모크 테스트로 마무리한다. 그리고 **4주 몰입형 프로젝트**의 팀 편성·주제 선정·기획 발표를 킥오프한다. → [평가와 몰입형 프로젝트](../03-평가와-몰입형-프로젝트.md)
