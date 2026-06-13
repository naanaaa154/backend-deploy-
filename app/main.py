from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.langsmith import init_langsmith
from app.core.database import Base, engine
from app.user.models.user import User
from app.rag.models.transcript import Transcript

# Inisialisasi LangSmith SEBELUM mengimpor router/services yang menginisialisasi LLM
try:
    init_langsmith()
except Exception as e:
    print(f"Warning: LangSmith initialization failed or skipped: {e}")

from app.rag.routes.ingest_router import router as ingest_router
from app.rag.routes.chat_router import router as chat_router
from app.rag.routes.transcript_router import router as transcript_router
from app.auth.routes.auth_router import auth_router
from app.user.routes.user_router import user_router


def ensure_transcript_optional_columns() -> None:
    """Ensure optional columns exist for legacy transcript tables."""
    statements = [
        "ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS start_time VARCHAR(64)",
        "ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS end_time VARCHAR(64)",
        "ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS location VARCHAR(255)",
    ]

    try:
        with engine.begin() as connection:
            for sql in statements:
                connection.execute(text(sql))
    except Exception as e:
        print(f"Warning: failed to ensure transcript optional columns: {e}")



# Buat tabel database jika belum ada
Base.metadata.create_all(bind=engine)
ensure_transcript_optional_columns()


app = FastAPI(title="Meeting RAG System")

# Konfigurasi CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Izinkan semua asal (bisa dipersempit nanti)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)
app.include_router(chat_router)
app.include_router(transcript_router)

app.include_router(auth_router, prefix='/api')
app.include_router(user_router, prefix='/api', tags=['Users'])