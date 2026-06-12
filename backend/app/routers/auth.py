import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_SCOPES = "read:user repo"


@router.get("/github")
async def github_login():
    """Kick off the GitHub OAuth dance. Redirects the user to GitHub's authorize page.

    GitHub will redirect back to /auth/callback with ?code=... once the user approves.
    """
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID not configured")

    params = {
        "client_id": settings.github_client_id,
        "scope": _SCOPES,
        "allow_signup": "false",
    }
    url = f"{_GITHUB_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/callback")
async def github_callback(code: str = Query(...)):
    """GitHub redirects here after the user authorizes. Exchange code → access_token,
    then redirect the browser to the frontend with the token in the URL query string."""
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

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

    if resp.status_code != 200:
        logger.error("[Auth] GitHub token exchange failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    payload = resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        logger.error("[Auth] No access_token in response: %s", payload)
        raise HTTPException(status_code=502, detail=f"GitHub did not return a token: {payload.get('error_description', 'unknown error')}")

    # Bounce back to the frontend with the token. The frontend /auth/callback page
    # reads the token off the URL and stores it in localStorage.
    redirect_url = f"{settings.frontend_url.rstrip('/')}/auth/callback?token={access_token}"
    return RedirectResponse(redirect_url)
