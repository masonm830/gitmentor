import json
import logging
import re

from app.agents.state import GitMentorState
from app.config import settings
from app.llm.claude_provider import ClaudeProvider

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a staff engineer drafting interview questions for a developer about THIS specific codebase. "
    "Every question must be impossible to answer without having read this repo's actual code — generic "
    "questions about REST, async, or SQL are forbidden. Every model answer must cite at least one real "
    "file path from the inputs. "
    "Function names in model answers are constrained: you may only name a function if its exact name "
    "appears verbatim in the file explanations or parsed metadata provided below. If you are unsure of "
    "the exact name, describe the behavior in plain English instead of inventing or guessing a name. "
    "Model answers describe what a strong response would COVER CONCEPTUALLY (the responsibilities, "
    "data flow, and trade-offs to discuss) — not a rigid call trace tied to one specific function name. "
    "This gives downstream grading flexibility to reward a candidate who names a different but "
    "behaviorally equivalent function. "
    "Respond with valid JSON only — no prose, no markdown fences, no explanation outside the JSON array."
)

_PROMPT_TEMPLATE = """Generate exactly 8 technical interview questions about this specific codebase.

## Architecture Overview
{architecture_overview}

## File Explanations ({file_count} files included)
{file_explanations_text}

## Required Question Mix (cover all categories — distribute the 8 across them)
1. **Data flow / control flow** (2 questions): Trace how data moves through specific files/functions.
2. **Design decisions** (2 questions): Why was a specific abstraction or boundary chosen? Reference the actual choice in the code.
3. **Failure modes** (2 questions): What breaks if X dependency is removed / Y service is down / Z input is malformed? Reference the specific file.
4. **Implementation deep-dive** (2 questions): Probe a specific function's implementation choice (algorithm, data structure, side effect, concurrency).

## Output Format

Return ONLY a JSON array of exactly 8 objects. Each object MUST have these fields:
- `question` (string): The interview question. Must name at least one specific file path or function from above.
- `category` (string): One of "data_flow", "design", "failure_mode", "implementation".
- `difficulty` (string): One of "easy", "medium", "hard". Aim for 2 easy, 4 medium, 2 hard across the 8.
- `model_answer` (string): 3-5 sentences describing what a strong answer would COVER CONCEPTUALLY — the responsibilities, data flow, and design trade-offs a candidate should discuss. Must cite at least one file path from above. Function names may only be used if they appear verbatim in the file explanations above; if you are not certain of the exact name, describe the behavior in plain English ("the route handler that processes login", "the helper that signs the JWT") rather than guessing. Must answer the question concretely — not "it depends" or "you would need to check".
- `relevant_files` (array of strings): 1-4 file paths from the provided file list that the candidate would need to read to answer.

## Hard Rules
- No question containing only generic terms ("explain how authentication works", "what is dependency injection"). Anchor every question to a concrete file or function from the inputs.
- Model answers may NOT say "the code likely does X" — be definite. If you can't be definite, pick a different question.
- Do not invent files. Every file path in `relevant_files` must appear in the file explanations above.
- Do not invent function names. A function name may appear in a model answer ONLY if that exact name appears verbatim in the file explanations above. If you are not 100% sure of the name, write the behavior in plain English ("the function that validates the token", "the handler for the /login route") — never guess a name like `validate_token()` or `handle_login()` just because it sounds plausible. Fabricated names cause downstream graders to penalize correct candidate answers.
- Write model answers as a CONCEPTUAL outline of what a strong answer would cover (responsibilities, data flow, design choices, trade-offs), not as a rigid step-by-step call trace tied to one specific function name. The grader needs flexibility to reward candidates who name a different but behaviorally equivalent function.
- Output the JSON array and nothing else. No preamble, no code fences, no trailing text."""

_MAX_FILES = 15
_MAX_EXPLANATION_CHARS = 600
_MAX_OVERVIEW_CHARS = 2500


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " [truncated]"


def _extract_json_array(text: str) -> str:
    """Pull out the first JSON array in the response, tolerating fences and stray prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


async def run_question_generator(state: GitMentorState) -> dict:
    logger.info(
        "[QuestionGenerator] Starting — repo_id=%s, file_count=%d",
        state["repo_id"],
        len(state["file_explanations"]),
    )

    explanations = state["file_explanations"]
    if not explanations:
        logger.warning("[QuestionGenerator] No file explanations available — generating from overview only")

    file_explanations_text = "\n\n".join(
        f"### {fp}\n{_truncate(explanation, _MAX_EXPLANATION_CHARS)}"
        for fp, explanation in list(explanations.items())[:_MAX_FILES]
    ) or "(no file explanations available — base questions on the architecture overview)"

    prompt = _PROMPT_TEMPLATE.format(
        architecture_overview=_truncate(state["architecture_overview"], _MAX_OVERVIEW_CHARS),
        file_count=min(len(explanations), _MAX_FILES),
        file_explanations_text=file_explanations_text,
    )

    llm = ClaudeProvider(model=settings.question_generator_model)
    try:
        raw = await llm.generate(prompt, system=_SYSTEM, temperature=0.4)
    except Exception as exc:
        logger.error("[QuestionGenerator] LLM call failed: %s", exc)
        return {
            "interview_questions": [],
            "errors": [f"QuestionGenerator failed: {exc}"],
        }

    try:
        questions = json.loads(_extract_json_array(raw))
        if not isinstance(questions, list):
            raise ValueError("Top-level JSON is not an array")
        logger.info("[QuestionGenerator] Generated %d questions", len(questions))
        return {"interview_questions": questions, "errors": []}
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("[QuestionGenerator] JSON parse failed: %s — raw[:300]=%r", exc, raw[:300])
        return {
            "interview_questions": [],
            "errors": [f"QuestionGenerator JSON parse failed: {exc}"],
        }
