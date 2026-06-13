from typing import List, Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import json
import re

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage

from app.core.ollama import get_classifier_llm
from app.core.ollama import get_llm
from app.rag.services.retrieval.prompts import (
    build_correction_and_intent_prompt,
    build_question_suggestions_prompt,
)

from .chat_types import QueryIntent


def _safe_json_loads(raw_text: str) -> Optional[Any]:
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except Exception:
        return None


def _normalize_payload_keys(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        normalized_key = key.strip().lower().replace(" ", "_")
        normalized[normalized_key] = value
    return normalized


def _extract_field_from_text(text: str, key: str) -> Optional[str]:
    pattern = rf"{key}\s*[:=]\s*(\".*?\"|'.*?'|[^\n,]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip()
    if (value.startswith("\"") and value.endswith("\"")) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return value.strip()


def _parse_correction_intent_response(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        return {}

    text = raw_text.strip()
    if not text:
        return {}

    if "```" in text:
        text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()

    payload = _safe_json_loads(text)
    if payload is None:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            payload = _safe_json_loads(match.group(0))

    if isinstance(payload, dict):
        return _normalize_payload_keys(payload)

    extracted: Dict[str, Any] = {}
    corrected_question = _extract_field_from_text(text, "corrected_question")
    if corrected_question:
        extracted["corrected_question"] = corrected_question

    classify_intent = _extract_field_from_text(text, "classify_intent")
    if classify_intent:
        extracted["classify_intent"] = classify_intent
    else:
        intent_match = re.search(
            r"\b(GENERAL|METADATA|RETRIEVAL|SUMMARY)\b",
            text,
            flags=re.IGNORECASE,
        )
        if intent_match:
            extracted["classify_intent"] = intent_match.group(1).upper()

    alasan = _extract_field_from_text(text, "alasan")
    if alasan:
        extracted["alasan"] = alasan

    return extracted


def normalize_query_for_retrieval(query: str) -> str:
    """
    Normalisasi query untuk retrieval saja:
    - lowercase
    - hilangkan tanda baca (.,!? dll)
    - rapikan spasi berlebih
    Catatan: prompt/LLM tetap memakai pertanyaan asli.
    """
    cleaned = query.lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query


def correct_and_classify_intent(query: str) -> Dict[str, Any]:
    """
    Gabungkan proses perbaikan query dan klasifikasi intent.
    Return JSON dengan key: corrected_question dan classify_intent.
    """
    if not query:
        return {
            "corrected_question": query,
            "classify_intent": QueryIntent.RETRIEVAL,
        }

    llm = get_classifier_llm()
    prompt = build_correction_and_intent_prompt(query)

    try:
        response = llm.invoke(prompt)
        payload = _parse_correction_intent_response(response.content)
    except Exception:
        payload = {}

    corrected_question = payload.get("corrected_question") or query
    intent = (payload.get("classify_intent") or QueryIntent.RETRIEVAL).upper()

    valid_intents = {
        QueryIntent.GENERAL,
        QueryIntent.RETRIEVAL,
        QueryIntent.METADATA,
        QueryIntent.SUMMARY,
    }
    if intent not in valid_intents:
        intent = QueryIntent.RETRIEVAL

    return {
        "corrected_question": corrected_question,
        "classify_intent": intent,
        "alasan": payload.get("alasan", ""),
    }


def extract_history_and_query(
    messages: List[BaseMessage],
) -> tuple[List[BaseMessage], str]:
    # Ambil pertanyaan terakhir user sebagai query, sisanya dianggap history.
    if not messages:
        return [], ""

    last_human_index = None
    for idx in range(len(messages) - 1, -1, -1):
        if isinstance(messages[idx], HumanMessage):
            last_human_index = idx
            break

    if last_human_index is None:
        return messages, ""

    history = messages[:last_human_index]
    query = messages[last_human_index].content
    return history, query


def trim_history(history_messages: List[BaseMessage], max_messages: int = 0) -> List[BaseMessage]:
    # Batasi history yang disertakan agar prompt tetap pendek.
    if not history_messages:
        return []
    return history_messages[-max_messages:]


def format_context(docs: List[Document]) -> str:
    # Gabungkan isi dokumen menjadi satu string context untuk prompt RAG.
    # Hanya isi dokumen tanpa label tambahan (factual source)
    return "\n\n".join(doc.page_content for doc in docs)


def build_sources(docs: List[Document]) -> List[Dict[str, Any]]:
    # Bangun source metadata untuk response.
    allowed_keys = {
        "date",
        "tanggal pelaksanaan",
        "agenda",
        "main_topic",
        "meeting_id",
        "chunk_index",
        "participants",
        "vector_score",
        "re_rank_score",
    }

    return [
        {
            **{
                k: d.metadata.get(k)
                for k in allowed_keys
                if d.metadata.get(k) is not None
            },
            "content": d.page_content,
        }
        for d in docs
    ]


def _fallback_question_suggestions(query: str, intent: str, max_questions: int) -> List[str]:
    topic = (query or "").strip()
    if len(topic) > 80:
        topic = topic[:77].rstrip() + "..."

    base_questions = [
        f"Agenda mana yang membahas {topic}?" if topic else "Agenda mana yang relevan dengan topik ini?",
        f"Kapan rapat terkait {topic} dilaksanakan?" if topic else "Kapan rapat terkait topik ini dilaksanakan?",
        f"Siapa saja peserta yang hadir pada rapat tentang {topic}?" if topic else "Siapa saja peserta yang hadir pada rapat terkait topik ini?",
        f"Apa kata kunci utama dalam rapat terkait {topic}?" if topic else "Apa kata kunci utama dalam rapat terkait topik ini?",
    ]

    if intent == QueryIntent.SUMMARY:
        base_questions.insert(0, "Apakah Anda ingin ringkasan dari agenda tertentu?")
    elif intent == QueryIntent.METADATA:
        base_questions.insert(0, "Apakah Anda mencari daftar agenda, peserta, atau tanggal tertentu?")

    unique_questions = []
    for q in base_questions:
        if q not in unique_questions:
            unique_questions.append(q)
        if len(unique_questions) >= max_questions:
            break

    return unique_questions


def generate_question_suggestions(
    query: str,
    intent: str,
    max_questions: int = 4,
) -> List[str]:
    if not query:
        return []

    llm = get_llm()
    prompt = build_question_suggestions_prompt(
        query=query,
        intent=intent,
        max_questions=max_questions,
    )

    suggestions: List[str] = []
    try:
        response = llm.invoke(prompt)
        payload = json.loads(response.content)
        if isinstance(payload, dict):
            payload = payload.get("suggestions") or payload.get("questions") or []
        if isinstance(payload, list):
            suggestions = [str(item).strip() for item in payload if str(item).strip()]
    except Exception:
        suggestions = []

    if not suggestions:
        suggestions = _fallback_question_suggestions(query, intent, max_questions)

    return suggestions[:max_questions]