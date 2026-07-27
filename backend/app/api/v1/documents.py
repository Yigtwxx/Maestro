"""Document upload endpoints for the RAG knowledge base (CLAUDE.md §10).

Uploaded documents are chunked, embedded and stored per-user so agents can
retrieve them as context during tasks.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.core.constants import (
    DOCUMENT_ALLOWED_EXTENSIONS,
    DOCUMENT_MAX_BYTES,
    RATE_LIMIT_READ,
    RATE_LIMIT_UPLOAD,
    RATE_LIMIT_WRITE,
)
from app.core.deps import ActiveUser
from app.schemas.document import DocumentPublic
from app.services import document_service
from app.services.document_service import DocumentError
from app.utils.rate_limiter import rate_limit

router = APIRouter(prefix="/documents", tags=["documents"])

_read_rate_limit = rate_limit(RATE_LIMIT_READ, scope="documents")
_write_rate_limit = rate_limit(RATE_LIMIT_WRITE, scope="documents")
# An upload pays for chunking plus one embedding call per chunk.
_upload_rate_limit = rate_limit(RATE_LIMIT_UPLOAD, scope="documents")


@router.get("", response_model=list[DocumentPublic], dependencies=[_read_rate_limit])
async def list_documents(user: ActiveUser) -> list[dict]:
    """List the current user's uploaded documents."""
    return await document_service.list_documents(user.id)


@router.post(
    "",
    response_model=DocumentPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_upload_rate_limit],
)
async def upload_document(file: UploadFile, user: ActiveUser) -> dict:
    """Upload a text/markdown document into the RAG knowledge base."""
    filename = file.filename or "untitled.txt"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in DOCUMENT_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(DOCUMENT_ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {allowed} files are supported.",
        )
    too_large = HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=f"File size exceeds the {DOCUMENT_MAX_BYTES // 1_000_000} MB limit.",
    )
    # Reject before reading the body into memory. Without this a 1 GB upload
    # would be fully buffered before the check ran, and an oversize document
    # also balloons the chunk/embedding work that slows every squad run.
    if file.size is not None and file.size > DOCUMENT_MAX_BYTES:
        raise too_large
    content = await file.read()
    # Fallback for the rare case the multipart parser left size unknown.
    if len(content) > DOCUMENT_MAX_BYTES:
        raise too_large
    try:
        return await document_service.ingest(user.id, filename, content)
    except DocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_write_rate_limit],
)
async def delete_document(document_id: str, user: ActiveUser) -> None:
    """Delete one of the user's documents and its vector chunks."""
    deleted = await document_service.delete_document(user.id, document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
        )
