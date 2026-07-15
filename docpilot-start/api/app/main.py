# app/main.py — docpilot FastAPI 진입점 (교안 week01 / + /health, week03 /documents)
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import documents


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱이 뜰 때 테이블 보장. (on_event 대신 lifespan — 최신 FastAPI 권장 방식)
    init_db()
    yield


app = FastAPI(title=get_settings().app_name, version="0.3.0", lifespan=lifespan)

# 프론트엔드(별도 오리진)에서 호출 가능하도록 CORS 허용.
# 운영 배포 시에는 allow_origins 를 실제 도메인으로 좁힌다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)


@app.get("/")
def root() -> dict:
    return {"message": "Hello, DocPilot"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
