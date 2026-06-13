from langchain_postgres import PGVector
try:
    from langchain_postgres.vectorstores import DistanceStrategy
    DISTANCE_STRATEGY = DistanceStrategy.COSINE
except ImportError:
    # Fallback or assume string is accepted if enum import fails, 
    # though usually langchain_postgres has DistanceStrategy.
    DISTANCE_STRATEGY = "cosine"

from app.core.config import settings
from app.core.ollama import get_embedding

COLLECTION_NAME = "meeting_docs"

def get_vectorstore():
    return PGVector(
        embeddings=get_embedding(),
        collection_name=COLLECTION_NAME,
        connection=settings.DATABASE_URL,
        use_jsonb=True,
        distance_strategy=DISTANCE_STRATEGY,
    )

