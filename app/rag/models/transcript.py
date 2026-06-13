from sqlalchemy import Column, DateTime, Date, Text, String, Time, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from app.core.database import Base
from datetime import datetime


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agenda = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)
    main_topic = Column(JSONB, nullable=True)
    participants = Column(JSONB, nullable=True)
    summary = Column(Text, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    location = Column(String(255), nullable=True)
    transcripts = Column(Text, nullable=False)
    # Ensure both DB-side and Python-side defaults so:
    # - DB will set default when inserting outside ORM
    # - ORM instances will have timestamp values immediately (no None)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=func.now(),
    )
