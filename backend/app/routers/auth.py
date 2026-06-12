import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
# public_repo is read/write on PUBLIC repos only, which is enough for cloning and reading
# public repositories. Supporting private repos would require the full `repo` scope and
# should be a deliberate, user-visible opt-in (e.g., a "Connect private repos" upgrade flow)
# rather than something we silently ask for at first sign-in.
_SCOPES = "read:user public_repo"

# In-memory CSRF state store: {state_token: issued_at_unix_seconds}.
# Entries are one-time-use and expire after _STATE_TTL_SECONDS. This is fine for a
# single-process dev server; multi-worker deploys should swap to Redis or a DB row.
_state_store: dict[str, float] = {}
_STATE_TTL_SECONDS = 600  # 10 minutes


def _purge_expired_states() -> None:
    """Drop any states older than the TTL. Called on every state read/write."""
    cutoff = time.time() - _STATE_TTL_SECONDS
    stale = [s for s, ts in _state_store.items() if ts < cutoff]
    for s in stale:
        _state_store.pop(s, None)


@router.get("/github")
async def github_login():
    """Kick off the GitHub OAuth dance. Redirects the user to GitHub's authorize page.

    GitHub will redirect back to /auth/callback with ?code=...&state=... once the user approves.
    """
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID not configured")

    _purge_expired_states()
    state = secrets.token_urlsafe(32)
    _state_store[state] = time.time()

    params = {
        "client_id": settings.github_client_id,
        "scope": _SCOPES,
        "allow_signup": "false",
        "state": state,
    }
    url = f"{_GITHUB_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/callback")
async def github_callback(code: str = Query(...), state: str = Query(...)):
    """GitHub redirects here after the user authorizes. Verify the state (CSRF), exchange
    code → access_token, then redirect the browser to the frontend with the token in the
    URL fragment (#token=...) so it is not sent in Referer headers or logged by proxies."""
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    _purge_expired_states()
    if state not in _state_store:
        logger.warning("[Auth] CSRF state missing or expired")
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    # One-time use: drop the state before any external call.
    _state_store.pop(state, None)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )

    try:
        payload = resp.json()
    except ValueError:
        payload = {}

    if resp.status_code != 200:
        logger.error(
            "[Auth] GitHub token exchange failed: status=%s error=%s",
            resp.status_code,
            payload.get("error", "unknown"),
        )
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    access_token = payload.get("access_token")
    if not access_token:
        logger.error(
            "[Auth] No access_token in response: error=%s description=%s",
            payload.get("error"),
            payload.get("error_description"),
        )
        raise HTTPException(
            status_code=502,
            detail=f"GitHub did not return a token: {payload.get('error_description', 'unknown error')}",
        )

    # Token is delivered to the frontend in the URL FRAGMENT (after `#`).
    # Fragments are never sent to servers, never appear in Referer headers, and never
    # land in proxy/access logs. The frontend AuthCallback page reads the fragment,
    # stores the token, and immediately clears the fragment from the address bar.
    redirect_url = f"{settings.frontend_url.rstrip('/')}/auth/callback#token={access_token}"
    return RedirectResponse(redirect_url)
