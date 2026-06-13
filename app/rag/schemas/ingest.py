from enum import Enum
from typing import List, Optional
from datetime import date as date_type, time as time_type
from pydantic import BaseModel, Field

class DocumentType(str, Enum):
    summary = "summary"
    transcript = "transcript"


class SummaryMetadata(BaseModel):
    """Optional metadata for a meeting summary.

    If provided, it will override metadata parsed from the summary text.
    """
    agenda: Optional[str] = Field(None, description="Meeting agenda")
    date: Optional[date_type] = Field(None, description="Meeting date (YYYY-MM-DD)")
    participants: Optional[List[str]] = Field(None, description="List of participants")
    main_topic: Optional[List[str]] = Field(None, description="List of main topics")
    meeting_id: Optional[str] = Field(None, description="External meeting identifier")
    start_time: Optional[time_type] = Field(None, description="Meeting start time")
    end_time: Optional[time_type] = Field(None, description="Meeting end time")
    location: Optional[str] = Field(None, description="Meeting location")


class SummaryIngestRequest(BaseModel):
    """Request payload to ingest a summary with optional metadata overrides."""
    summary_text: str = Field(..., description="Raw summary markdown/text")
    metadata: Optional[SummaryMetadata] = Field(None, description="Optional metadata overrides")


class TranscriptIngestRequest(BaseModel):
    """Request payload to ingest a transcript with required metadata provided separately."""
    transcript_text: str = Field(..., description="Raw transcript text")
    metadata: SummaryMetadata = Field(..., description="Metadata required for transcript ingestion")
