import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.agents.interview_evaluator import evaluate_answer
from app.models.schemas import (
    InterviewStartRequest, InterviewStartResponse, InterviewQuestionPublic,
    InterviewEvaluateRequest, InterviewEvaluateResponse, EvaluationResult,
)
from app.services import supabase as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post(
    "/repos/{repo_id}/interview/start",
    response_model=InterviewStartResponse,
)
async def interview_start(repo_id: str, body: InterviewStartRequest):
    """Start a mock interview session for the given analysis.

    Returns all 8 questions (sanitized — no model_answer) for the frontend to display.
    Pre-creates 8 rows in interview_sessions so /evaluate can do a deterministic UPDATE.
    """
    analysis = await db.get_analysis(body.analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.get("repo_id") != repo_id:
        raise HTTPException(status_code=400, detail="analysis_id does not belong to this repo")

    questions = analysis.get("interview_questions") or []
    if not questions:
        raise HTTPException(status_code=400, detail="Analysis has no interview questions")

    session_id = str(uuid.uuid4())

    try:
        await db.create_interview_session_rows(session_id, repo_id, body.analysis_id, questions)
    except Exception as exc:
        logger.exception("[Interview] Failed to create session rows")
        raise HTTPException(status_code=500, detail=f"Could not create interview session: {exc}")

    public_questions = [
        InterviewQuestionPublic(
            index=idx,
            question=q.get("question", ""),
            category=q.get("category"),
            difficulty=q.get("difficulty"),
            relevant_files=q.get("relevant_files", []) or [],
        )
        for idx, q in enumerate(questions)
    ]

    logger.info(
        "[Interview] Started session %s — repo=%s analysis=%s, %d questions",
        session_id, repo_id, body.analysis_id, len(public_questions),
    )

    return InterviewStartResponse(
        session_id=session_id,
        repo_id=repo_id,
        analysis_id=body.analysis_id,
        questions=public_questions,
    )


@router.post(
    "/repos/{repo_id}/interview/evaluate",
    response_model=InterviewEvaluateResponse,
)
async def interview_evaluate(repo_id: str, body: InterviewEvaluateRequest):
    """Evaluate a candidate's answer to a specific question in a session.

    Loads the question + model_answer from the analyses table (model_answer never
    crosses the wire to the client) and runs the InterviewEvaluator agent.
    """
    row = await db.get_interview_session_row(body.session_id, body.question_index)
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No row for that (session_id, question_index). Did you call /interview/start?",
        )
    if row.get("repo_id") != repo_id:
        raise HTTPException(status_code=400, detail="session_id does not belong to this repo")

    analysis = await db.get_analysis(row["analysis_id"])
    if not analysis:
        raise HTTPException(status_code=404, detail="Underlying analysis no longer exists")

    questions = analysis.get("interview_questions") or []
    if body.question_index < 0 or body.question_index >= len(questions):
        raise HTTPException(status_code=400, detail="question_index out of range")

    question_obj = questions[body.question_index]
    question_text = question_obj.get("question", "")
    model_answer = question_obj.get("model_answer", "")
    relevant_files = question_obj.get("relevant_files", []) or []
    file_explanations = analysis.get("file_explanations") or {}

    logger.info(
        "[Interview] Evaluating session=%s q_idx=%d (user_answer=%d chars, %d relevant files)",
        body.session_id, body.question_index, len(body.user_answer), len(relevant_files),
    )

    eval_payload = await evaluate_answer(
        repo_id=repo_id,
        question=question_text,
        user_answer=body.user_answer,
        model_answer=model_answer,
        file_explanations=file_explanations,
        relevant_files=relevant_files,
    )
    result = eval_payload["result"]
    errors = eval_payload["errors"]

    try:
        await db.update_interview_evaluation(
            body.session_id, body.question_index, body.user_answer, result,
        )
    except Exception as exc:
        logger.exception("[Interview] Failed to persist evaluation")
        errors.append(f"Persist failed: {exc}")

    return InterviewEvaluateResponse(
        session_id=body.session_id,
        question_index=body.question_index,
        evaluation=EvaluationResult(**result),
        errors=errors,
    )
