from datetime import datetime, date, time
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


class TranscriptBase(BaseModel):
    agenda: str
    date: date
    main_topic: Optional[List[str]] = None
    participants: Optional[List[str]] = None
    summary: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    location: Optional[str] = None


class TranscriptCreate(TranscriptBase):
    transcripts: str


class TranscriptListItem(TranscriptBase):
    id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TranscriptDetail(TranscriptListItem):
    transcripts: str

    class Config:
        from_attributes = True
