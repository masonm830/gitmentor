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

# Sentinel returned by _embed_batch to distinguish "network unreachable after
# all retries" from "HTTP error / unexpected exception". Render's free tier
# blocks outbound HF calls (DNS errno -5), so the network path is the common
# failure case on prod and we degrade quietly to zero vectors there.
_NETWORK_FAILURE = object()


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _embed_batch(batch: list[str]):
    headers = {"Authorization": f"Bearer {settings.huggingface_api_token}"}
    payload = {"inputs": batch, "options": {"wait_for_model": True}}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = httpx.post(HF_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_S)
        except httpx.RequestError:
            # DNS / connection / timeout — retry silently. The caller emits
            # one summary warning if every batch fails the same way.
            if attempt < MAX_RETRIES:
                time.sleep(COLD_START_WAIT_S)
            continue

        if resp.status_code == 503:
            if attempt < MAX_RETRIES:
                time.sleep(COLD_START_WAIT_S)
                continue
            return _NETWORK_FAILURE

        resp.raise_for_status()
        return [_normalize(vec) for vec in resp.json()]

    return _NETWORK_FAILURE


def embed_texts(texts: list[str]) -> list[list[float]]:
    all_embeddings: list[list[float]] = []
    network_failure_seen = False

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        try:
            result = _embed_batch(batch)
        except Exception:
            # HTTP 4xx/5xx (non-503) or unexpected — log traceback once,
            # fall back to empty lists so downstream consumers can skip.
            logger.exception("HF embedding HTTP error (batch starting at index %d)", i)
            all_embeddings.extend([[] for _ in batch])
            continue

        if result is _NETWORK_FAILURE:
            network_failure_seen = True
            all_embeddings.extend([[0.0] * EMBEDDING_DIM for _ in batch])
        else:
            all_embeddings.extend(result)

    if network_failure_seen:
        logger.warning("HF API unreachable, returning zero embeddings")

    return all_embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product equals cosine similarity when both vectors are L2-normalized,
    which they are here (embed_texts normalizes responses from the HF Inference API).

    Pure numeric op — no network call.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
