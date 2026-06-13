from typing import List, Dict, Any, TypedDict, Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    # State LangGraph:
    # - messages: history chat (Human/AI)
    # - sources: sumber dokumen yang dipakai untuk menjawab
    messages: Annotated[List[BaseMessage], add_messages]
    sources: Optional[List[Dict[str, Any]]]
    suggestions: Optional[List[str]]
    meeting_id: Optional[str]


class QueryIntent:
    # Kategori intent pertanyaan (dipakai untuk routing jalur pemrosesan).
    GENERAL = "GENERAL"
    RETRIEVAL = "RETRIEVAL"
    METADATA = "METADATA"
    SUMMARY = "SUMMARY"