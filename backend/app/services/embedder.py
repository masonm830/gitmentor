import logging
import math
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 32
HF_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{MODEL_NAME}"
MAX_RETRIES = 3
COLD_START_WAIT_S = 10
REQUEST_TIMEOUT_S = 120


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _embed_batch(batch: list[str]) -> list[list[float]]:
    headers = {"Authorization": f"Bearer {settings.huggingface_api_token}"}
    payload = {"inputs": batch, "options": {"wait_for_model": True}}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = httpx.post(HF_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_S)
        except httpx.RequestError as exc:
            logger.warning("HF request error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(COLD_START_WAIT_S)
            continue

        if resp.status_code == 503:
            logger.info(
                "HF model cold-starting (attempt %d/%d), waiting %ds",
                attempt, MAX_RETRIES, COLD_START_WAIT_S,
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"HF Inference API returned 503 after {MAX_RETRIES} attempts"
                )
            time.sleep(COLD_START_WAIT_S)
            continue

        resp.raise_for_status()
        return [_normalize(vec) for vec in resp.json()]

    raise RuntimeError(f"HF Inference API failed after {MAX_RETRIES} attempts")


def embed_texts(texts: list[str]) -> list[list[float]]:
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        try:
            all_embeddings.extend(_embed_batch(batch))
        except Exception:
            logger.exception("Embedding failed for batch starting at index %d", i)
            all_embeddings.extend([[] for _ in batch])

    return all_embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product equals cosine similarity when both vectors are L2-normalized,
    which they are here (embed_texts normalizes responses from the HF Inference API).

    Pure numeric op — no network call.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
