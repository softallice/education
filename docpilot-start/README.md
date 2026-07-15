# docpilot-start — 교육용 시작 스캐폴드 (frontend · api · db)

클라우드프로그래밍 강의 러닝 프로젝트 **docpilot**의 출발점이다. `docker compose` 한 번으로 **프론트엔드(React) ↔ API(FastAPI) ↔ DB(PostgreSQL)** 3계층이 연결된 상태를 띄운다. week01~week03에서 손으로 쌓는 구조를 미리 조립해 둔 "달리는 골격"이다.

## 구성

```text
docpilot-start/
├── frontend/            # React(Vite) SPA → 빌드 후 nginx 서빙, /api 프록시
│   ├── src/{main.tsx, App.tsx, api.ts, styles.css}
│   ├── Dockerfile       # 멀티스테이지(node build → nginx)
│   └── nginx.conf       # /api/ → api:8000 프록시 + SPA 폴백
├── api/                 # FastAPI (교안 week01 / + /health, week03 /documents)
│   ├── app/{main.py, config.py, db.py, routers/documents.py}
│   ├── Dockerfile
│   └── requirements.txt
├── db/
│   └── init.sql         # PostgreSQL 16 초기 스키마(documents)
├── docker-compose.yml   # 3 services
├── .env.example
└── .gitignore
```

## 빠른 시작

```bash
docker compose up --build
```

- 프론트엔드: <http://localhost:8080>
- API 문서(Swagger): <http://localhost:8000/docs>

**확인**: 브라우저에서 `http://localhost:8080` 접속 → 우상단 배지가 **"API: 정상"** 이면 프론트↔API↔DB 연결 성공. 파일을 업로드하면 목록에 나타난다(메타데이터가 DB에 저장됨).

정리:

```bash
docker compose down          # 컨테이너 중지·삭제
docker compose down -v       # DB 볼륨까지 삭제(초기화)
```

## 데이터 흐름

```text
브라우저 ──▶ frontend(nginx :80) ──/api/*──▶ api(FastAPI :8000) ──▶ db(PostgreSQL :5432)
```

프론트엔드는 항상 상대경로 `/api/...`로 호출한다. 로컬 개발(`npm run dev`)에서는 Vite 프록시가, 컨테이너에서는 nginx가 `/api`를 API로 전달하므로 코드 변경이 필요 없다.

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | `{"message": "Hello, DocPilot"}` |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/documents` | 문서 메타 목록(최신순) |
| POST | `/documents` | 파일 업로드 → 메타데이터 DB 저장 |

## 개별 실행(컨테이너 없이, 선택)

```bash
# API
cd api && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=postgresql+psycopg://docpilot:docpilot@localhost:5432/docpilot \
  uvicorn app.main:app --reload      # db 컨테이너만 띄운 상태에서

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## 강의와의 연결

- **week01** `/`·`/health` · **week02** Dockerfile 컨테이너화 · **week03** compose + PostgreSQL + `/documents` — 이 스타터에 이미 반영돼 있다.
- **week04~05**에서 이 이미지를 kind(K8s)에 배포하고, **week06~**부터 `api/app/routers/`에 `chat`·`ask`·`agent`를 더해 docpilot을 키운다.
- `api/app/config.py`는 `pydantic-settings` 기반이라 week06 이후 필드(LLM 키 등)를 그대로 확장한다.
