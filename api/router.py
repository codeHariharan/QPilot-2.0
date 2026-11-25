import logging
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest, QueryResponse
from src.embedding import EmbeddingManager
from src.generation import RAGRetriever
from src.vectore_store import VectorStore

logger = logging.getLogger(__name__)
router = APIRouter()

APP_DIR = Path(__file__).resolve().parents[1]
SESSION_ROOT = APP_DIR / "temp"

with (APP_DIR / "config" / "config.yml").open(encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)


@lru_cache(maxsize=1)
def get_embedding_manager() -> EmbeddingManager:
    # Loaded once, on the first request, then reused.
    return EmbeddingManager(CONFIG["model_name"])


@router.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest) -> QueryResponse:
    session_dir = SESSION_ROOT / request.session_id
    if not session_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Session not found. Upload and index documents first.",
        )

    vector_store = VectorStore(
        collection_name=CONFIG["vector_store"]["collection_name"],
        persistant_dir=str(session_dir / "vector_store"),
    )
    try:
        retriever = RAGRetriever(vector_store, get_embedding_manager())
        answer = retriever.generate(request.query, retriever, top_k=request.top_k)
    except Exception:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail="Could not generate an answer.")
    finally:
        vector_store.client.close()

    return QueryResponse(answer=answer)