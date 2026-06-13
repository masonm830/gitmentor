import json
import logging
import re

from app.config import settings
from app.llm.claude_provider import ClaudeProvider
from app.services.embedder import cosine_similarity, embed_texts
from app.services.rag import search_chunks

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a senior software engineer grading a candidate's answer to an interview question about a "
    "SPECIFIC codebase. You have the question, the candidate's answer, the model answer, the relevant "
    "file explanations, and RAG-retrieved code chunks. "
    "Be a strict grader. Penalize vague answers that could apply to any web app or any Python script. "
    "Reward answers that name specific functions, files, line numbers, or implementation details from "
    "the inputs. If the candidate says 'the code probably does X' without evidence, that is not partial "
    "credit — it is a gap. "
    "Grade on BEHAVIORAL ACCURACY, not exact function-name matching. The model answer is a conceptual "
    "outline of what a strong answer should cover; it is not a fixed answer key. If the candidate names "
    "a real function from the file explanations or RAG chunks that achieves the same purpose as one the "
    "model answer references, treat that as fully correct — do not penalize for using a synonym function "
    "name when the behavior described is accurate. Only penalize function-name choice when the named "
    "function does not exist in the inputs (hallucination) or when its behavior contradicts what the "
    "candidate claims it does. "
    "Respond with valid JSON only — no prose, no markdown fences."
)

_PROMPT_TEMPLATE = """Grade this interview answer.

## Question
{question}

## Candidate's answer
{user_answer}

## Model answer (for your reference — do not parrot it back, grade against it)
{model_answer}

## Relevant file explanations
{file_explanations}

## RAG-retrieved code chunks (for grounding)
{rag_chunks}

{similarity_section}

## Scoring rubric — be strict
Score each dimension 0-10. Anchor your scores to these bands:

- **accuracy** (factual correctness about what the code does):
  - 0-3: factually wrong, contradicts the code
  - 4-6: partially correct but with notable inaccuracies
  - 7-8: mostly correct, minor slips
  - 9-10: every claim about the code is verifiable from the inputs above
- **completeness** (did they cover the question's required scope):
  - 0-3: missed most of the question
  - 4-6: covered the obvious surface, missed the meat
  - 7-8: covered the main points, missed one or two
  - 9-10: covered every concept the model answer covers
- **depth** (real understanding vs. recital):
  - 0-3: pure recital of obvious facts; no "why"
  - 4-6: mentions one design choice but doesn't justify it
  - 7-8: explains why a choice was made; references trade-offs
  - 9-10: connects the code to wider engineering reasoning (perf, scale, maintainability) AND grounds each claim in a specific file/function

## Output Format
Return ONLY a JSON object with this exact shape:
{{
  "scores": {{
    "accuracy": <int 0-10>,
    "completeness": <int 0-10>,
    "depth": <int 0-10>
  }},
  "strengths": [
    "<2-3 items. Each must cite the specific code element (file or function name) the candidate referenced correctly. If the answer cites nothing concrete, the strengths list may be shorter or call this out.>"
  ],
  "gaps": [
    "<2-3 items. Each must name what was missed or wrong, and the specific file/function the candidate should have referenced.>"
  ],
  "model_answer_summary": "<2-3 sentences summarizing what a strong answer looks like — anchored to specific files/functions in the inputs above. Do not just paraphrase the model_answer verbatim.>",
  "follow_up_question": "<one question that probes the weakest dimension. Must reference a specific file or function from the inputs.>"
}}

## Hard rules
- If the candidate's answer is < 15 words or contains zero references to any file/function from the inputs, the maximum for any dimension is 4.
- Do NOT score accuracy above 5 if the candidate references files or functions that do NOT appear in the inputs above (hallucination).
- Grade behavior, not naming. If the candidate names a real function from the file explanations or RAG chunks that achieves the same behavior the model answer attributes to a different function, treat it as correct and do not list it as a gap. The model answer is a conceptual reference, not an answer key — the candidate is not required to use the same function names it does, only to describe accurate behavior grounded in real code from the inputs.
- `strengths` and `gaps` must each cite a specific code element by name — no generic feedback like "good structure" or "needs more depth".
- The `overall` score is computed by the server, do not include it. Same for `semantic_similarity`."""


def _extract_json_object(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _compute_overall(scores: dict) -> int:
    accuracy = float(scores.get("accuracy", 0))
    completeness = float(scores.get("completeness", 0))
    depth = float(scores.get("depth", 0))
    return round(accuracy * 0.4 + completeness * 0.35 + depth * 0.25)


def _semantic_similarity(user_answer: str, model_answer: str) -> float:
    if not user_answer.strip() or not model_answer.strip():
        return 0.0
    embeddings = embed_texts([user_answer, model_answer])
    if len(embeddings) < 2 or not embeddings[0] or not embeddings[1]:
        return 0.0
    return round(cosine_similarity(embeddings[0], embeddings[1]), 4)


def _format_file_explanations(file_explanations: dict[str, str], relevant_files: list[str]) -> str:
    if not relevant_files:
        return "(no relevant files identified)"
    parts = []
    for fp in relevant_files:
        text = file_explanations.get(fp)
        if text:
            parts.append(f"### {fp}\n{text[:800]}")
        else:
            parts.append(f"### {fp}\n(no explanation stored for this file)")
    return "\n\n".join(parts) if parts else "(no relevant file explanations)"


def _format_rag_chunks(chunks: list) -> str:
    if not chunks:
        return "(no chunks retrieved)"
    return "\n\n".join(
        f"[{c.chunk_type} from {c.file_path} · sim={c.similarity}]\n{c.text_preview}"
        for c in chunks
    )


async def evaluate_answer(
    repo_id: str,
    question: str,
    user_answer: str,
    model_answer: str,
    file_explanations: dict[str, str],
    relevant_files: list[str],
) -> dict:
    """Run the interview evaluator. Returns an EvaluationResult-shaped dict plus an errors list.

    Shape: {"result": {...}, "errors": [...]}
    """
    errors: list[str] = []

    try:
        rag_chunks = await search_chunks(repo_id, question, top_k=5)
    except Exception as exc:
        logger.warning("[InterviewEvaluator] RAG retrieval failed: %s", exc)
        rag_chunks = []
        errors.append(f"RAG retrieval failed: {exc}")

    raw_similarity = _semantic_similarity(user_answer, model_answer)
    # 0.0 is the failure sentinel from _semantic_similarity (embedding service
    # unreachable, empty answers, or both vectors orthogonal). A genuine 0.0
    # cosine between two non-empty natural-language answers is vanishingly rare,
    # so collapsing it to None is safe and lets us suppress the misleading row.
    effective_similarity: float | None = raw_similarity if raw_similarity > 0.0 else None

    if effective_similarity is None:
        similarity_section = ""
    elif effective_similarity > 0.85:
        similarity_section = (
            f"## Pre-computed semantic similarity (candidate vs model answer): {effective_similarity:.3f}\n"
            "The candidate's answer is semantically very close to the model answer (>0.85). "
            "Calibrate partial credit upward, but still penalize specific factual errors or missed concepts."
        )
    else:
        similarity_section = (
            f"## Pre-computed semantic similarity (candidate vs model answer): {effective_similarity:.3f}\n"
            "Semantic similarity is informational only — grade on the rubric, not on similarity."
        )

    prompt = _PROMPT_TEMPLATE.format(
        question=question,
        user_answer=user_answer,
        model_answer=model_answer or "(no model answer provided)",
        file_explanations=_format_file_explanations(file_explanations, relevant_files),
        rag_chunks=_format_rag_chunks(rag_chunks),
        similarity_section=similarity_section,
    )

    llm = ClaudeProvider(model=settings.explanation_agent_model)

    try:
        raw = await llm.generate(prompt, system=_SYSTEM, temperature=0.1)
    except Exception as exc:
        logger.exception("[InterviewEvaluator] LLM call failed")
        return {
            "result": _fallback_result(effective_similarity, f"LLM call failed: {exc}"),
            "errors": errors + [f"InterviewEvaluator LLM failed: {exc}"],
        }

    try:
        data = json.loads(_extract_json_object(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("[InterviewEvaluator] JSON parse failed: %s — raw[:300]=%r", exc, raw[:300])
        return {
            "result": _fallback_result(effective_similarity, f"JSON parse failed: {exc}"),
            "errors": errors + [f"InterviewEvaluator JSON parse failed: {exc}"],
        }

    scores = data.get("scores", {})
    accuracy = max(0, min(10, int(scores.get("accuracy", 0))))
    completeness = max(0, min(10, int(scores.get("completeness", 0))))
    depth = max(0, min(10, int(scores.get("depth", 0))))
    overall = _compute_overall({"accuracy": accuracy, "completeness": completeness, "depth": depth})

    result = {
        "scores": {
            "accuracy": accuracy,
            "completeness": completeness,
            "depth": depth,
            "overall": overall,
        },
        "semantic_similarity": effective_similarity,
        "strengths": data.get("strengths", []) or [],
        "gaps": data.get("gaps", []) or [],
        "model_answer_summary": data.get("model_answer_summary", "") or "",
        "follow_up_question": data.get("follow_up_question", "") or "",
    }
    return {"result": result, "errors": errors}


def _fallback_result(semantic_similarity: float | None, reason: str) -> dict:
    return {
        "scores": {"accuracy": 0, "completeness": 0, "depth": 0, "overall": 0},
        "semantic_similarity": semantic_similarity,
        "strengths": [],
        "gaps": [f"Evaluation could not complete: {reason}"],
        "model_answer_summary": "",
        "follow_up_question": "",
    }
