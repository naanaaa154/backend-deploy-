import os
from dotenv import load_dotenv

load_dotenv(override=True)  # ⬅️ WAJIB

def init_langsmith():
    project = os.getenv("LANGCHAIN_PROJECT")
    api_key = os.getenv("LANGCHAIN_API_KEY")

    if not project:
        raise RuntimeError("LANGCHAIN_PROJECT tidak terbaca dari .env")

    if not api_key:
        raise RuntimeError("LANGCHAIN_API_KEY tidak terbaca dari .env")

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ["LANGCHAIN_API_KEY"] = api_key
