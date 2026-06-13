from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Form, Depends
from datetime import date, time
from sqlalchemy.orm import Session


from app.core.database import get_db
from app.rag.schemas.transcript import TranscriptCreate
from app.rag.services.ingest.transcript_ingest import ingest_transcript
from app.rag.services.transcript_service import create_transcript

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])


@router.post("/transcript-upload")
async def ingest_transcript_upload(
    background_tasks: BackgroundTasks,
    transcript_file: UploadFile = File(...),
    summary_file: UploadFile = File(...),
    agenda: str = Form(...),
    date: date = Form(...),
    start_time: time = Form(...),
    end_time: time = Form(...),
    location: str = Form(...),
    participants: str = Form(...),  # e.g., "Alice, Bob"
    main_topic: str = Form(...),    # e.g., "Roadmap, OKR"
    db: Session = Depends(get_db),
):
    """Unified endpoint: upload a transcript file and submit metadata via form.

    All provided metadata will be attached to every transcript chunk in the vector store.
    """
    try:
        t_bytes = await transcript_file.read()
        t_content = t_bytes.decode("utf-8")
    except Exception as e:
        return {"status": "error", "message": f"Gagal membaca file transkrip: {str(e)}"}

    try:
        s_bytes = await summary_file.read()
        summary_content = s_bytes.decode("utf-8").strip()
    except Exception as e:
        return {"status": "error", "message": f"Gagal membaca file summary: {str(e)}"}

    def normalize_list(s: str):
        return [v.strip() for v in s.split(",") if v.strip()] if s else []

    transcript_payload = TranscriptCreate(
        agenda=agenda,
        date=date,
        main_topic=normalize_list(main_topic),
        participants=normalize_list(participants),
        summary=summary_content,
        start_time=start_time,
        end_time=end_time,
        location=location,
        transcripts=t_content,
    )
    transcript = create_transcript(db, transcript_payload)

    # Samakan meeting_id pada metadata embedding dengan id pada tabel transcripts.
    # Ini membuat filtering/traceability ke data transcript menjadi konsisten.
    meeting_id = transcript.id

    override = {
        "agenda": agenda,
        "date": date,
        "participants": transcript_payload.participants,
        "main_topic": transcript_payload.main_topic,
        "meeting_id": meeting_id,
        "summary": summary_content,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
    }

    background_tasks.add_task(ingest_transcript, t_content, override)
    return {
        "status": "processing",
        "message": "Transkrip dan metadata diterima. Proses embedding berjalan di latar belakang.",
        "file": transcript_file.filename,
        "transcript_id": transcript.id,
        "metadata": {
            **override,
        },
    }
