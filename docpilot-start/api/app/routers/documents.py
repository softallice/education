# app/routers/documents.py — 문서 메타 업로드/조회 (교안 week03 /documents)
from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Document, get_session

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(get_session)) -> list[Document]:
    """저장된 문서 메타 목록(최신순)."""
    rows = session.execute(select(Document).order_by(Document.id.desc())).scalars().all()
    return list(rows)


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> Document:
    """업로드된 파일의 '메타데이터'만 DB에 저장한다(내용은 저장하지 않음)."""
    body = await file.read()
    doc = Document(
        filename=file.filename or "unknown",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(body),
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc
