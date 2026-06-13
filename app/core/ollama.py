from langchain_ollama import ChatOllama
from langchain_ollama import OllamaEmbeddings

from app.core.config import settings

def get_llm():
    provider = settings.LLM_PROVIDER.lower()

    if provider == "groq":
        from app.core.groq import get_llm as get_groq_llm

        return get_groq_llm()

    if provider != "ollama":
        raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")

    return ChatOllama(
        model=settings.OLLAMA_LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0
    )

def get_classifier_llm():
    provider = settings.LLM_PROVIDER.lower()

    if provider == "groq":
        from app.core.groq import get_classifier_llm as get_groq_classifier_llm

        return get_groq_classifier_llm()

    if provider != "ollama":
        raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")

    return ChatOllama(
        model=settings.OLLAMA_LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0
    )

# def get_classifier_llm():
#     return ChatOllama(
#         model=settings.OLLAMA_CLASSIFIER_MODEL,
#         base_url=settings.OLLAMA_BASE_URL,
#         temperature=0
#     )

def get_embedding():
    return OllamaEmbeddings(
        model=settings.OLLAMA_EMBEDDING_MODEL,
        base_url=settings.OLLAMA_BASE_URL
    )
