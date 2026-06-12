import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 32


def load_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded (dim=%d)", EMBEDDING_DIM)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = load_model()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        try:
            embeddings = model.encode(batch, normalize_embeddings=True)
            all_embeddings.extend(embeddings.tolist())
        except Exception:
            logger.exception("Embedding failed for batch starting at index %d", i)
            all_embeddings.extend([[] for _ in batch])

    return all_embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product is equivalent to cosine similarity when both vectors are L2-normalized,
    which they are here (sentence-transformers `normalize_embeddings=True` in embed_texts)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
