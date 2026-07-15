# app/db.py — DB 연결과 Document 모델 (교안 week03 스키마)
from sqlalchemy import Column, DateTime, Integer, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

# pool_pre_ping: 죽은 커넥션을 미리 걸러 재연결(컨테이너 재시작 대비)
engine = create_engine(get_settings().database_url, pool_pre_ping=True)
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
    """앱 시작 시 테이블이 없으면 생성. (db/init.sql 과 중복돼도 IF NOT EXISTS 로 안전.)"""
    Base.metadata.create_all(bind=engine)


def get_session():
    """FastAPI 의존성: 요청마다 세션을 열고 끝나면 닫는다."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
