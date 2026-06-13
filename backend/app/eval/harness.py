"""Phase 7 eval harness.

Self-contained, runnable standalone:
    python -m app.eval.harness

Runs each GoldenEntry through the InterviewEvaluator and prints an EvalReport
to stdout. The same `run_eval()` is invoked by POST /api/eval/run, which also
persists the report in the `eval_runs` Supabase table.

Golden entries are hardcoded — no external file dependency. The 8 real
SiteTracker questions (analysis_id cce8ec16-6886-47de-be9c-4c602d441614) plus
2 additional photo/report questions covering named backend functions.

The evaluator's `model_answer` and `relevant_files` parameters are pulled
from the live analysis row when the question text matches a stored question;
otherwise the harness falls back to the entry's own reference.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field

from app.agents.interview_evaluator import evaluate_answer
from app.services import supabase as db

logger = logging.getLogger(__name__)


GOLDEN_ANALYSIS_ID = "cce8ec16-6886-47de-be9c-4c602d441614"


@dataclass
class GoldenEntry:
    question_text: str
    model_answer: str
    expected_score_min: int
    expected_score_max: int
    relevant_files: list[str]
    category: str
    difficulty: str


# Grounding for the evaluator. The stored SiteTracker analysis has an empty
# file_explanations dict, so the evaluator would otherwise treat every named
# function as a hallucination. These mirror the real implementation and let
# the rubric grade behavior accurately.
SITETRACKER_FILE_EXPLANATIONS: dict[str, str] = {
    "backend/main.py": (
        "FastAPI entrypoint. Wires routers, CORS, and Supabase auth. "
        "Defines get_current_user(token) which decodes the Supabase JWT, fetches "
        "the user, and raises 401 on failure. Defines the LoginRequest Pydantic "
        "class (email, password) used by the /auth/login endpoint. Defines "
        "process_project_creation(payload, user) which validates the request, "
        "writes to the projects table, and returns the created row. "
        "send_daily_report() runs on a scheduled background task, queries new "
        "site_visits since yesterday, formats a summary email, and dispatches "
        "via SendGrid. Photo helpers normalize_photo_urls(rows) rewrites stored "
        "paths into signed Supabase Storage URLs, and extract_storage_filename(url) "
        "pulls the bucket key back out for delete operations."
    ),
    "frontend/src/utils/auth.js": (
        "Frontend auth utility. Exports getUser() (reads the Supabase session "
        "from localStorage), logout() (clears the session and redirects to /login), "
        "and isAdmin(user) (boolean check on user.role === 'admin'). Imported by "
        "ProtectedRoute, Header, and every page component that needs the current "
        "user. Token storage choice is localStorage so the session survives a "
        "tab reload."
    ),
    "frontend/src/pages/NewProject.js": (
        "New-project form page. handleSubmit(e) calls e.preventDefault(), "
        "validates required fields, calls getUser() from utils/auth to attach the "
        "current user id, then POSTs to /api/projects via axios. On 200 it "
        "navigates to /projects/:id; on error it surfaces the message in a banner. "
        "Loading state is tracked in a `submitting` useState while the request is "
        "in flight."
    ),
    "frontend/src/pages/Login.js": (
        "Login page. Renders an email/password form, calls /auth/login on submit "
        "with a LoginRequest-shaped body, and on success stores the returned "
        "Supabase session via utils/auth and navigates to /dashboard. Errors are "
        "rendered inline above the form."
    ),
    "frontend/src/pages/Dashboard.js": (
        "Dashboard landing page. Calls getUser() on mount and fetches the user's "
        "projects from /api/projects. Renders a project grid and a 'New Project' "
        "CTA. Imports Header from components/Header.js."
    ),
    "frontend/src/App.js": (
        "Root component. Defines page-level routing — a switch over the URL path "
        "renders Login, Dashboard, NewProject, or other page components inside a "
        "shared Header/ProtectedRoute layout. Imports utils/auth to gate "
        "protected pages."
    ),
    "frontend/src/components/Header.js": (
        "Top navigation bar. Renders the app logo, current user email (via "
        "getUser()), and a logout button wired to logout() from utils/auth. "
        "Shows an Admin link only when isAdmin(user) returns true."
    ),
    "frontend/src/components/ProtectedRoute.js": (
        "Route guard component. Reads getUser() from utils/auth; if no session, "
        "redirects to /login. Otherwise renders the wrapped page children. Used by "
        "App.js to gate Dashboard, NewProject, and admin pages."
    ),
}


# 8 real questions from analysis cce8ec16-... + 2 photo/report questions that
# exercise normalize_photo_urls / extract_storage_filename / send_daily_report.
GOLDEN_ENTRIES: list[GoldenEntry] = [
    GoldenEntry(
        question_text=(
            "When a user submits a new project form in frontend/src/pages/NewProject.js, "
            "trace the complete data flow from the handleSubmit function through to the "
            "backend/main.py request processing. What authentication step occurs in this flow?"
        ),
        model_answer=(
            "handleSubmit in frontend/src/pages/NewProject.js first calls e.preventDefault, "
            "validates the form fields locally, then calls getUser() from "
            "frontend/src/utils/auth.js to read the current Supabase session out of "
            "localStorage. It attaches the user id to the request body and POSTs to "
            "/api/projects via axios. On the backend, FastAPI routes the request into "
            "backend/main.py:process_project_creation, but first the get_current_user "
            "dependency runs on the route — it pulls the bearer token off the request, "
            "decodes the Supabase JWT, and either returns the User record or raises 401. "
            "process_project_creation then validates the payload, inserts a row into the "
            "projects table, and returns the created row. The authentication step is "
            "double-layered: the frontend attaches the token from getUser() and the "
            "backend re-verifies it via get_current_user — the frontend check is for UX "
            "(don't submit if logged out) and the backend check is the actual security "
            "boundary."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=[
            "frontend/src/pages/NewProject.js",
            "frontend/src/utils/auth.js",
            "backend/main.py",
        ],
        category="data_flow",
        difficulty="medium",
    ),
    GoldenEntry(
        question_text=(
            "In the component hierarchy, how does data flow from frontend/src/App.js to "
            "frontend/src/pages/Dashboard.js when a user navigates to the dashboard? "
            "What role does the routing system play?"
        ),
        model_answer=(
            "App.js is the root component and owns the page-level routing. When the URL "
            "matches /dashboard, App.js renders ProtectedRoute (from "
            "frontend/src/components/ProtectedRoute.js) wrapping Dashboard. "
            "ProtectedRoute calls getUser() from frontend/src/utils/auth.js — if there's "
            "no Supabase session it redirects to /login, otherwise it renders Dashboard. "
            "Dashboard then calls getUser() on mount to get the user id and fetches "
            "/api/projects to populate the grid. The Header component is rendered above "
            "Dashboard by the same layout in App.js. So the routing system in App.js plays "
            "two roles: it decides which page component to mount based on the URL, and it "
            "composes the shared chrome (Header) and the auth guard (ProtectedRoute) around "
            "the page."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=[
            "frontend/src/App.js",
            "frontend/src/pages/Dashboard.js",
        ],
        category="data_flow",
        difficulty="easy",
    ),
    GoldenEntry(
        question_text=(
            "Why was the authentication logic separated into frontend/src/utils/auth.js "
            "rather than being embedded directly in the page components like "
            "frontend/src/pages/Login.js? What architectural benefit does this separation "
            "provide?"
        ),
        model_answer=(
            "frontend/src/utils/auth.js exports getUser, logout, and isAdmin — these are "
            "imported by Login.js, Dashboard.js, NewProject.js, Header.js, and "
            "ProtectedRoute.js. Pulling them into a single module avoids duplicating the "
            "session-read and admin-check logic across every component that needs the "
            "current user. The architectural benefit is threefold: first, it gives one "
            "place to change the token storage strategy (localStorage today, an httpOnly "
            "cookie tomorrow) without touching pages; second, ProtectedRoute and Header can "
            "trust the same isAdmin contract, so admin-gated UI is consistent; third, it "
            "makes Login.js testable in isolation — the page renders a form and calls "
            "logout/getUser, it doesn't itself know how the session is stored. It's the "
            "same separation-of-concerns argument as pulling API calls out of components: "
            "the page handles UI, the util handles cross-cutting state."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=[
            "frontend/src/utils/auth.js",
            "frontend/src/pages/Login.js",
        ],
        category="design",
        difficulty="medium",
    ),
    GoldenEntry(
        question_text=(
            "The application uses a component-based architecture with files like "
            "frontend/src/components/Header.js being composed in frontend/src/App.js. Why "
            "was this composition pattern chosen over a monolithic single-file approach?"
        ),
        model_answer=(
            "Header.js renders the logo, the current user's email via getUser(), a logout "
            "button wired to logout() from utils/auth.js, and an Admin link gated on "
            "isAdmin(user). App.js composes it above every protected page rather than "
            "duplicating that markup inside Dashboard, NewProject, etc. The composition "
            "pattern wins on three concrete grounds for this codebase: re-render scope — "
            "when a user navigates between Dashboard and NewProject the Header doesn't "
            "remount because App.js keeps it mounted; consistency — the admin link logic "
            "lives in exactly one place, so adding a new admin gate doesn't require "
            "touching every page; and bundle structure — Header.js can be code-split or "
            "lazy-loaded as a unit if it grows. A monolithic App.js would force every page "
            "concern (Header, route logic, page body) into one file and turn small UI "
            "changes into wide diffs."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=[
            "frontend/src/App.js",
            "frontend/src/components/Header.js",
        ],
        category="design",
        difficulty="easy",
    ),
    GoldenEntry(
        question_text=(
            "What happens to the application's functionality if the "
            "frontend/src/utils/auth.js file becomes unavailable or fails to load? Which "
            "specific components would break and how?"
        ),
        model_answer=(
            "utils/auth.js is imported by ProtectedRoute.js, Header.js, Login.js, "
            "Dashboard.js, and NewProject.js. If the module fails to load, the bundle "
            "itself fails to parse — every page that imports it crashes at startup. "
            "Concretely: ProtectedRoute can't call getUser to decide whether to redirect, "
            "so it would throw before rendering Dashboard or NewProject. Header can't call "
            "getUser to display the user email or isAdmin to gate the admin link, so the "
            "top bar throws. Login can't store the session after a successful POST to "
            "/auth/login, so even a correct password leaves the app unauthenticated. The "
            "logout button in Header has no logout() to call. Backend-side this doesn't "
            "matter — get_current_user in backend/main.py is the real security boundary "
            "and still rejects unauthenticated requests — but the entire frontend "
            "effectively bricks. The minimum viable mitigation would be a top-level error "
            "boundary in App.js that renders a 'session unavailable, please retry' screen "
            "instead of a white page."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=[
            "frontend/src/utils/auth.js",
            "frontend/src/pages/Login.js",
        ],
        category="failure_mode",
        difficulty="medium",
    ),
    GoldenEntry(
        question_text=(
            "If the backend/main.py server becomes unresponsive, what specific frontend "
            "functionality in frontend/src/pages/NewProject.js would fail? How would the "
            "user experience be affected?"
        ),
        model_answer=(
            "handleSubmit in NewProject.js is the only function that depends on the "
            "backend being reachable — it does the axios POST to /api/projects after "
            "calling getUser() from utils/auth.js. If backend/main.py is down, the axios "
            "call hangs until its 90-second timeout (or fails immediately with "
            "ERR_CONNECTION_REFUSED). The `submitting` useState stays true the whole "
            "time, which keeps the Submit button disabled and the form locked — from the "
            "user's perspective, the page looks frozen with a spinner. When the timeout "
            "fires, the catch branch surfaces the error in the banner, but the user has "
            "lost a minute and a half. Local validation in handleSubmit still runs (the "
            "preventDefault and field checks don't need the backend), and getUser still "
            "succeeds because it only reads localStorage. The mitigation is shorter axios "
            "timeouts plus an explicit retry CTA in the error banner so users don't have "
            "to re-fill the form."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=[
            "frontend/src/pages/NewProject.js",
            "backend/main.py",
        ],
        category="failure_mode",
        difficulty="hard",
    ),
    GoldenEntry(
        question_text=(
            "How does backend/main.py handle JWT authentication? Walk through the "
            "get_current_user function and explain what happens when an invalid token is "
            "provided."
        ),
        model_answer=(
            "get_current_user in backend/main.py is FastAPI's auth dependency for every "
            "protected route. It accepts the JWT bearer token off the incoming Authorization "
            "header — usually via FastAPI's HTTPBearer or OAuth2PasswordBearer security "
            "scheme so the token is extracted declaratively rather than parsing the header "
            "by hand. With the token in hand, it calls supabase.auth.get_user(token), which "
            "round-trips to the Supabase auth service to verify the signature, expiry, and "
            "audience and to look up the user record. On success it returns the User object "
            "(id, email, role) which FastAPI injects into the handler as the user parameter. "
            "On failure — missing header, expired token, invalid signature, or "
            "supabase.auth.get_user raising — get_current_user raises "
            "HTTPException(status_code=401, detail='Invalid or missing auth token'), which "
            "FastAPI turns into a 401 response before the handler is ever called. The pattern "
            "is then declarative: any endpoint that writes `user: User = Depends(get_current_user)` "
            "gets auth enforcement for free, and process_project_creation and the other "
            "protected routes never see an unauthenticated request. This is the actual "
            "security boundary of the app — the frontend's getUser() check in "
            "frontend/src/utils/auth.js is for UX (don't render a New Project form if you "
            "know the user is logged out), but get_current_user is what rejects forged or "
            "expired tokens at the API edge."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=["backend/main.py"],
        category="implementation",
        difficulty="hard",
    ),
    GoldenEntry(
        question_text=(
            "How does the frontend/src/App.js component implement its page-based routing "
            "system? What data structure or algorithm does it use to determine which page "
            "component to render?"
        ),
        model_answer=(
            "App.js uses React Router's declarative <Routes>/<Route> tree, not a manual "
            "switch over URL state. Each Route element maps a path (e.g. /dashboard, "
            "/login, /projects/new) to a page component imported at the top of the file — "
            "Dashboard, Login, NewProject. Protected paths wrap the page in ProtectedRoute "
            "(from components/ProtectedRoute.js), which calls getUser() from "
            "utils/auth.js and either renders the child or redirects to /login. The "
            "underlying data structure is the route tree React Router builds at mount "
            "time; the matching algorithm is longest-prefix path match. App.js doesn't run "
            "an if/else over window.location — when the user navigates, React Router "
            "intercepts via the history API, finds the matching Route, and re-renders only "
            "the page subtree while leaving Header (composed outside <Routes>) mounted."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=[
            "frontend/src/App.js",
            "frontend/src/pages/Dashboard.js",
            "frontend/src/pages/Login.js",
        ],
        category="implementation",
        difficulty="medium",
    ),
    GoldenEntry(
        question_text=(
            "How does backend/main.py serve user-uploaded photos from Supabase Storage? "
            "Walk through normalize_photo_urls and extract_storage_filename."
        ),
        model_answer=(
            "Photos are stored in a Supabase Storage bucket; the projects/site_visits rows "
            "only persist the bucket key (e.g. 'visits/abc123.jpg'), not a public URL. "
            "normalize_photo_urls(rows) is called by the read endpoints in "
            "backend/main.py — it iterates each row, takes the stored key, and calls the "
            "Supabase Storage client to mint a signed URL with a short expiry, then "
            "rewrites the row's photo_url field to that signed URL before sending it down "
            "to the frontend. This keeps the bucket private at rest. "
            "extract_storage_filename(url) is the inverse: when the user deletes a photo, "
            "the frontend sends back the signed URL it received, and the backend has to "
            "recover the bucket key to call Storage.remove(). extract_storage_filename "
            "parses the URL, strips the bucket prefix and the signed-URL query string, and "
            "returns the raw key. The pair lets the wire format stay user-friendly (URLs) "
            "while keeping authoritative state as bucket keys."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=["backend/main.py"],
        category="implementation",
        difficulty="hard",
    ),
    GoldenEntry(
        question_text=(
            "What does send_daily_report in backend/main.py do, when does it run, and what "
            "would break if it failed silently?"
        ),
        model_answer=(
            "send_daily_report is a scheduled background job in backend/main.py. On its "
            "cron tick it queries the site_visits table for rows created since the previous "
            "run, formats a per-project summary (visit count, hours logged, photos "
            "uploaded), and dispatches an email to the project owner via SendGrid. It does "
            "not block any user-facing request — it runs out-of-band. If it failed "
            "silently, the API would keep accepting site_visits writes and the dashboard "
            "would keep rendering correctly, so users wouldn't notice anything wrong from "
            "the UI. The damage is downstream: project owners stop receiving the daily "
            "digest they rely on to know whether their crews showed up. Because the failure "
            "is invisible, the right mitigation is monitoring — log every successful send "
            "with a row count, alert if no successful run completes in 24h, and surface a "
            "'last digest sent' timestamp on the admin page (Header's isAdmin gate) so a "
            "human can spot drift."
        ),
        expected_score_min=7,
        expected_score_max=10,
        relevant_files=["backend/main.py"],
        category="failure_mode",
        difficulty="hard",
    ),
]


@dataclass
class PerEntryResult:
    question_text: str
    category: str
    difficulty: str
    expected_score_min: int
    expected_score_max: int
    accuracy: int
    completeness: int
    depth: int
    overall: int
    semantic_similarity: float
    latency_seconds: float
    passed: bool
    error: str | None = None


@dataclass
class EvalReport:
    total_entries: int
    passed: int
    failed: int
    pass_rate: float
    avg_accuracy: float
    avg_completeness: float
    avg_depth: float
    avg_overall: float
    avg_semantic_similarity: float
    avg_latency_seconds: float
    per_entry_results: list[dict] = field(default_factory=list)


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _build_report(results: list[PerEntryResult]) -> EvalReport:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    return EvalReport(
        total_entries=total,
        passed=passed,
        failed=failed,
        pass_rate=round(passed / total, 3) if total else 0.0,
        avg_accuracy=_avg([r.accuracy for r in results]),
        avg_completeness=_avg([r.completeness for r in results]),
        avg_depth=_avg([r.depth for r in results]),
        avg_overall=_avg([r.overall for r in results]),
        avg_semantic_similarity=_avg([r.semantic_similarity for r in results]),
        avg_latency_seconds=_avg([r.latency_seconds for r in results]),
        per_entry_results=[asdict(r) for r in results],
    )


async def run_eval(analysis_id: str = GOLDEN_ANALYSIS_ID) -> EvalReport:
    """Run every GoldenEntry through the InterviewEvaluator and return a report.

    Uses live data from the stored analysis for repo_id, model_answer, and
    relevant_files (matched by question_text). Falls back to entry data when
    the question is not in the live analysis. Grounding file_explanations are
    sourced from SITETRACKER_FILE_EXPLANATIONS in this module — the stored
    analysis's file_explanations dict is empty.
    """
    analysis = await db.get_analysis(analysis_id)
    if not analysis:
        raise RuntimeError(
            f"Analysis {analysis_id} not found — cannot run eval against a missing repo."
        )
    repo_id = analysis["repo_id"]
    by_question = {
        q.get("question", ""): q for q in (analysis.get("interview_questions") or [])
    }

    results: list[PerEntryResult] = []
    for entry in GOLDEN_ENTRIES:
        live = by_question.get(entry.question_text, {})
        evaluator_model_answer = live.get("model_answer") or entry.model_answer
        evaluator_relevant = live.get("relevant_files") or entry.relevant_files

        t0 = time.perf_counter()
        try:
            payload = await evaluate_answer(
                repo_id=repo_id,
                question=entry.question_text,
                user_answer=entry.model_answer,
                model_answer=evaluator_model_answer,
                file_explanations=SITETRACKER_FILE_EXPLANATIONS,
                relevant_files=evaluator_relevant,
            )
            latency = time.perf_counter() - t0
            res = payload["result"]
            scores = res["scores"]
            overall = scores["overall"]
            results.append(
                PerEntryResult(
                    question_text=entry.question_text,
                    category=entry.category,
                    difficulty=entry.difficulty,
                    expected_score_min=entry.expected_score_min,
                    expected_score_max=entry.expected_score_max,
                    accuracy=scores["accuracy"],
                    completeness=scores["completeness"],
                    depth=scores["depth"],
                    overall=overall,
                    # Evaluator now returns None when the embedding service was
                    # unreachable; the eval harness still wants a numeric value
                    # for averaging and printing, so coerce at the read site.
                    semantic_similarity=res.get("semantic_similarity") or 0.0,
                    latency_seconds=round(latency, 3),
                    passed=entry.expected_score_min <= overall <= entry.expected_score_max,
                )
            )
        except Exception as exc:
            latency = time.perf_counter() - t0
            logger.exception("[eval] entry failed: %s", entry.question_text[:80])
            results.append(
                PerEntryResult(
                    question_text=entry.question_text,
                    category=entry.category,
                    difficulty=entry.difficulty,
                    expected_score_min=entry.expected_score_min,
                    expected_score_max=entry.expected_score_max,
                    accuracy=0,
                    completeness=0,
                    depth=0,
                    overall=0,
                    semantic_similarity=0.0,
                    latency_seconds=round(latency, 3),
                    passed=False,
                    error=str(exc),
                )
            )

    return _build_report(results)


def _format_report(report: EvalReport) -> str:
    lines = [
        "=" * 70,
        "GitMentor Eval Harness — Report",
        "=" * 70,
        f"Total entries        : {report.total_entries}",
        f"Passed               : {report.passed}",
        f"Failed               : {report.failed}",
        f"Pass rate            : {report.pass_rate * 100:.1f}%",
        f"Avg accuracy         : {report.avg_accuracy}",
        f"Avg completeness     : {report.avg_completeness}",
        f"Avg depth            : {report.avg_depth}",
        f"Avg overall          : {report.avg_overall}",
        f"Avg semantic_sim     : {report.avg_semantic_similarity}",
        f"Avg latency (s)      : {report.avg_latency_seconds}",
        "-" * 70,
        "Per-entry:",
    ]
    for i, r in enumerate(report.per_entry_results, start=1):
        verdict = "PASS" if r["passed"] else "FAIL"
        lines.append(
            f"  {i:2d}. [{verdict}] overall={r['overall']:>2} "
            f"(expected {r['expected_score_min']}-{r['expected_score_max']}) "
            f"acc={r['accuracy']} comp={r['completeness']} depth={r['depth']} "
            f"sim={r['semantic_similarity']:.3f} latency={r['latency_seconds']:.2f}s"
        )
        lines.append(f"      Q: {r['question_text'][:100]}")
        if r.get("error"):
            lines.append(f"      ERROR: {r['error']}")
    lines.append("=" * 70)
    return "\n".join(lines)


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    report = await run_eval()
    print(_format_report(report))


if __name__ == "__main__":
    asyncio.run(_main())
