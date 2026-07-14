# Week 10 — 도구·데이터 연동과 MCP (Agentic AI)

> 이번 주 한 줄: `docpilot`의 도구가 **실제 세계**(외부 API·DB·파일)에 연결되고, **MCP 서버**로 표준화되어 어떤 클라이언트든 호출한다.
> docpilot 진화: week09의 장난감 도구를 **실전 연동**(REST API 호출 · PostgreSQL 조회 · 파일 읽기)으로 확장 + **가드레일**(타임아웃/재시도/입력검증) + **MCP 서버**로 도구 노출.

이번 주부터 docpilot은 응답만 하던 서비스를 넘어 **스스로 외부 작업을 수행하는 Agentic 서비스**가 된다. week09의 [단일 Agent](./week09-ai-agent-기초.md)가 실전 도구를 갖추는 주다.

---

## 학습 목표

- [ ] 도구를 **실제 외부 리소스**(REST API·DB·파일)에 연결한다.
- [ ] 신뢰성 가드레일 — **타임아웃 / 재시도 / 입력검증 / 에러 처리** 를 도구에 두른다.
- [ ] 파일·경로 도구의 **path traversal** 등 보안 위험을 막는다.
- [ ] **MCP(Model Context Protocol)** 가 무엇이고 왜 표준이 필요한지 설명한다.
- [ ] Python으로 **MCP 서버**를 만들어 docpilot 도구를 노출한다.
- [ ] **MCP 클라이언트**로 서버에 붙어 도구를 나열·호출한다.
- [ ] 이 단계가 **Agentic 서비스**임을 이해한다.

## 사전 준비

- **지난주 산출물**: week09의 `agent/tools.py`, `raw_agent.py`, `/agent` 엔드포인트.
- **DB**: week03에서 docker-compose로 띄운 PostgreSQL. 이번 주 도구는 week03의 `documents`와 별개인 **`kb_documents`** 테이블을 쓴다(아래 2단계에 시드 SQL 제공).
- **환경**: Python 3.12. API 키·DB 접속정보는 **환경변수로만**. 세팅은 [실습 환경과 기술 스택](../02-실습환경과-기술스택.md) 참고.
- **키 로딩**: `.env` + `get_settings()`를 기준으로 한다. 아래 shell `export`를 써도 python-dotenv가 `.env`를 읽어 호환된다.

```bash
cd docpilot && source .venv/bin/activate
pip install "httpx>=0.27" "tenacity>=8.3" "psycopg[binary]>=3.2" "mcp>=1.2"
```

**확인**: `python -c "import httpx, tenacity, psycopg, mcp; print('ok')"` → `ok`.

```bash
# 외부 연동에 쓸 환경변수 (예시 — 본인 환경에 맞게)
export DOCPILOT_DB_DSN="postgresql://docpilot:docpilot@localhost:5432/docpilot"
export DOCPILOT_DATA_DIR="$(pwd)/data"     # 파일 읽기 도구의 sandbox 루트
mkdir -p "$DOCPILOT_DATA_DIR"
echo "docpilot 사용 설명서: 문서를 올리면 그 내용으로 답합니다." > "$DOCPILOT_DATA_DIR/manual.txt"
```

**확인**: `cat "$DOCPILOT_DATA_DIR/manual.txt"` → 방금 쓴 문장이 보인다.

---

## 개념 (요약)

### 1. 실제 연동은 "실패한다"는 전제에서 시작한다

week09의 도구는 순수 함수라 항상 성공했다. 실제 연동은 다르다:

- **REST API**: 느려지거나(타임아웃), 5xx로 죽거나, rate limit(429)에 걸린다.
- **DB**: 커넥션이 끊기고, 잘못된 쿼리는 인젝션 위험을 낳는다.
- **파일**: 경로 조작으로 `/etc/passwd`를 읽으려는 시도(path traversal)가 온다.

Agent에서는 **인자를 LLM이 생성**하므로 위험이 더 크다. 모델이 만든 인자를 절대 신뢰하지 말고 **시스템 경계에서 검증**한다.

### 2. 가드레일 4종

| 가드레일 | 목적 | 구현 |
|---|---|---|
| **타임아웃(timeout)** | 느린 외부 호출이 전체를 멈추지 않게 | `httpx.Client(timeout=...)`, DB `statement_timeout` |
| **재시도(retry)** | 일시적 오류(네트워크·429·5xx) 회복 | `tenacity` 지수 백오프 |
| **입력검증(validation)** | LLM이 만든 인자 방어 | Pydantic 모델, 허용 목록(allowlist), 경로 정규화 |
| **에러 처리** | 실패를 **모델에게 구조화해 전달** → 회복 유도 | `{"error": "..."}` 형태로 반환(예외로 죽지 않음) |

> 핵심 원칙: **도구는 예외를 던져 프로세스를 죽이지 않고, 실패를 "관찰 가능한 결과"로 모델에 돌려준다.** 그래야 agent가 다른 도구로 우회하거나 사용자에게 상황을 설명할 수 있다.

### 3. MCP — 왜 표준이 필요한가

week09에서 도구를 붙일 때, 우리는 OpenAI 전용 JSON Schema로 정의하고 우리 코드에 하드코딩했다. 문제:

- 도구를 **Gemini·Claude·LangGraph**에 다시 쓰려면 각자 포맷으로 재작성해야 한다. (N개 모델 × M개 도구 = N×M 통합 지옥)
- 도구가 **다른 팀·다른 서비스**에 있으면 공유가 어렵다.

**MCP(Model Context Protocol)** 는 "AI 애플리케이션과 도구/데이터 소스를 잇는 표준 프로토콜"이다. **USB-C에 비유**된다: 한 번 MCP 서버로 만들어 두면, MCP를 지원하는 **모든 클라이언트**(Claude Desktop, IDE, 커스텀 agent 등)가 같은 방식으로 도구를 발견·호출한다.

```
[MCP 없이]  각 앱마다 도구를 따로 연결        [MCP]  표준 서버 하나에 모두 연결
  App A ─┐                                    App A ─┐
  App B ─┼─▶ 도구들 (각각 개별 통합)           App B ─┼─▶ [MCP Server] ─▶ 도구/DB/파일
  App C ─┘                                    App C ─┘   (JSON-RPC 표준)
```

MCP 서버는 3가지를 노출한다: **Tools**(실행 가능한 함수), **Resources**(읽을 수 있는 데이터), **Prompts**(재사용 프롬프트 템플릿). 이번 주는 **Tools**에 집중한다. 전송(transport)은 로컬은 **stdio**, 원격은 HTTP를 쓴다.

---

## 실습: 단계별 따라하기

```
docpilot/
├── agent/
│   ├── tools.py            # week09
│   ├── real_tools.py       # 1~3부: 실전 도구 + 가드레일   ← 이번 주
│   └── raw_agent.py        # week09 (실전 도구 추가 등록)
├── mcp_server/
│   └── server.py           # 4부: MCP 서버                 ← 이번 주
└── mcp_client_demo.py      # 5부: MCP 클라이언트 데모       ← 이번 주
```

```bash
mkdir -p mcp_server
```

---

### 1부 · 외부 REST API 도구 (타임아웃 + 재시도)

#### 1단계. 환율 조회 도구

`agent/real_tools.py`를 만들고, 키가 필요 없는 공개 API(`frankfurter.app`)로 환율을 조회한다. **타임아웃**과 **지수 백오프 재시도**를 건다.

```python
# agent/real_tools.py
"""실전 연동 도구 + 가드레일 (REST API / DB / 파일)."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# --- 공통 상수 (매직 넘버 대신 이름 부여) -----------------------------------
HTTP_TIMEOUT_SECONDS = 5.0
MAX_RETRIES = 3
ALLOWED_CURRENCIES = {"USD", "EUR", "KRW", "JPY", "GBP", "CNY"}


class ToolError(Exception):
    """도구 내부 오류. 최종적으로는 {'error': ...}로 변환해 모델에 돌려준다."""


# --- 도구 1: 외부 REST API (환율) ------------------------------------------
@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)
def _fetch_rate(base: str, target: str) -> float:
    url = "https://api.frankfurter.app/latest"
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        resp = client.get(url, params={"from": base, "to": target})
        resp.raise_for_status()          # 4xx/5xx면 예외 → tenacity가 재시도
        data = resp.json()
    rate = data.get("rates", {}).get(target)
    if rate is None:
        raise ToolError(f"환율 응답에 {target}가 없습니다.")
    return float(rate)


def get_exchange_rate(base: str, target: str) -> dict:
    """base 통화 1단위의 target 통화 환율을 반환. 예: base='USD', target='KRW'."""
    base, target = base.upper(), target.upper()
    # 입력검증: 허용된 통화만 (LLM이 만든 인자 방어)
    if base not in ALLOWED_CURRENCIES or target not in ALLOWED_CURRENCIES:
        return {"error": f"지원하지 않는 통화입니다. 허용: {sorted(ALLOWED_CURRENCIES)}"}
    try:
        rate = _fetch_rate(base, target)
        return {"base": base, "target": target, "rate": rate}
    except Exception as exc:  # 재시도 소진·타임아웃 등 → 구조화된 에러로 반환
        return {"error": f"환율 조회 실패: {exc}"}
```

**확인**:

```bash
python -c "from agent.real_tools import get_exchange_rate; print(get_exchange_rate('USD','KRW')); print(get_exchange_rate('USD','BTC'))"
```

기대 출력(환율 값은 변동):

```
{'base': 'USD', 'target': 'KRW', 'rate': 1350.4}
{'error': "지원하지 않는 통화입니다. 허용: ['CNY', 'EUR', 'GBP', 'JPY', 'KRW', 'USD']"}
```

> **왜 에러를 dict로?** 예외를 그대로 던지면 agent 루프가 죽는다. `{"error": ...}`로 돌려주면 모델이 "환율 조회에 실패했어요"라고 사용자에게 설명하거나 다른 방법을 시도할 수 있다.

---

### 2부 · DB 조회 도구 (파라미터 바인딩으로 인젝션 방어)

#### 2단계. (필요 시) DB 시드

이번 주 도구용 `kb_documents` 테이블을 시드한다. week03의 `documents`(다른 스키마)와 이름이 겹치지 않도록 **별도 테이블 이름**을 쓴다:

```sql
-- seed.sql
CREATE TABLE IF NOT EXISTS kb_documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO kb_documents (title, content) VALUES
  ('환불 정책', '구매 후 7일 이내 전액 환불이 가능합니다.'),
  ('요금제 안내', 'docpilot 프리미엄 요금제는 월 29,000원입니다.'),
  ('세금 정책', 'docpilot의 부가세율은 10%로 계산합니다.');
```

```bash
psql "$DOCPILOT_DB_DSN" -f seed.sql
```

**확인**: `psql "$DOCPILOT_DB_DSN" -c "SELECT count(*) FROM kb_documents;"` → `3` 이상.

#### 3단계. DB 조회 도구

`agent/real_tools.py`에 이어서 추가한다. **절대 문자열을 이어 붙이지 말고 파라미터 바인딩**을 쓴다.

```python
# agent/real_tools.py (이어서 추가)
import psycopg

DB_DSN = os.getenv("DOCPILOT_DB_DSN", "postgresql://docpilot:docpilot@localhost:5432/docpilot")
DB_TIMEOUT_MS = 3000
MAX_DB_ROWS = 20


def search_documents_db(keyword: str, limit: int = 5) -> dict:
    """kb_documents 테이블에서 제목/본문에 keyword가 포함된 행을 검색한다."""
    # 입력검증
    keyword = (keyword or "").strip()
    if not keyword:
        return {"error": "keyword가 비어 있습니다."}
    limit = max(1, min(int(limit), MAX_DB_ROWS))  # 상한/하한 clamp
    try:
        # statement_timeout: 느린 쿼리가 전체를 막지 않게 (DB측 타임아웃)
        with psycopg.connect(DB_DSN, connect_timeout=3,
                             options=f"-c statement_timeout={DB_TIMEOUT_MS}") as conn:
            with conn.cursor() as cur:
                # %s 파라미터 바인딩 → SQL 인젝션 원천 차단. f-string 금지!
                cur.execute(
                    """
                    SELECT id, title, content
                    FROM kb_documents
                    WHERE title ILIKE %(kw)s OR content ILIKE %(kw)s
                    ORDER BY id
                    LIMIT %(lim)s
                    """,
                    {"kw": f"%{keyword}%", "lim": limit},
                )
                rows = cur.fetchall()
        return {"count": len(rows),
                "rows": [{"id": r[0], "title": r[1], "content": r[2]} for r in rows]}
    except Exception as exc:
        return {"error": f"DB 조회 실패: {exc}"}
```

**확인**:

```bash
python -c "from agent.real_tools import search_documents_db; import json; print(json.dumps(search_documents_db('환불'), ensure_ascii=False))"
```

기대 출력:

```json
{"count": 1, "rows": [{"id": 1, "title": "환불 정책", "content": "구매 후 7일 이내 전액 환불이 가능합니다."}]}
```

> **인젝션 방어의 핵심**: `keyword`가 `'; DROP TABLE documents; --` 여도 파라미터 바인딩이면 값으로만 취급되어 안전하다. **LLM이 만든 문자열을 SQL에 직접 넣지 않는다.**

---

### 3부 · 파일 읽기 도구 (path traversal 방어)

#### 4단계. sandbox 안에서만 읽는 파일 도구

`agent/real_tools.py`에 이어서 추가한다. `DOCPILOT_DATA_DIR` **바깥은 절대 못 읽게** 경로를 정규화해 검증한다.

```python
# agent/real_tools.py (이어서 추가)
DATA_DIR = Path(os.getenv("DOCPILOT_DATA_DIR", "./data")).resolve()
MAX_FILE_BYTES = 100_000


def read_file(relative_path: str) -> dict:
    """DOCPILOT_DATA_DIR 내부의 텍스트 파일을 읽는다. 바깥 경로는 거부한다."""
    try:
        # 경로 정규화 후 sandbox 루트 안에 있는지 검증 (../ 탈출 차단)
        target = (DATA_DIR / relative_path).resolve()
        if not target.is_relative_to(DATA_DIR):   # Python 3.9+
            return {"error": "허용된 데이터 디렉터리 밖의 경로입니다."}
        if not target.is_file():
            return {"error": f"파일이 없습니다: {relative_path}"}
        if target.stat().st_size > MAX_FILE_BYTES:
            return {"error": "파일이 너무 큽니다(100KB 초과)."}
        return {"path": relative_path, "content": target.read_text(encoding="utf-8")}
    except Exception as exc:
        return {"error": f"파일 읽기 실패: {exc}"}


# --- 실전 도구 레지스트리 + 스키마 (week09 형식과 동일) ----------------------
REAL_TOOL_REGISTRY = {
    "get_exchange_rate": get_exchange_rate,
    "search_documents_db": search_documents_db,
    "read_file": read_file,
}

REAL_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "두 통화 간 최신 환율을 조회한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base": {"type": "string", "description": "기준 통화 (예: USD)"},
                    "target": {"type": "string", "description": "대상 통화 (예: KRW)"},
                },
                "required": ["base", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents_db",
            "description": "docpilot DB의 kb_documents 테이블을 키워드로 검색한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "검색 키워드"},
                    "limit": {"type": "integer", "description": "최대 행 수(기본 5)"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "docpilot 데이터 디렉터리 안의 텍스트 파일을 읽는다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string", "description": "데이터 디렉터리 기준 상대 경로 (예: manual.txt)"},
                },
                "required": ["relative_path"],
            },
        },
    },
]
```

**확인**: 정상 읽기와 traversal 차단을 모두 검증한다.

```bash
python -c "from agent.real_tools import read_file; print(read_file('manual.txt')); print(read_file('../../../etc/passwd'))"
```

기대 출력:

```
{'path': 'manual.txt', 'content': 'docpilot 사용 설명서: 문서를 올리면 그 내용으로 답합니다.\n'}
{'error': '허용된 데이터 디렉터리 밖의 경로입니다.'}
```

> **관찰**: `../../../etc/passwd`가 정규화 검증에서 막혔다. 파일·경로를 다루는 모든 도구는 이런 sandbox 검증이 필수다.

#### 5단계. agent에 실전 도구 등록

week09의 `agent/raw_agent.py`에서 도구를 합친다. 상단 import와 create 호출부만 수정한다.

```python
# agent/raw_agent.py (수정)
from agent.tools import TOOL_REGISTRY, TOOL_SCHEMAS
from agent.real_tools import REAL_TOOL_REGISTRY, REAL_TOOL_SCHEMAS

# 두 도구 세트를 병합
TOOL_REGISTRY = {**TOOL_REGISTRY, **REAL_TOOL_REGISTRY}
TOOL_SCHEMAS = [*TOOL_SCHEMAS, *REAL_TOOL_SCHEMAS]
```

**확인**: 실전 도구를 쓰게 하는 질의로 `/agent`를 호출한다(week09의 서버가 떠 있어야 함).

```bash
curl -s -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"query": "kb_documents 테이블에서 요금제를 찾아 그 금액을 USD로 환산하면 얼마야?"}' | python -m json.tool
```

기대 출력(요약): `trace`에 `search_documents_db` → `get_exchange_rate` → `calculator`가 순서대로 찍히고, `answer`에 환산 금액이 나온다. **여러 실전 도구를 스스로 엮어 작업을 수행** = Agentic 서비스.

---

### 4부 · MCP 서버 만들기

#### 6단계. FastMCP로 docpilot 도구 노출

`mcp_server/server.py`를 만든다. MCP Python SDK의 `FastMCP`는 데코레이터로 도구를 선언하면 프로토콜 처리를 대신해 준다.

```python
# mcp_server/server.py
"""docpilot 도구를 MCP로 노출하는 서버 (stdio transport)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agent.real_tools import get_exchange_rate, read_file, search_documents_db

mcp = FastMCP("docpilot-tools")


@mcp.tool()
def exchange_rate(base: str, target: str) -> dict:
    """두 통화 간 최신 환율을 조회한다. 예: base='USD', target='KRW'."""
    return get_exchange_rate(base, target)


@mcp.tool()
def documents_search(keyword: str, limit: int = 5) -> dict:
    """docpilot DB의 kb_documents 테이블을 키워드로 검색한다."""
    return search_documents_db(keyword, limit)


@mcp.tool()
def data_file(relative_path: str) -> dict:
    """docpilot 데이터 디렉터리 안의 텍스트 파일을 읽는다."""
    return read_file(relative_path)


if __name__ == "__main__":
    # stdio transport로 실행 (로컬 클라이언트가 자식 프로세스로 띄운다)
    mcp.run(transport="stdio")
```

**확인**: MCP Inspector로 서버를 눈으로 확인한다(Node 필요).

```bash
# 서버가 뜨고 도구 목록이 보이는지 브라우저 UI로 확인
npx @modelcontextprotocol/inspector python -m mcp_server.server
```

Inspector 웹 UI의 **Tools** 탭에 `exchange_rate`, `documents_search`, `data_file` 3개가 나타나고, 각 도구를 폼으로 직접 호출해 결과를 볼 수 있다. (Inspector 없이 넘어가도 5부에서 코드로 확인한다.)

> `@mcp.tool()` 하나로 도구의 이름·설명(docstring)·파라미터 스키마(타입 힌트)가 **자동 생성**된다. week09에서 손으로 쓰던 JSON Schema를 SDK가 대신 만들어 준다.

---

### 5부 · MCP 클라이언트로 호출 확인

#### 7단계. Python 클라이언트

`mcp_client_demo.py`를 만든다. 서버를 자식 프로세스로 띄우고(stdio), 도구를 나열·호출한다.

```python
# mcp_client_demo.py
"""MCP 클라이언트: docpilot MCP 서버에 붙어 도구를 나열·호출한다."""
from __future__ import annotations

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 서버를 어떻게 띄울지 지정 (여기서는 파이썬 모듈로 실행)
SERVER = StdioServerParameters(command="python", args=["-m", "mcp_server.server"])


async def main() -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # (1) 도구 목록 조회 — 표준 프로토콜로 발견(discovery)
            tools = await session.list_tools()
            print("=== 사용 가능한 도구 ===")
            for t in tools.tools:
                print(f"- {t.name}: {t.description}")

            # (2) 도구 호출
            print("\n=== documents_search('요금제') ===")
            r1 = await session.call_tool("documents_search", {"keyword": "요금제"})
            print(r1.content[0].text)

            print("\n=== exchange_rate('USD','KRW') ===")
            r2 = await session.call_tool("exchange_rate", {"base": "USD", "target": "KRW"})
            print(r2.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
```

**확인**:

```bash
python mcp_client_demo.py
```

기대 출력(요약):

```
=== 사용 가능한 도구 ===
- exchange_rate: 두 통화 간 최신 환율을 조회한다. 예: base='USD', target='KRW'.
- documents_search: docpilot DB의 kb_documents 테이블을 키워드로 검색한다.
- data_file: docpilot 데이터 디렉터리 안의 텍스트 파일을 읽는다.

=== documents_search('요금제') ===
{"count": 1, "rows": [{"id": 2, "title": "요금제 안내", "content": "docpilot 프리미엄 요금제는 월 29,000원입니다."}]}

=== exchange_rate('USD','KRW') ===
{"base": "USD", "target": "KRW", "rate": 1350.4}
```

> **이것이 표준화의 힘**: 클라이언트는 우리 도구의 내부 구현을 전혀 몰라도 `list_tools()` 로 발견하고 `call_tool()` 로 호출했다. 같은 서버를 **Claude Desktop**에도 붙일 수 있다.

#### 8단계. Claude Desktop에 연결 — **선택/도전**

> **선택/도전**: 필수 경로는 7단계(Python MCP 클라이언트)에서 끝난다. Claude Desktop 연동은 외부 앱 설정이 필요한 심화이며, 단일 세션 부담을 줄이려면 건너뛰어도 무방하다.

Claude Desktop의 설정 파일(`claude_desktop_config.json`)에 서버를 등록하면, 채팅 중 docpilot 도구를 직접 쓸 수 있다.

```json
{
  "mcpServers": {
    "docpilot-tools": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/절대경로/docpilot",
      "env": {
        "DOCPILOT_DB_DSN": "postgresql://docpilot:docpilot@localhost:5432/docpilot",
        "DOCPILOT_DATA_DIR": "/절대경로/docpilot/data"
      }
    }
  }
}
```

**확인**: Claude Desktop 재시작 후 입력창의 도구(🔨) 아이콘에 `docpilot-tools`가 보이고, "kb_documents에서 환불 정책 찾아줘"라고 하면 `documents_search`가 호출된다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `httpx.ConnectTimeout` | 외부 API 지연·네트워크 | `HTTP_TIMEOUT_SECONDS` 조정, 재시도 로그 확인. 프록시 환경이면 `HTTPS_PROXY` 설정 |
| 환율 도구가 매번 재시도만 하다 실패 | API 다운/차단 | `{"error": ...}`가 정상 동작. 오프라인이면 fallback 값 사용하도록 확장 |
| `psycopg.OperationalError` | DB 미기동·DSN 오류 | week03 compose로 DB 기동, `psql "$DOCPILOT_DB_DSN" -c '\l'`로 접속 확인 |
| DB 조회에 원치 않는 행 다수 | `ILIKE '%kw%'` 광범위 매칭 | 키워드 구체화, `limit` 하향 |
| `read_file`이 정상 파일도 거부 | `DOCPILOT_DATA_DIR` 미설정/상대경로 | 환경변수를 절대경로로 export, `.resolve()` 확인 |
| MCP 클라이언트가 멈춤/무응답 | 서버 `command`/`cwd` 오류, import 실패 | 먼저 `python -m mcp_server.server`가 단독 기동되는지 확인(에러는 stderr로) |
| Inspector `npx` 실패 | Node 미설치 | Node 18+ 설치, 또는 5부 Python 클라이언트로 대체 |
| `ModuleNotFoundError: mcp` | 미설치/venv 불일치 | `pip install "mcp>=1.2"`, venv activate 확인 |

---

## 이번 주 과제

**제출물**: `docpilot` 저장소 커밋/PR.

1. **실전 도구 1개 추가**: 아래 중 하나를 `agent/real_tools.py`에 가드레일 포함으로 구현한다.
   - 공개 REST API 하나 더 연동(예: 우편번호/공휴일 API) — 타임아웃 + 재시도 필수.
   - `write_file` 도구 — 단, sandbox 검증 + 확장자 allowlist + 크기 제한 필수.
2. 그 도구를 **MCP 서버(`mcp_server/server.py`)에도 `@mcp.tool()`로 노출**하고, `mcp_client_demo.py`로 호출한 로그를 제출한다.
3. **가드레일 검증 3종**을 캡처로 제출: (a) 타임아웃/재시도 동작, (b) 잘못된 입력이 `{"error": ...}`로 반환, (c) path traversal 또는 인젝션 시도가 차단.
4. `README`에 "MCP가 없을 때의 통합 비용(N×M)과 MCP가 그것을 어떻게 줄이는지"를 3줄 이상 정리.

**채점 포인트**: 모든 도구가 예외로 죽지 않고 `{"error": ...}`로 실패를 반환하는가 / LLM이 만든 인자를 검증하는가 / MCP 서버-클라이언트 왕복이 동작하는가.

---

## 체크리스트

- [ ] `get_exchange_rate`가 타임아웃·재시도·통화 allowlist를 갖추고 동작한다.
- [ ] `search_documents_db`가 **파라미터 바인딩**으로 DB를 조회한다(인젝션 방어).
- [ ] `read_file`이 sandbox 밖 경로(`../`)를 거부한다.
- [ ] 모든 도구가 실패 시 예외가 아니라 `{"error": ...}`를 반환한다.
- [ ] agent가 실전 도구 여러 개를 스스로 엮어 답한다(trace 확인).
- [ ] MCP 서버가 도구 3개를 노출한다(Inspector 또는 클라이언트로 확인).
- [ ] Python MCP 클라이언트가 `list_tools`/`call_tool`로 왕복한다.
- [ ] API 키·DB 접속정보가 코드에 없고 환경변수로만 주입된다.

---

## 다음 주 예고

week11에서는 **하나의 agent를 넘어 여러 agent가 협업**한다. `researcher`(자료 조사) + `writer`(보고서 작성)가 역할을 나눠, 이번 주에 만든 도구·MCP 리소스를 함께 쓰며 하나의 결과물을 만든다. 오케스트레이터/워커 패턴, agent 간 메시지 전달, 상태·메모리 공유, 실패 복구와 휴먼 인 더 루프를 다룬다. → week11 — Multi-Agent 시스템
