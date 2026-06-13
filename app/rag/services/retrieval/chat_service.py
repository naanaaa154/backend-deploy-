from typing import List, Dict, Any, Optional
import json
import logging
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
import psycopg
from app.core.config import settings
from sqlalchemy.orm import Session
from uuid import UUID
from app.rag.models.chat import ChatSession, ChatMessage
from app.user.models.user import User

from app.rag.services.retrieval.chat_types import GraphState, QueryIntent
from app.rag.services.retrieval.chat_helpers import (
    normalize_query_for_retrieval,
    correct_and_classify_intent,
    # correct_user_query,
    extract_history_and_query,
    build_sources,
    generate_question_suggestions,
)
from app.rag.services.retrieval.response_generator import (
    generate_general_response,
    generate_metadata_response,
    generate_retrieval_response,
    generate_summary_response,
)
from app.rag.services.retrieval.document_retriever import (
    DocumentRetriever,
    HAS_FLASHRANK,
    Ranker,
)


class ChatService:
    def __init__(self):
        # Initialize Ranker (only once)
        # Using a small/fast model by default
        if HAS_FLASHRANK:
            # Cross-encoder re-ranking untuk meningkatkan kualitas dokumen hasil vector search.
            # Retrieval intent: TinyBERT (lebih cepat)
            # Metadata intent: MiniLM (kualitas lebih baik)
            self._retrieval_ranker = Ranker(
                model_name="ms-marco-MiniLM-L-12-v2",
                cache_dir="./models",
            )
            self._retrieval_fallback_ranker = Ranker(
                model_name="ms-marco-TinyBERT-L-2-v2",
                cache_dir="./models",
            )
            self._metadata_ranker = Ranker(
                    model_name="ms-marco-MiniLM-L-12-v2",
                    cache_dir="./models",
                )
            self._summary_ranker = Ranker(
                    model_name="ms-marco-MiniLM-L-12-v2",
                    cache_dir="./models",
                )

        else:
            self._retrieval_ranker = None
            self._retrieval_fallback_ranker = None
            self._metadata_ranker = None
            self._summary_ranker = None

        self._retriever = DocumentRetriever()
        self._pool = self._create_pool()
        self._setup_checkpointer()
        self._graph_app = self._build_graph()

        # Basic logger for terminal visibility (uvicorn will render stdout/stderr).
        self._logger = logging.getLogger(__name__)

    def _get_postgres_uri(self) -> str:
        # Normalisasi DATABASE_URL agar kompatibel dengan psycopg (bukan dialect SQLAlchemy).
        db_uri = settings.DATABASE_URL
        if db_uri.startswith("postgresql+psycopg://"):
            return db_uri.replace("postgresql+psycopg://", "postgresql://", 1)
        return db_uri

    def _create_pool(self) -> ConnectionPool:
        # Pool koneksi untuk PostgresSaver (checkpoint LangGraph).
        return ConnectionPool(conninfo=self._get_postgres_uri(), max_size=10)

    def _setup_checkpointer(self) -> None:
        # Setup tabel/struktur checkpoint LangGraph di Postgres (jika belum ada).
        with psycopg.connect(self._get_postgres_uri(), autocommit=True) as conn:
            PostgresSaver(conn).setup()

    def _build_graph(self):
        # Definisi graph sederhana: START -> model -> END.
        # Node model memutuskan retrieval lalu memanggil LLM.
        workflow = StateGraph(GraphState)
        workflow.add_node("model", self._call_model)
        workflow.add_edge(START, "model")
        workflow.add_edge("model", END)
        return workflow.compile(checkpointer=PostgresSaver(self._pool))

    def _retrieve_with_fallback(
        self,
        *,
        normalized_query: str,
        meeting_id: Optional[str],
        configs: List[Dict[str, Any]],
    ) -> List[Document]:
        for config in configs:
            docs = self._retriever.retrieve_documents(
                query=normalized_query,
                meeting_id=meeting_id,
                **config,
            )
            if docs:
                return docs
        return []

    def _call_model(self, state: GraphState) -> Dict[str, Any]:
        """
        Node utama graph:
        1. Extract query
        2. Classify intent (GENERAL / database / RETRIEVAL)
        3. Route ke handler yang sesuai
        4. Return answer + sources
        """

        messages = state.get("messages", [])
        meeting_id = state.get("meeting_id")
        history_messages, query = extract_history_and_query(messages)

        try:
            last_four = history_messages[-2:]
            if last_four:
                self._logger.info(
                    "CHAT_HISTORY_LAST_FOUR %s",
                    json.dumps(
                        [
                            {
                                "role": getattr(msg, "type", msg.__class__.__name__),
                                "content": getattr(msg, "content", ""),
                            }
                            for msg in last_four
                        ],
                        ensure_ascii=False,
                        default=str,
                    ),
                )
            else:
                self._logger.info("CHAT_HISTORY_LAST_FOUR []")
        except Exception:
            print("CHAT_HISTORY_LAST_FOUR", history_messages[-2:])

        if not query:
            return {"messages": []}

        corrected_and_intent = correct_and_classify_intent(query)
        corrected_query = corrected_and_intent.get("corrected_question", query)
        try:
            self._logger.info(
                "CHAT_CORRECTION_INTENT %s",
                json.dumps(
                    {
                        "original_question": query,
                        **corrected_and_intent,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
        except Exception:
            print(
                "CHAT_CORRECTION_INTENT",
                {
                    "original_question": query,
                    **corrected_and_intent,
                },
            )

        query = corrected_query

        # 1️⃣ Klasifikasi intent
        intent = corrected_and_intent.get("classify_intent", QueryIntent.RETRIEVAL)

        docs: List[Document] = []
        answer: str = ""
        suggestions: List[str] = []

        # 2️⃣ Routing berdasarkan intent
        if intent == QueryIntent.GENERAL:
            # Chat biasa (tanpa retrieval)
            answer = generate_general_response(query, history_messages)

        elif intent == QueryIntent.RETRIEVAL:
            # RAG mode
            normalized_query = normalize_query_for_retrieval(query)
            docs = self._retrieve_with_fallback(
                normalized_query=normalized_query,
                meeting_id=meeting_id,
                configs=[
                    
                    {
                        "k": 1,
                        "score_threshold": 0.7,
                        "use_reranking": True,
                        "ranker": self._retrieval_ranker,
                        "tipe": "all",
                    },
                    {
                        "k": 1,
                        "score_threshold": 0.3,
                        "use_reranking": True,
                        "ranker": self._retrieval_ranker,
                        "tipe": "all",
                    },
                    {
                        "k": 1,
                        "score_threshold": 0.3,
                        "use_reranking": False,
                    },
                ],
            )

            if docs:
                rag_history = history_messages
                answer = generate_retrieval_response(
                    query=query,
                    docs=docs,
                    history_messages=rag_history,
                )
            else:
                answer = (
                    "Mohon maaf, saya tidak menemukan informasi spesifik mengenai hal tersebut dalam dokumen ini. "
                )
                suggestions = generate_question_suggestions(query, intent)

        elif intent == QueryIntent.METADATA:
            # Metadata mode: hanya ambil dokumen metadata, tanpa batas jumlah chunk.
            normalized_query = normalize_query_for_retrieval(query)
            docs = self._retrieve_with_fallback(
                normalized_query=normalized_query,
                meeting_id=meeting_id,
                configs=[
                    
                    {
                        "score_threshold": 0.7,
                        "tipe": "metadata",
                        "unlimited": True,
                        "use_reranking": True,
                        "ranker": self._metadata_ranker,
                    },
                    {
                        "score_threshold": 0.3,
                        "tipe": "metadata",
                        "unlimited": True,
                        "use_reranking": True,
                        "ranker": self._metadata_ranker,
                    },
                ],
            )

            if docs:
                rag_history = history_messages
                answer = generate_metadata_response(
                    query=query,
                    docs=docs,
                    history_messages=rag_history,
                )
            else:
                answer = (
                    "Mohon maaf, saya tidak menemukan informasi spesifik mengenai hal tersebut dalam dokumen ini."
                )
                suggestions = generate_question_suggestions(query, intent)
        elif intent == QueryIntent.SUMMARY:
            # Summary mode: ambil lebih banyak dokumen untuk mencari keterkaitan agenda.
            normalized_query = normalize_query_for_retrieval(query)
            docs = self._retrieve_with_fallback(
                normalized_query=normalized_query,
                meeting_id=meeting_id,
                configs=[
                    {
                        "k": 4,
                        "score_threshold": 0.92,
                        "use_reranking": True,
                        "tipe": "summary",
                        "ranker": self._summary_ranker,
                    },
                    {
                        "k": 4,
                        "score_threshold": 0.92,
                        "use_reranking": True,
                        "tipe": "summary",
                        "ranker": self._retrieval_ranker,
                    },
                ],
            )

            if docs:
                rag_history = history_messages
                answer = generate_summary_response(
                    query=query,
                    docs=docs,
                    history_messages=rag_history,
                )
            else:
                answer = (
                    "Mohon maaf, saya tidak menemukan informasi spesifik mengenai hal tersebut dalam dokumen ini."
                )
                suggestions = generate_question_suggestions(query, intent)

        else:
            # Safety fallback
            answer = generate_general_response(query, history_messages)

        # 3️⃣ Bangun sources (hanya jika ada dokumen)
        sources = []
        if docs:
           
           
            sources = build_sources(docs)

        result = {
            "messages": [AIMessage(content=answer)],
            "sources": sources,
            "suggestions": suggestions,
        }

        # Terminal log: show how the system identified the request and what it returned.
        # This is intentionally best-effort and should never break the request.
        try:
            self._logger.info(
                "CHAT_IDENTIFICATION %s",
                json.dumps(
                    {
                        "intent": intent,
                        "question": query,
                        "answer": answer,
                        "sources": sources,
                        "suggestions": suggestions,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
        except Exception:
            # Fallback to print if logger formatting fails for any reason.
            print(
                "CHAT_IDENTIFICATION",
                {
                    "intent": intent,
                    "question": query,
                    "answer": answer,
                    "sources": sources,
                    "suggestions": suggestions,
                },
            )

        return result

    def process_chat(
        self,
        db: Session,
        user: User,
        question: str,
        session_id: UUID = None,
        meeting_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:

        # Entry point service: kelola session chat + simpan message user/assistant ke DB.
        
        # 1. Handle Session
        if session_id:
            chat_session = db.query(ChatSession).filter(
                ChatSession.id == session_id,
                ChatSession.user_id == user.id
            ).first()
            if not chat_session:
              
                raise ValueError("Session not found or access denied")
        else:
            # Create agenda from first question (truncated)
            agenda = question[:50] + "..." if len(question) > 50 else question
            chat_session = ChatSession(user_id=user.id, agenda=agenda)
            db.add(chat_session)
            db.commit()
            db.refresh(chat_session)

        # 2. Save User Message
        user_msg = ChatMessage(
            chat_session_id=chat_session.id,
            role="user",
            body=question
        )
        db.add(user_msg)
        db.commit() # Commit to get ID and ensure stored before crash

        config = {"configurable": {"thread_id": str(chat_session.id)}}
        output = self._graph_app.invoke(
            {
                "messages": [HumanMessage(content=question)],
                "meeting_id": str(meeting_id) if meeting_id else None,
            },
            config,
        )

        messages = output.get("messages", [])
        answer = messages[-1].content if messages else ""
        sources = output.get("sources", [])
        suggestions = output.get("suggestions", [])


        # 3. Save Assistant Message
        assistant_msg = ChatMessage(
            chat_session_id=chat_session.id,
            role="assistant",
            body=answer
        )
        db.add(assistant_msg)
        db.commit()

        

        return {
            "session_id": chat_session.id,
            "answer": answer,
            "sources": sources,
            "suggestions": suggestions,
        }

    def get_user_sessions(self, db: Session, user: User) -> List[ChatSession]:
        return db.query(ChatSession).filter(
            ChatSession.user_id == user.id
        ).order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc()).all()

    def get_session_history(self, db: Session, user: User, session_id: UUID) -> List[ChatMessage]:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id
        ).first()
        
        if not session:
            return None
            
        return db.query(ChatMessage).filter(
            ChatMessage.chat_session_id == session_id
        ).order_by(ChatMessage.created_at.asc()).all()

    def create_session(self, db: Session, user: User) -> ChatSession:
        chat_session = ChatSession(user_id=user.id, agenda="New Chat")
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)
        return chat_session

    def delete_session(self, db: Session, user: User, session_id: UUID) -> bool:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        ).first()

        if not session:
            return False

        db.delete(session)
        db.commit()
        return True

    def set_session_pinned(
        self,
        db: Session,
        user: User,
        session_id: UUID,
        is_pinned: bool,
    ) -> Optional[ChatSession]:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        ).first()

        if not session:
            return None

        session.is_pinned = is_pinned
        db.commit()
        db.refresh(session)
        return session
