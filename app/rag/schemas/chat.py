from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date as date_type

class ChatRequest(BaseModel):
    session_id: Optional[UUID] = None
    question: str
    meeting_id: Optional[UUID] = None
    # history_window: Optional[int] = None  # jumlah pesan terakhir untuk konteks percakapan
    # k: Optional[int] = 6  # jumlah dokumen yang diambil


class Source(BaseModel):
    date: Optional[date_type] = None
    agenda: Optional[str] = None
    main_topic: Optional[List[str]] = None
    meeting_id: Optional[str] = None
    chunk_index: Optional[int] = None
    participants: Optional[List[str]] = None
    content: Optional[str] = None
    vector_score: Optional[float] = None
    re_rank_score: Optional[float] = None


class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    sources: List[Source]
    suggestions: Optional[List[str]] = None


class ChatMessageSchema(BaseModel):
    id: UUID
    role: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionSchema(BaseModel):
    id: UUID
    agenda: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    is_pinned: bool = False

    class Config:
        from_attributes = True


class ChatSessionPinUpdate(BaseModel):
    is_pinned: bool
