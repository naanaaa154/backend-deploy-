from typing import List

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.ollama import get_llm
from app.rag.services.retrieval.prompts import (
    SYSTEM_PROMPT_GENERAL,
    SYSTEM_PROMPT_METADATA,
    SYSTEM_PROMPT_RETRIEVAL,
    SYSTEM_PROMPT_SUMMARY,
)

from .chat_helpers import format_context, trim_history


def generate_general_response(
    query: str,
    history_messages: List[BaseMessage],
) -> str:
    # Jawaban general (tanpa konteks dokumen rapat).
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT_GENERAL),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ]
    )
    chain = prompt | llm
    response = chain.invoke(
        {
            "history": history_messages,
            "question": query,
        },
    )
    return response.content


def _generate_contextual_response(
    query: str,
    docs: List[Document],
    history_messages: List[BaseMessage],
    system_prompt: str,
) -> str:
    # Jawaban berbasis dokumen: LLM dipandu agar hanya menjawab berdasarkan konteks.
    llm = get_llm()
    context = format_context(docs)

    trimmed_history = trim_history(history_messages)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "Konteks:\n{context}\n\nPertanyaan:\n{question}"),
        ]
    )
    chain = prompt | llm

    response = chain.invoke(
        {
            "context": context,
            "question": query,
            "history": trimmed_history,
        },
    )

    return response.content


def generate_retrieval_response(
    query: str,
    docs: List[Document],
    history_messages: List[BaseMessage],
) -> str:
    # Jalur RETRIEVAL: pertanyaan isi dokumen.
    return _generate_contextual_response(
        query=query,
        docs=docs,
        history_messages=history_messages,
        system_prompt=SYSTEM_PROMPT_RETRIEVAL,
    )


def generate_metadata_response(
    query: str,
    docs: List[Document],
    history_messages: List[BaseMessage],
) -> str:
    return _generate_contextual_response(
        query=query,
        docs=docs,
        history_messages=history_messages,
        system_prompt=SYSTEM_PROMPT_METADATA,
    )


def generate_summary_response(
    query: str,
    docs: List[Document],
    history_messages: List[BaseMessage],
) -> str:
    return _generate_contextual_response(
        query=query,
        docs=docs,
        history_messages=history_messages,
        system_prompt=SYSTEM_PROMPT_SUMMARY,
    )

    
# def generate_metadata_response(
#     query: str,
#     docs: List[Document],
#     history_messages: List[BaseMessage],
# ) -> str:
#     # Jalur METADATA: pertanyaan daftar/identitas metadata rapat.
#     return _generate_contextual_response(
#         query=query,
#         docs=docs,
#         history_messages=history_messages,
#         system_prompt=SYSTEM_PROMPT_METADATA,
#     )