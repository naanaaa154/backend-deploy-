from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.rag.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSessionSchema,
    ChatMessageSchema,
    ChatSessionPinUpdate,
)
from app.rag.services.retrieval.chat_service import ChatService
from app.core.database import get_db
from app.auth.services.auth_service import get_current_user
from app.user.models.user import User

router = APIRouter(prefix="/api/chat", tags=["Chat"])
chat_service = ChatService()


@router.post("/", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        return chat_service.process_chat(
            db,
            current_user,
            req.question,
            req.session_id,
            req.meeting_id,
            # history_window=req.history_window,
            # k=(req.k or 6),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/session", response_model=ChatSessionSchema)
def create_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Explicitly create a new chat session"""
    return chat_service.create_session(db, current_user)


@router.get("/sessions", response_model=List[ChatSessionSchema])
def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all chat sessions for the current user"""
    return chat_service.get_user_sessions(db, current_user)


@router.get("/sessions/{session_id}", response_model=List[ChatMessageSchema])
def get_session_history(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get message history for a specific session"""
    history = chat_service.get_session_history(db, current_user, session_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return history


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    deleted = chat_service.delete_session(db, current_user, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok", "message": "Session deleted"}


@router.patch("/sessions/{session_id}/pin", response_model=ChatSessionSchema)
def pin_session(
    session_id: UUID,
    payload: ChatSessionPinUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = chat_service.set_session_pinned(db, current_user, session_id, payload.is_pinned)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
