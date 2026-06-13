from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.rag.schemas.transcript import TranscriptDetail, TranscriptListItem
from app.rag.services.transcript_service import list_transcripts, get_transcript, delete_transcript

router = APIRouter(prefix="/api/transcripts", tags=["Transcripts"])


@router.get("", response_model=list[TranscriptListItem])
def fetch_transcripts(db: Session = Depends(get_db)):
    return list_transcripts(db)


@router.get("/{transcript_id}", response_model=TranscriptDetail)
def fetch_transcript(transcript_id: UUID, db: Session = Depends(get_db)):
    transcript = get_transcript(db, transcript_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transkrip tidak ditemukan")
    return transcript


@router.delete("/{transcript_id}")
def remove_transcript(transcript_id: UUID, db: Session = Depends(get_db)):
    deleted = delete_transcript(db, transcript_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transkrip tidak ditemukan")
    return {"status": "ok", "message": "Transkrip dihapus"}
