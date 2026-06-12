import logging

from app.services.embedder import embed_texts
from app.services.supabase import get_client
from app.models.schemas import SearchResult

logger = logging.getLogger(__name__)


async def search_chunks(repo_id: str, query: str, top_k: int = 5) -> list[SearchResult]:
    embeddings = embed_texts([query])
    if not embeddings or not embeddings[0]:
        return []

    query_embedding = embeddings[0]
    client = get_client()

    result = client.rpc("match_code_chunks", {
        "query_embedding": query_embedding,
        "match_repo_id": repo_id,
        "match_count": top_k,
    }).execute()

    return [
        SearchResult(
            chunk_id=row["id"],
            file_path=row["file_path"],
            chunk_type=row["chunk_type"],
            similarity=round(row["similarity"], 4),
            text_preview=row["text"][:200],
            metadata=row["metadata"],
        )
        for row in result.data
    ]
