import logging

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 32

# Lazy. `sentence_transformers` pulls in torch + transformers + tokenizers on
# import (~300MB resident), which puts a Render free-tier 512MB box over the
# limit before a request is even served. We defer both the import and the
# model load until the first embed/eval call.
_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # noqa: WPS433
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded (dim=%d)", EMBEDDING_DIM)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
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
    which they are here (sentence-transformers `normalize_embeddings=True` in embed_texts).

    Does not touch the model — pure numeric op, safe to call without triggering the lazy load.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
