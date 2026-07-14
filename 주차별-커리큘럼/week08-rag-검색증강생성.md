# Week 8 — RAG 검색증강생성 (docpilot `/ask` 완성) · **Block 2 미니 과제**

> 이번 주 한 줄: 문서를 임베딩해 벡터DB에 넣고, 질문과 관련된 조각만 찾아 LLM에 넣어 **근거 있는 답**을 만든다.
> docpilot 진화: 업로드 문서 청킹 → 임베딩(week07) → 벡터DB(Chroma 기본 / pgvector 대안) → 검색 → LLM(week06) 컨텍스트 주입 → `/ask` 답변.

> ⚠️ **이번 주는 Block 2(AI 서비스)의 미니 과제다.** week06(LLM 생성) + week07(임베딩/멀티모달)에서 만든 부품을 **하나의 파이프라인**으로 조립해 "문서 기반으로 답하는 docpilot"의 핵심을 완성한다. Block 2 평가는 이 결과물을 기준으로 한다.

---

## 학습 목표

- [ ] 임베딩·유사도, 벡터DB, 청킹·검색의 역할을 설명할 수 있다.
- [ ] RAG 파이프라인 4단계(인덱싱 → 검색 → 컨텍스트 주입 → 생성)를 이해한다.
- [ ] 문서를 청킹해 임베딩하고 Chroma에 저장하는 **인덱싱 스크립트**를 만든다.
- [ ] 질의 시 유사 청크를 검색해 LLM에 주입하는 `/ask`를 구현한다.
- [ ] "왜 RAG가 필요한가"(할루시네이션·최신성·비용·출처)를 근거로 설명한다.
- [ ] (대안) pgvector로도 같은 검색을 할 수 있음을 안다.

---

## 사전 준비

- week06(`/chat`), week07(`/embed`)이 동작하는 docpilot. [week06](./week06-llm-api-연동.md) / [week07](./week07-멀티모달과-huggingface.md).
- LLM 프로바이더 키(OpenAI/Gemini) 또는 Ollama. (생성 단계에 필요)
- (pgvector 대안 시) week03에서 띄운 PostgreSQL. [week03](./week03-docker-compose-멀티컨테이너.md).

---

## 개념 (요약)

### 1) 왜 RAG인가

LLM은 학습 시점 지식만 알고, 우리 회사/수업 문서는 모른다. 그냥 물으면 **지어낸다(할루시네이션)**. 문서를 통째로 프롬프트에 넣으면 **컨텍스트 한도 초과 + 비용 폭발**. 그래서:

> **RAG(Retrieval-Augmented Generation)** = "질문과 관련된 문서 조각만 찾아서(Retrieval) 프롬프트에 넣고(Augment) 답을 만든다(Generation)."

이점: (1) 우리 문서 기반 정확도 ↑, (2) 최신 문서 반영, (3) 필요한 조각만 넣어 비용 ↓, (4) **출처 표시** 가능.

### 2) 파이프라인 4단계

```
[인덱싱: 사전 1회]
  문서 → (청킹) 조각들 → (임베딩) 벡터들 → 벡터DB에 저장

[질의: 매 질문]
  질문 → (임베딩) 질문 벡터 → (검색) 벡터DB에서 top-k 유사 조각
       → (주입) system+조각들+질문으로 프롬프트 구성 → (생성) LLM → 답 + 출처
```

### 3) 청킹(chunking)

문서를 검색 단위로 자르는 것. 너무 크면 관련 없는 내용까지 딸려오고, 너무 작으면 맥락이 끊긴다. 실무 기본값: **문자 300~800자, 겹침(overlap) 10~20%**. 겹침은 경계에서 문장이 잘려 뜻이 사라지는 걸 막는다.

### 4) 벡터DB

임베딩 벡터를 저장하고 "가장 가까운 k개"를 빠르게 찾아주는 DB.

| 옵션 | 특징 | 이번 주 |
|---|---|---|
| **Chroma** | 파이썬 임베디드, 파일로 로컬 저장, 세팅 간단 | **기본** |
| **pgvector** | PostgreSQL 확장, 기존 DB(week03) 재사용, SQL로 조회 | **대안** |

---

## 실습: 단계별 따라하기

흐름:
- **1부**: Chroma 설치 + 청킹 유틸.
- **2부**: 인덱싱 스크립트(문서 → 청크 → 임베딩 → 저장) + `/documents/{id}/index`.
- **3부**: 검색 + `/ask`(컨텍스트 주입 + 생성 + 출처).
- **4부(대안)**: pgvector로 같은 검색.

전제: week07의 `app/embeddings.py`(`embed`)와 week06의 `app/llm.py`(`complete`/`build_messages`)를 그대로 재사용한다.

### 1부. 준비

#### 1단계. Chroma 설치

무엇을/왜: 로컬 벡터DB. 별도 서버 없이 파일로 저장된다.

```bash
pip install "chromadb>=0.5" "pypdf>=4.0"
```

`requirements.txt`에 추가:

```text
# requirements.txt (추가)
chromadb>=0.5
pypdf>=4.0
```

**확인**:

```bash
python -c "import chromadb; print('chroma', chromadb.__version__)"
```

기대 출력: `chroma 0.5.x`.

`.env`에 저장 경로/검색 파라미터 추가:

```bash
# RAG
CHROMA_DIR=./chroma_data
RAG_COLLECTION=docpilot
CHUNK_SIZE=600
CHUNK_OVERLAP=100
TOP_K=4
```

`app/config.py`의 `Settings`에 추가:

```python
# app/config.py  (Settings 안에 추가)
    # RAG
    chroma_dir: str = "./chroma_data"
    rag_collection: str = "docpilot"
    chunk_size: int = 600
    chunk_overlap: int = 100
    top_k: int = 4
```

**확인**:

```bash
python -c "from app.config import get_settings; s=get_settings(); print(s.chroma_dir, s.chunk_size, s.top_k)"
```

기대 출력: `./chroma_data 600 4`.

#### 2단계. 청킹 유틸 (`app/chunking.py`)

무엇을/왜: 긴 텍스트를 겹침 있는 조각으로 자른다. 문단 경계를 최대한 존중한다.

```python
# app/chunking.py
from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> list[str]:
    """문자 기준 슬라이딩 윈도로 텍스트를 자른다(겹침 포함)."""
    text = " ".join(text.split())  # 공백/개행 정규화
    if not text:
        return []
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += step
    return chunks
```

**확인**:

```bash
python -c "
from app.chunking import chunk_text
c = chunk_text('가나다라마바사아자차카타파하' * 60, chunk_size=100, overlap=20)
print('청크 수:', len(c), '| 첫 청크 길이:', len(c[0]))
"
```

기대 출력: 청크가 여러 개로 쪼개지고 첫 청크 길이가 100이면 성공.

---

### 2부. 인덱싱 (문서 → 벡터DB)

#### 3단계. 벡터스토어 래퍼 (`app/vectorstore.py`)

무엇을/왜: Chroma 컬렉션에 조각을 저장/검색하는 얇은 래퍼. 임베딩은 week07 `embed`를 그대로 쓴다(인덱싱·질의 모델 일치가 핵심).

```python
# app/vectorstore.py
from __future__ import annotations

from functools import lru_cache

import chromadb

from app.config import get_settings
from app.embeddings import embed


@lru_cache
def get_collection():
    """디스크에 저장되는 Chroma 컬렉션을 얻는다(1회 초기화)."""
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    # 임베딩을 우리가 직접 계산해 넣으므로 embedding_function은 지정하지 않는다.
    return client.get_or_create_collection(
        name=settings.rag_collection,
        metadata={"hnsw:space": "cosine"},  # 코사인 거리
    )


def add_chunks(doc_id: str, chunks: list[str], source: str) -> int:
    """조각들을 임베딩해 컬렉션에 upsert. 저장한 개수를 반환."""
    if not chunks:
        return 0
    vectors = embed(chunks)  # (n, dim), 정규화됨
    ids = [f"{doc_id}:{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "source": source, "chunk_index": i} for i in range(len(chunks))]
    get_collection().upsert(
        ids=ids,
        documents=chunks,
        embeddings=vectors.tolist(),
        metadatas=metadatas,
    )
    return len(chunks)


def search(query: str, top_k: int | None = None) -> list[dict]:
    """질문을 임베딩해 가장 가까운 조각 top_k를 반환."""
    settings = get_settings()
    k = top_k or settings.top_k
    q_vec = embed([query])[0]
    res = get_collection().query(
        query_embeddings=[q_vec.tolist()],
        n_results=k,
    )
    # Chroma 결과를 평탄한 리스트로 정리
    hits: list[dict] = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({
            "text": doc,
            "source": meta.get("source"),
            "chunk_index": meta.get("chunk_index"),
            "score": round(1 - dist, 4),  # cosine distance → similarity 근사
        })
    return hits
```

**확인**:

```bash
python -c "from app.vectorstore import get_collection; print('collection ok:', get_collection().name)"
```

기대 출력: `collection ok: docpilot`. (실행 후 `./chroma_data/`가 생긴다.)

#### 4단계. 문서 로더 (`app/loader.py`)

무엇을/왜: `.txt`/`.md`/`.pdf`에서 순수 텍스트를 뽑는다.

```python
# app/loader.py
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def load_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    raise ValueError(f"unsupported file type: {suffix}")
```

#### 5단계. 인덱싱 스크립트 (`scripts/index_docs.py`)

무엇을/왜: 폴더의 문서들을 한 번에 청킹·임베딩·저장하는 CLI. RAG의 "사전 1회" 단계.

```python
# scripts/index_docs.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가(스크립트를 어디서 실행하든 app 패키지를 찾도록)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.chunking import chunk_text
from app.loader import load_text
from app.vectorstore import add_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Index documents into the vector store")
    parser.add_argument("path", help="파일 또는 폴더 경로")
    args = parser.parse_args()

    settings = get_settings()
    target = Path(args.path)
    files = [target] if target.is_file() else sorted(
        p for p in target.rglob("*") if p.suffix.lower() in {".txt", ".md", ".pdf"}
    )
    if not files:
        print("no documents found")
        return

    total = 0
    for f in files:
        text = load_text(f)
        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        n = add_chunks(doc_id=f.stem, chunks=chunks, source=f.name)
        total += n
        print(f"indexed {f.name}: {n} chunks")
    print(f"done. total chunks = {total}")


if __name__ == "__main__":
    main()
```

샘플 문서를 만들어 인덱싱한다:

```bash
mkdir -p sample_docs
cat > sample_docs/docpilot.md <<'EOF'
# docpilot 소개
docpilot은 문서 기반 AI 도우미다. 사용자가 문서를 업로드하면 그 내용으로 질문에 답한다.
배포는 Kubernetes에 Deployment와 Service로 이루어진다. 롤아웃과 롤백을 지원한다.
RAG는 질문과 관련된 문서 조각을 검색해 LLM에 넣어 근거 있는 답을 만든다.
임베딩 모델로는 all-MiniLM-L6-v2를 사용하며 벡터 차원은 384이다.
EOF

python scripts/index_docs.py sample_docs
```

**확인**: `indexed docpilot.md: N chunks` / `done. total chunks = N` 출력.

```bash
python -c "from app.vectorstore import get_collection; print('저장된 조각 수:', get_collection().count())"
```

기대 출력: `저장된 조각 수: N` (0보다 큼).

#### 6단계. (선택) 업로드 문서 즉시 인덱싱 엔드포인트

무엇을/왜: week03의 `/documents` 업로드 흐름과 연결해, 업로드 즉시 인덱싱한다.

`app/main.py`에 추가:

```python
# app/main.py  (추가)
from app.chunking import chunk_text
from app.loader import load_text
from app.vectorstore import add_chunks
import tempfile, os


@app.post("/documents/index")
async def index_uploaded(file: UploadFile = File(...)) -> dict:
    """문서를 업로드하면 청킹·임베딩해 벡터DB에 저장한다."""
    from app.config import get_settings
    settings = get_settings()

    suffix = os.path.splitext(file.filename or "doc.txt")[1].lower()
    if suffix not in {".txt", ".md", ".pdf"}:
        raise HTTPException(status_code=415, detail=f"unsupported type: {suffix}")

    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        text = load_text(tmp.name)

    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    n = add_chunks(doc_id=(file.filename or "doc"), chunks=chunks, source=file.filename or "doc")
    return {"filename": file.filename, "chunks_indexed": n}
```

> `UploadFile`, `File`, `HTTPException`는 week07에서 이미 import했다. 없으면 `from fastapi import UploadFile, File, HTTPException` 추가.

```bash
curl -s -X POST http://localhost:8000/documents/index \
  -F "file=@sample_docs/docpilot.md;type=text/markdown" | python -m json.tool
```

**확인**: `"chunks_indexed": N` (N>0).

---

### 3부. 검색 + 생성 = `/ask`

#### 7단계. RAG 조립 (`app/rag.py`)

무엇을/왜: 검색된 조각으로 프롬프트를 만들고 LLM에 넣는다. "컨텍스트에 없으면 모른다고 답하라"는 규칙을 시스템 프롬프트에 넣어 할루시네이션을 억제한다.

```python
# app/rag.py
from __future__ import annotations

from app import llm
from app.vectorstore import search

RAG_SYSTEM = (
    "You are docpilot, a document-grounded assistant. "
    "Answer ONLY using the provided context. "
    "If the answer is not in the context, say '문서에서 근거를 찾지 못했습니다.' in Korean. "
    "Cite sources by their [source] tag. Answer in Korean."
)


def build_context(hits: list[dict]) -> str:
    """검색 결과를 프롬프트에 넣을 컨텍스트 블록으로 만든다."""
    blocks = []
    for h in hits:
        blocks.append(f"[source: {h['source']} #{h['chunk_index']}]\n{h['text']}")
    return "\n\n---\n\n".join(blocks)


async def answer(question: str, top_k: int | None = None) -> dict:
    hits = search(question, top_k=top_k)
    if not hits:
        return {"answer": "인덱싱된 문서가 없습니다. 먼저 문서를 인덱싱하세요.", "sources": []}

    context = build_context(hits)
    user_prompt = (
        f"컨텍스트:\n{context}\n\n"
        f"질문: {question}\n\n"
        "위 컨텍스트만 근거로 답하고, 사용한 출처를 밝혀줘."
    )
    messages = llm.build_messages(user_prompt, system=RAG_SYSTEM)
    reply = await llm.complete(messages, temperature=0.1)  # 사실 답변이므로 낮게

    sources = [{"source": h["source"], "chunk_index": h["chunk_index"], "score": h["score"]} for h in hits]
    return {"answer": reply, "sources": sources}
```

#### 8단계. `/ask` 엔드포인트

무엇을/왜: 사용자 질문 → 검색증강 답변 + 출처를 반환한다. docpilot의 핵심 기능.

`app/main.py`에 추가:

```python
# app/main.py  (추가)
from app import rag


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


@app.post("/ask")
async def ask(req: AskRequest) -> dict:
    """문서 기반(RAG) 질의응답. 답변 + 출처를 반환한다."""
    return await rag.answer(req.question, top_k=req.top_k)
```

> `BaseModel`, `Field`는 week06/07에서 import됨. 없으면 `from pydantic import BaseModel, Field` 추가.

서버를 켜고 물어본다:

```bash
uvicorn app.main:app --reload
```

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "docpilot은 어떤 임베딩 모델을 쓰고 벡터 차원은 몇 이야?"}' \
  | python -m json.tool
```

**확인**: 아래처럼 문서에 근거한 답과 출처가 나온다.

```json
{
    "answer": "docpilot은 all-MiniLM-L6-v2 임베딩 모델을 사용하며 벡터 차원은 384입니다. [source: docpilot.md]",
    "sources": [
        {"source": "docpilot.md", "chunk_index": 0, "score": 0.71}
    ]
}
```

이제 **문서에 없는** 것을 물어 할루시네이션 억제를 확인한다:

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "docpilot의 월 구독 요금은 얼마야?"}' | python -m json.tool
```

**확인**: `"문서에서 근거를 찾지 못했습니다."` 류의 답. → 모르면 지어내지 않고 솔직히 답한다.

#### 9단계. 검색만 따로 확인 (`/search`, 선택·디버깅용)

무엇을/왜: 생성 없이 "무엇이 검색됐는지"만 보면 RAG 품질을 빠르게 진단할 수 있다.

```python
# app/main.py  (추가)
from app.vectorstore import search as vs_search


@app.get("/search")
async def search_endpoint(q: str, top_k: int = 4) -> dict:
    return {"query": q, "hits": vs_search(q, top_k=top_k)}
```

```bash
curl -s "http://localhost:8000/search?q=배포는%20어떻게%20하나&top_k=2" | python -m json.tool
```

**확인**: 배포 관련 조각이 상위에 `score`와 함께 나온다. → 검색이 의미 기반으로 동작.

---

### 4부. (대안) pgvector로 검색하기

무엇을/왜: 이미 PostgreSQL(week03)을 쓴다면 별도 벡터DB 없이 SQL로 검색할 수 있다. 운영 단순화·트랜잭션 일관성이 장점.

#### 10단계. pgvector 확장 + 테이블

week03의 `docker-compose.yml`에서 DB 이미지를 `pgvector/pgvector:pg16`으로 바꾸면 확장이 포함된다. 그 후:

```sql
-- psql로 접속해 실행
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS doc_chunks (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      TEXT NOT NULL,
    source      TEXT NOT NULL,
    chunk_index INT  NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(384) NOT NULL      -- all-MiniLM-L6-v2 차원
);

-- 코사인 거리용 근사 인덱스
CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx
    ON doc_chunks USING hnsw (embedding vector_cosine_ops);
```

**확인**: `\d doc_chunks`로 `embedding | vector(384)` 컬럼이 보이면 OK.

#### 11단계. pgvector 벡터스토어 (`app/vectorstore_pg.py`)

무엇을/왜: Chroma 래퍼와 동일한 `add_chunks`/`search` 인터페이스를 psycopg + pgvector로 제공한다. `app/rag.py`는 import만 바꾸면 그대로 동작한다.

```bash
pip install "psycopg[binary]>=3.1" "pgvector>=0.3"
```

```python
# app/vectorstore_pg.py
from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector

from app.config import get_settings
from app.embeddings import embed

# 예: postgresql://docpilot:secret@localhost:5432/docpilot
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://docpilot:secret@localhost:5432/docpilot")


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(DATABASE_URL)
    register_vector(conn)
    return conn


def add_chunks(doc_id: str, chunks: list[str], source: str) -> int:
    if not chunks:
        return 0
    vectors = embed(chunks)
    with _connect() as conn, conn.cursor() as cur:
        for i, (text, vec) in enumerate(zip(chunks, vectors)):
            cur.execute(
                "INSERT INTO doc_chunks (doc_id, source, chunk_index, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s)",
                (doc_id, source, i, text, vec),
            )
        conn.commit()
    return len(chunks)


def search(query: str, top_k: int | None = None) -> list[dict]:
    k = top_k or get_settings().top_k
    q_vec = embed([query])[0]
    with _connect() as conn, conn.cursor() as cur:
        # <=> 는 코사인 거리 연산자. 1 - 거리 = 유사도
        cur.execute(
            "SELECT source, chunk_index, content, 1 - (embedding <=> %s) AS score "
            "FROM doc_chunks ORDER BY embedding <=> %s LIMIT %s",
            (q_vec, q_vec, k),
        )
        rows = cur.fetchall()
    return [
        {"source": r[0], "chunk_index": r[1], "text": r[2], "score": round(float(r[3]), 4)}
        for r in rows
    ]
```

`app/rag.py`에서 검색 백엔드를 바꾸려면 한 줄만 교체:

```python
# from app.vectorstore import search           # Chroma
from app.vectorstore_pg import search           # pgvector
```

**확인**: pgvector로 인덱싱 후 `/ask`가 Chroma 때와 동일하게 동작한다. → 벡터DB는 교체 가능한 부품임을 체감.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `/ask`가 항상 "근거 못 찾음" | 인덱싱 안 됨/컬렉션 비었음 | `get_collection().count()`로 조각 수 확인. 인덱싱 먼저 |
| 검색 결과가 엉뚱함 | 인덱싱·질의 임베딩 모델 불일치 | 둘 다 `EMBEDDING_MODEL` 동일하게. 재인덱싱 |
| 답이 컨텍스트를 무시하고 지어냄 | 시스템 프롬프트 약함/temperature 높음 | `RAG_SYSTEM` 규칙 강화, `temperature=0.1` |
| 청크가 너무 크다/작다 | `CHUNK_SIZE` 부적절 | 300~800 사이로 조정, overlap 10~20% |
| PDF에서 텍스트 안 나옴 | 스캔 이미지 PDF(텍스트 레이어 없음) | OCR 필요(범위 밖). 텍스트 PDF로 테스트 |
| Chroma `readonly database` | 권한/경로 문제 | `CHROMA_DIR` 쓰기 권한 확인. 컨테이너면 볼륨 마운트 |
| pgvector `type "vector" does not exist` | 확장 미설치 | `CREATE EXTENSION vector;` 실행, `pgvector/pgvector` 이미지 사용 |
| pgvector 차원 오류 | 테이블 `vector(N)` ≠ 모델 차원 | 모델 차원(MiniLM=384)에 맞춰 테이블 재생성 |
| 답변 비용/지연 큼 | top_k 과다/청크 큼 | `TOP_K` 3~5, 청크 축소. 소형 LLM 고려 |

---

## 이번 주 과제 (Block 2 미니 과제)

제출물(리포지토리 + README + 실행 로그/스크린샷):

1. **필수** — 인덱싱 스크립트(`scripts/index_docs.py`) + `/ask`가 동작하고, **자기 문서**(강의 노트/PDF/README 등)로 RAG 데모를 보이기.
   - 문서에 **있는** 질문 → 근거 있는 답 + 출처.
   - 문서에 **없는** 질문 → "근거 못 찾음" 응답(할루시네이션 억제 확인).
2. **필수** — 답변에 **출처(source/chunk)** 가 함께 표시될 것.
3. **도전** — `CHUNK_SIZE`/`TOP_K`를 2~3가지로 바꿔가며 같은 질문의 답 품질을 비교하고, 최적값과 이유를 한 문단으로.
4. **도전** — Chroma와 pgvector 두 백엔드를 모두 붙이고, 인덱싱/검색 속도·운영 편의를 비교.
5. **도전** — `/ask`를 스트리밍(week06 `/chat/stream` 방식)으로 확장해 답을 실시간으로 흘려보내기.

> 평가 관점: 파이프라인 4단계(인덱싱→검색→주입→생성)가 실제로 도는가, 출처가 보이는가, 없는 걸 지어내지 않는가.

---

## 체크리스트

- [ ] `chromadb`, `pypdf` 설치 및 `requirements.txt` 반영
- [ ] `app/chunking.py`(겹침 청킹) 동작 확인
- [ ] `app/vectorstore.py`(add/search, 코사인) — week07 `embed` 재사용
- [ ] 인덱싱 스크립트로 문서 저장, `count()`로 조각 수 확인
- [ ] `app/rag.py`(컨텍스트 주입 + 근거-제한 시스템 프롬프트)
- [ ] `/ask` 동작: 있는 질문=근거 답+출처, 없는 질문=근거 못 찾음
- [ ] (선택) `/search`로 검색 품질 진단
- [ ] (대안) pgvector로 동일 검색 성공 — 벡터DB 교체 가능성 이해
- [ ] 자기 문서로 RAG 데모(Block 2 미니 과제) 완료

---

## 다음 주 예고

[Week 9 — Agent 기초](./week09-ai-agent-기초.md): 지금까지 docpilot은 "물으면 답하는" 수동적 존재였다. 다음 주부터 **스스로 도구를 골라 쓰는 Agent**로 진화한다. tool/function calling과 ReAct(추론+행동)를 배워, docpilot이 검색·계산·API 호출 같은 도구를 직접 부르게 만든다. 이번 주 RAG의 `search`도 Agent가 호출하는 하나의 "도구"가 된다.
