from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.rag.models.transcript import Transcript
from app.rag.schemas.transcript import TranscriptCreate


def create_transcript(db: Session, payload: TranscriptCreate) -> Transcript:
    transcript = Transcript(
        agenda=payload.agenda,
        date=payload.date,
        main_topic=payload.main_topic,
        participants=payload.participants,
        summary=payload.summary,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=payload.location,
        transcripts=payload.transcripts,
    )
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    return transcript


def list_transcripts(db: Session, limit: int = 50) -> List[Transcript]:
    return (
        db.query(Transcript)
        .order_by(Transcript.created_at.desc())
        .limit(limit)
        .all()
    )


def get_transcript(db: Session, transcript_id: UUID) -> Optional[Transcript]:
    return db.query(Transcript).filter(Transcript.id == transcript_id).first()


def delete_transcript(db: Session, transcript_id: UUID) -> bool:
    transcript = get_transcript(db, transcript_id)
    if not transcript:
        return False

    db.execute(
        text(
            "DELETE FROM langchain_pg_embedding WHERE cmetadata->>'meeting_id' = :meeting_id"
        ),
        {"meeting_id": str(transcript_id)},
    )
    db.delete(transcript)
    db.commit()
    return True
