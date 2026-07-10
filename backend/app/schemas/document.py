"""Document (RAG knowledge base) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentPublic(BaseModel):
    """Metadata for an uploaded document (its text lives in the vector DB)."""

    id: str
    filename: str
    chunk_count: int
    created_at: datetime
