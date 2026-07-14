# Week 3 — Docker Compose 멀티 컨테이너

> 이번 주 한 줄: 앱 혼자서는 서비스가 안 된다. `docpilot`(web)과 PostgreSQL을 Compose로 함께 띄우고, 문서 메타데이터를 DB에 저장한다.
> docpilot 진화: **단일 컨테이너 → 멀티 컨테이너(web + PostgreSQL)** + `/documents` 엔드포인트(업로드 메타 DB 저장·조회) + 볼륨 영속화

이 문서는 [주차별 커리큘럼 목차](./README.md)의 3주차다. [Week 2](./week02-docker-컨테이너-기초.md)의 컨테이너화된 `docpilot`을 이어서 확장한다.

---

## 학습 목표

- [ ] 컨테이너 네트워크로 서비스끼리 이름으로 통신하는 원리를 이해한다.
- [ ] 볼륨으로 데이터를 컨테이너 수명과 분리해 영속화한다.
- [ ] 환경변수로 설정을 주입한다(12-Factor #3 Config).
- [ ] 시크릿(비밀번호 등)을 코드에 넣지 않는 이유와 기초 처리법을 안다.
- [ ] `docker-compose.yml`로 web + PostgreSQL 16을 한 번에 띄운다.
- [ ] `docpilot`에 `/documents` 엔드포인트를 추가해 DB에 저장·조회한다.

## 사전 준비

- 지난주 산출물: 컨테이너화된 `docpilot` (`Dockerfile`, `.dockerignore`, `main.py`, `requirements.txt`)
- 필요한 도구: Docker + Docker Compose v2 (`docker compose version`)
- 확인 명령:

```bash
docker compose version     # Docker Compose version v2.x
cd ~/projects/docpilot
ls                         # Dockerfile, main.py, requirements.txt 확인
```

> `docker compose`(공백)는 Compose v2다. 옛 `docker-compose`(하이픈)는 v1이니 가급적 v2를 쓴다.

---

## 개념 (요약)

### 1. 컨테이너 네트워크

Compose는 프로젝트별로 **가상 네트워크**를 자동 생성한다. 같은 네트워크에 속한 컨테이너는 **서비스 이름**을 호스트명처럼 써서 서로 통신한다.

- `docpilot`(web) 컨테이너가 DB에 접속할 때 IP가 아니라 **`db`라는 이름**으로 접속한다.
- 왜? 컨테이너 IP는 재시작마다 바뀌지만 서비스 이름은 안정적이다(DNS 역할). 이게 12-Factor "Backing services"의 실전 형태다.

### 2. 볼륨(Volume)

컨테이너는 **일회용(disposable)** 이다. 지우면 안의 데이터도 사라진다. DB 데이터가 컨테이너와 함께 날아가면 안 되므로, **볼륨**에 데이터를 저장해 컨테이너 수명과 분리한다.

- 명명된 볼륨(named volume): `pgdata`처럼 이름을 붙여 Docker가 관리하는 저장소. DB 데이터에 적합.
- 컨테이너를 지웠다 다시 만들어도 볼륨이 살아 있으면 데이터가 유지된다 → 이번 주 핵심 실습.

### 3. 환경변수와 시크릿 기초

- **환경변수(Config)**: 접속 주소·포트·DB 이름처럼 환경마다 달라지는 값. 코드가 아니라 환경에서 주입한다. `docpilot`은 `DATABASE_URL` 하나로 DB 접속 정보를 받는다.
- **시크릿(Secret)**: 비밀번호·API 키처럼 유출되면 안 되는 값. **절대 코드/이미지에 하드코딩하지 않는다.** 이번 주는 `.env` 파일로 분리하고 `.gitignore`로 커밋을 막는다(가장 기본).
- 운영 환경에서는 Docker/K8s의 secret 리소스나 Vault 같은 시크릿 매니저를 쓴다(5주차에서 확장).

> **철칙**: 비밀번호를 소스에 적지 않는다. `.env`는 절대 커밋하지 않는다. 이 두 가지는 이번 주부터 습관으로 굳힌다.

---

## 실습: 단계별 따라하기

### 1부. DB 연동 코드 추가

#### 1단계. 의존성 추가

`requirements.txt`에 SQLAlchemy와 PostgreSQL 드라이버(psycopg 3)를 추가한다. 파일 전체를 아래로 교체:

```text
fastapi==0.115.6
uvicorn[standard]==0.32.1
sqlalchemy==2.0.36
psycopg[binary]==3.2.3
pydantic==2.10.4
```

**확인**: 로컬 가상환경에서도 확인해 두면 편하다.

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -c "import sqlalchemy, psycopg, pydantic; print('ok')"   # ok
```

#### 2단계. db.py 작성 (DB 연결 + 모델)

프로젝트 루트에 `db.py`를 만든다. `DATABASE_URL` 환경변수로 접속 정보를 받는다(12-Factor #3).

```python
# db.py — docpilot week03: DB 연결과 Document 모델
import os

from sqlalchemy import Column, DateTime, Integer, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 접속 정보는 코드가 아니라 환경변수에서. 로컬 폴백은 개발 편의용.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://docpilot:docpilot@localhost:5432/docpilot",
)

# pool_pre_ping: 죽은 커넥션을 미리 걸러 재연결 (컨테이너 재시작 대비)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    """업로드된 문서의 메타데이터. 실제 파일 내용이 아니라 '정보'만 저장한다."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


def init_db() -> None:
    """앱 시작 시 테이블이 없으면 생성. (실무는 마이그레이션 도구를 쓰지만 학습용으로 간단히.)"""
    Base.metadata.create_all(bind=engine)
```

> `postgresql+psycopg://` 스킴이 psycopg 3 드라이버를 지정한다. 사용자/비밀번호/호스트/포트/DB이름 순서다.

#### 3단계. main.py 확장 (/documents 추가)

`main.py`를 아래 완결본으로 교체한다. 1주차의 `/`·`/health`는 그대로 두고, 문서 메타 업로드·목록·단건 조회를 추가한다.

```python
# main.py — docpilot week03: /documents (업로드 메타 DB 저장/조회)
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Document, SessionLocal, init_db

app = FastAPI(title="docpilot", version="0.3.0")


@app.on_event("startup")
def on_startup() -> None:
    # 앱이 뜰 때 테이블 보장. DB가 아직 준비 안 됐으면 여기서 에러가 날 수 있어
    # compose의 healthcheck + depends_on으로 기동 순서를 맞춘다(아래 5단계).
    init_db()


def get_db():
    """요청마다 세션을 열고 끝나면 닫는다(의존성 주입)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DocumentOut(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime

    class Config:
        from_attributes = True  # ORM 객체 → 응답 스키마 변환 허용


@app.get("/")
def root() -> dict:
    return {"message": "Hello, DocPilot"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    """파일을 받아 '메타데이터만' DB에 저장한다(내용 저장은 8주차 RAG에서)."""
    body = await file.read()  # 크기 계산용으로만 읽는다
    doc = Document(
        filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(body),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)  # DB가 채운 id/created_at을 다시 읽어옴
    return doc


@app.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    """저장된 문서 메타 목록(최신순)."""
    return list(db.scalars(select(Document).order_by(Document.id.desc())))


@app.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db)) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc
```

### 2부. Compose로 web + PostgreSQL 띄우기

#### 4단계. .env 파일과 .gitignore 확인

DB 자격증명을 `.env`로 분리한다. 프로젝트 루트에 `.env` 생성:

```text
POSTGRES_USER=docpilot
POSTGRES_PASSWORD=docpilot
POSTGRES_DB=docpilot
DATABASE_URL=postgresql+psycopg://docpilot:docpilot@db:5432/docpilot
```

> `DATABASE_URL`의 호스트가 `localhost`가 아니라 **`db`** 임에 주목. 이것이 Compose 서비스 이름(=네트워크상의 호스트명)이다.

`.gitignore`에 `.env`가 있는지 반드시 확인한다(1주차에 이미 추가했음).

```bash
grep -q "^.env" .gitignore && echo ".env ignored OK" || echo "MISSING: add .env to .gitignore"
```

**확인**: `.env ignored OK`가 나와야 한다. 안 나오면 `.gitignore`에 `.env` 줄을 추가한다.

#### 5단계. docker-compose.yml 작성 (완결된 코드)

프로젝트 루트에 `docker-compose.yml`을 만든다. 복붙해서 바로 뜨는 완결본이다.

```yaml
# docker-compose.yml — docpilot week03: web + PostgreSQL 16
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data   # 데이터 영속화 (컨테이너 지워도 유지)
    healthcheck:
      # DB가 '진짜 접속 가능한' 상태가 될 때까지 web을 기다리게 한다
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10
    # 5432를 호스트로 노출(선택). 로컬 DB 툴로 붙어볼 때 편함.
    ports:
      - "5432:5432"

  web:
    build: .                    # 현재 폴더의 Dockerfile로 docpilot 이미지 빌드
    environment:
      DATABASE_URL: ${DATABASE_URL}
    depends_on:
      db:
        condition: service_healthy   # db healthcheck 통과 후 web 시작
    ports:
      - "8000:8000"

volumes:
  pgdata:                       # 명명된 볼륨 선언
```

> `depends_on: condition: service_healthy` + `healthcheck`가 핵심이다. 이게 없으면 web이 DB보다 먼저 떠서 접속 에러가 난다(흔한 함정).

#### 6단계. 스택 기동

```bash
docker compose up --build
```

- `--build` = web 이미지를 새로 빌드
- 두 서비스 로그가 한 화면에 섞여 나온다(`db-1`, `web-1` 접두어)

**확인**: 아래 흐름이 보인다.

```text
db-1   | ... database system is ready to accept connections
web-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
web-1  | INFO:     Application startup complete.
```

`web` 기동 전에 `db`가 healthy가 되어야 하므로, db 로그가 먼저 안정된 뒤 web이 뜬다.

### 3부. 동작 확인과 볼륨 영속화

#### 7단계. /documents 엔드포인트 테스트

**새 터미널**에서(스택은 켠 채로):

```bash
# 테스트용 파일 하나 만들기
echo "docpilot test document" > sample.txt

# 1) 업로드 (메타가 DB에 저장됨)
curl -F "file=@sample.txt" http://127.0.0.1:8000/documents

# 2) 목록 조회
curl http://127.0.0.1:8000/documents

# 3) 단건 조회 (위에서 받은 id 사용, 보통 1)
curl http://127.0.0.1:8000/documents/1
```

**확인**: 업로드 응답이 아래와 비슷하다(id·created_at은 DB가 채움).

```json
{"id":1,"filename":"sample.txt","content_type":"text/plain","size_bytes":23,"created_at":"2026-09-.."}
```

목록은 배열로, 단건은 객체로 온다. 없는 id(`/documents/999`)는 404 + `{"detail":"document not found"}`.

브라우저에서 <http://127.0.0.1:8000/docs>를 열면 `POST /documents`를 파일 선택 UI로 직접 테스트할 수 있다.

#### 8단계. DB에 실제로 들어갔는지 직접 확인

```bash
docker compose exec db psql -U docpilot -d docpilot -c "SELECT id, filename, size_bytes FROM documents;"
```

**확인**: 방금 올린 `sample.txt` 행이 psql 출력에 보인다.

#### 9단계. 볼륨 영속화 검증 (이번 주 하이라이트)

컨테이너를 **지웠다 다시 만들어도** 데이터가 유지되는지 확인한다.

```bash
# 컨테이너만 내림 (볼륨은 유지 — -v 안 붙임!)
docker compose down

# 다시 올림
docker compose up -d

# 데이터가 살아있는지 확인
curl http://127.0.0.1:8000/documents
```

**확인**: `down` → `up` 했는데도 아까 올린 문서가 그대로 조회된다. **볼륨 덕분에 컨테이너 수명과 데이터가 분리됐기 때문**이다.

반대로 볼륨까지 지우면 데이터가 사라지는 것도 확인해 보자(주의: 되돌릴 수 없음).

```bash
docker compose down -v            # -v = 볼륨까지 삭제
docker compose up -d
curl http://127.0.0.1:8000/documents   # []  (빈 배열 — 데이터 사라짐)
```

**확인**: `-v`로 내리면 목록이 `[]`가 된다. 즉 데이터는 컨테이너가 아니라 **볼륨**에 있었다.

정리와 커밋:

```bash
docker compose down               # 스택 정지
git add main.py db.py requirements.txt docker-compose.yml
git commit -m "feat: docpilot week03 compose(web+postgres) + /documents 메타 저장"
git push
```

> `.env`와 `sample.txt`는 커밋하지 않는다. `git status`로 `.env`가 안 보이는지 다시 확인한다.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| web이 `connection refused`로 죽음 | DB보다 먼저 기동 | `depends_on: condition: service_healthy` + healthcheck 확인(본 문서대로) |
| `could not translate host name "db"` | web이 DB에 `localhost`로 접속 | `.env`의 `DATABASE_URL` 호스트가 `db`인지 확인 |
| `password authentication failed` | `.env` 자격증명 불일치 | `POSTGRES_*`와 `DATABASE_URL`의 user/pw가 같은지 확인 |
| `port 5432 already in use` | 호스트에 로컬 Postgres 실행 중 | compose의 db `ports`를 `"5433:5432"`로 바꾸거나 로컬 pg 중지 |
| 코드 고쳤는데 반영 안 됨 | web 이미지 재빌드 안 함 | `docker compose up --build` |
| `down` 후 데이터가 사라짐 | `down -v`로 볼륨까지 삭제함 | 데이터 유지하려면 `-v` 없이 `down` |
| `.env` 값이 안 먹음 | `.env`가 compose와 다른 폴더 | `docker-compose.yml`과 같은 디렉터리에 `.env` |
| `on_event startup deprecated` 경고 | FastAPI 신버전 lifespan 권장 | 학습용은 무시 가능(동작함). 원하면 lifespan 핸들러로 이관 |

---

## 이번 주 과제

**제출물**: `docker-compose.yml`, `db.py`, 확장된 `main.py`가 커밋된 저장소 + 아래 확장.

1. **필수** — 위 실습을 완주한다. `/documents` 업로드·목록·단건 조회가 동작하고, 볼륨 영속화(9단계)를 스크린샷 또는 로그로 증빙한다.
2. **삭제 엔드포인트 추가** — `DELETE /documents/{doc_id}`를 구현한다. 존재하면 삭제 후 `204 No Content`, 없으면 404를 반환한다.

   ```python
   from fastapi import Response

   @app.delete("/documents/{doc_id}", status_code=204)
   def delete_document(doc_id: int, db: Session = Depends(get_db)) -> Response:
       doc = db.get(Document, doc_id)
       if doc is None:
           raise HTTPException(status_code=404, detail="document not found")
       db.delete(doc)
       db.commit()
       return Response(status_code=204)
   ```

   업로드 → 삭제 → 목록이 비는 걸 `curl -X DELETE ...`로 확인하고 커밋한다.
3. **개념 정리(README)** — (1) 볼륨이 왜 필요한지 2줄, (2) `depends_on` + healthcheck가 없으면 무슨 일이 나는지 2줄, (3) `.env`를 커밋하면 안 되는 이유 1줄.

> 제출: LMS에 저장소 URL, 볼륨 영속화 증빙, 마지막 커밋 해시를 제출한다.

---

## 체크리스트

- [ ] `requirements.txt`에 SQLAlchemy·psycopg를 추가했다.
- [ ] `db.py`에 `DATABASE_URL` 기반 연결과 `Document` 모델을 작성했다.
- [ ] `main.py`에 `/documents` POST/GET(목록)/GET(단건)을 구현했다.
- [ ] `.env`로 자격증명을 분리하고 `.gitignore`로 커밋을 막았다.
- [ ] `docker-compose.yml`로 web + PostgreSQL 16을 함께 띄웠다.
- [ ] 파일 업로드 후 psql로 DB에 행이 들어간 걸 확인했다.
- [ ] `down` → `up` 후에도 데이터가 유지되는(볼륨 영속화) 걸 확인했다.
- [ ] (과제) `DELETE /documents/{doc_id}`를 추가했다.
- [ ] `.env` 제외하고 커밋·푸시했다.

---

## 다음 주 예고

**Week 4 — Kubernetes 배포 기초** (다음 블록의 시작)

Compose로 여러 컨테이너를 한 대에서 띄우는 건 배웠다. 하지만 실제 운영은 여러 대의 서버에 걸쳐 자동으로 확장·복구되어야 한다. 다음 주부터는 **Kubernetes**로 넘어간다. `kind`(또는 minikube)로 로컬 클러스터를 만들고, `docpilot` 이미지를 **Deployment + Service**로 배포한 뒤 `kubectl`로 상태를 확인한다. 2주차에 레지스트리에 올린 이미지와 3주차의 DB 개념이 여기서 쿠버네티스 리소스로 재구성된다.
