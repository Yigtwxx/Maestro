"""Document (RAG knowledge base) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentPublic(BaseModel):
    """Metadata for an uploaded document (its text lives in the vector DB)."""

    id: str
    filename: str
    chunk_count: int
    size_bytes: int = 0
    created_at: datetime


class DocumentStorage(BaseModel):
    """A user's knowledge-base usage against their plan allowance.

    ``max_documents``/``max_bytes`` are ``null`` for an unmetered (admin)
    account, which means "no ceiling" -- not zero.
    """

    documents: int
    bytes: int
    max_documents: int | None
    max_bytes: int | None
