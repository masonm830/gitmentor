import asyncio
import logging

from langgraph.graph import END, START, StateGraph

from app.agents.explanation_agent import run_explanation_agent
from app.agents.gap_detector import run_gap_detector
from app.agents.question_generator import run_question_generator
from app.agents.repo_analyzer import run_repo_analyzer
from app.agents.state import GitMentorState

logger = logging.getLogger(__name__)


async def _safe_repo_analyzer(state: GitMentorState) -> dict:
    try:
        return await run_repo_analyzer(state)
    except Exception as exc:
        logger.exception("[Graph] repo_analyzer crashed — pipeline continues with empty overview")
        return {
            "architecture_overview": "",
            "status": "repo_analyzer_crashed",
            "errors": [f"RepoAnalyzer crashed: {exc}"],
        }


async def _safe_explanation_agent(state: GitMentorState) -> dict:
    try:
        return await run_explanation_agent(state)
    except Exception as exc:
        logger.exception("[Graph] explanation_agent crashed — downstream agents will run without explanations")
        return {
            "file_explanations": {},
            "status": "explanation_agent_crashed",
            "errors": [f"ExplanationAgent crashed: {exc}"],
        }


async def _parallel_qa_gap(state: GitMentorState) -> dict:
    """Run question_generator and gap_detector concurrently and merge results.

    Each branch is isolated: a raised exception in one does not stop the other,
    and partial results from the surviving branch still land in state.
    """
    logger.info("[Graph] Running question_generator + gap_detector in parallel — repo_id=%s", state["repo_id"])

    qg_result, gd_result = await asyncio.gather(
        run_question_generator(state),
        run_gap_detector(state),
        return_exceptions=True,
    )

    update: dict = {"errors": []}
    statuses: list[str] = []

    if isinstance(qg_result, Exception):
        logger.error("[Graph] question_generator raised: %s", qg_result)
        update["interview_questions"] = []
        update["errors"].append(f"QuestionGenerator raised: {qg_result}")
        statuses.append("question_generator_failed")
    else:
        update["interview_questions"] = qg_result.get("interview_questions", [])
        update["errors"].extend(qg_result.get("errors", []))
        statuses.append("question_generator_ok" if update["interview_questions"] else "question_generator_empty")

    if isinstance(gd_result, Exception):
        logger.error("[Graph] gap_detector raised: %s", gd_result)
        update["gap_analysis"] = {}
        update["errors"].append(f"GapDetector raised: {gd_result}")
        statuses.append("gap_detector_failed")
    else:
        update["gap_analysis"] = gd_result.get("gap_analysis", {})
        update["errors"].extend(gd_result.get("errors", []))
        statuses.append("gap_detector_ok" if update["gap_analysis"] else "gap_detector_empty")

    if all(s.endswith("_failed") for s in statuses):
        update["status"] = "analysis_failed"
    elif any(s.endswith("_failed") or s.endswith("_empty") for s in statuses):
        update["status"] = "analysis_partial"
    else:
        update["status"] = "analysis_complete"

    logger.info("[Graph] Parallel stage done — status=%s, errors=%d", update["status"], len(update["errors"]))
    return update


def build_graph():
    builder = StateGraph(GitMentorState)

    builder.add_node("repo_analyzer", _safe_repo_analyzer)
    builder.add_node("explanation_agent", _safe_explanation_agent)
    builder.add_node("parallel_qa_gap", _parallel_qa_gap)

    builder.add_edge(START, "repo_analyzer")
    builder.add_edge("repo_analyzer", "explanation_agent")
    builder.add_edge("explanation_agent", "parallel_qa_gap")
    builder.add_edge("parallel_qa_gap", END)

    return builder.compile()
