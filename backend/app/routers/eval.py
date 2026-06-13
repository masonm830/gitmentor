"""Phase 7 eval endpoints.

POST /api/eval/run   — runs the golden dataset through the evaluator,
                      stores the report in eval_runs, returns the report.
GET  /api/eval/runs  — last 10 eval_runs rows for the dashboard.

Intentionally unauthenticated — this is an internal developer tool.
"""
from dataclasses import asdict
import logging

from fastapi import APIRouter, HTTPException

from app.eval.harness import run_eval
from app.services import supabase as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eval")


@router.post("/run")
async def run_eval_endpoint():
    """Runs the full golden-dataset eval. Takes 2-5 minutes."""
    logger.info("[eval] /api/eval/run invoked")
    try:
        report = await run_eval()
    except Exception as exc:
        logger.exception("[eval] harness failed")
        raise HTTPException(status_code=500, detail=f"Eval harness failed: {exc}")

    report_dict = asdict(report)
    try:
        run_id = await db.store_eval_run(report_dict)
        report_dict["id"] = run_id
    except Exception as exc:
        logger.exception("[eval] persist failed")
        # Eval ran successfully — still return it to the caller even if persist failed.
        report_dict["persist_error"] = str(exc)

    logger.info(
        "[eval] complete — pass_rate=%.2f avg_overall=%.2f",
        report.pass_rate,
        report.avg_overall,
    )
    return report_dict


@router.get("/runs")
async def list_eval_runs():
    """Last 10 eval runs, newest first."""
    rows = await db.list_recent_eval_runs(limit=10)
    return {"runs": rows}
