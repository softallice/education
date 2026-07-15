-- db/init.sql — PostgreSQL 초기화 (컨테이너 최초 기동 시 1회 실행)
-- 교안 week03 documents 스키마. IF NOT EXISTS 로 앱의 init_db 와 중복돼도 안전.

CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    filename     VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes   INTEGER      NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- (선택) week08 RAG 대비 pgvector 확장. 이미지에 확장이 없으면 무시된다.
-- CREATE EXTENSION IF NOT EXISTS vector;
