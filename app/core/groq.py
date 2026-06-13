from langchain_groq import ChatGroq

from app.core.config import settings


def get_llm():
	if not settings.GROQ_API_KEY:
		raise ValueError("GROQ_API_KEY is not set. Please configure it in your environment.")

	return ChatGroq(
		model=settings.GROQ_LLM_MODEL,
		api_key=settings.GROQ_API_KEY,
		temperature=0,
	)

def get_classifier_llm():
	if not settings.GROQ_API_KEY:
		raise ValueError("GROQ_API_KEY is not set. Please configure it in your environment.")

	return ChatGroq(
		model=settings.GROQ_LLM_MODEL_CLASSIFIER,
		api_key=settings.GROQ_API_KEY,
		temperature=0,
	)
