#!/usr/bin/env python3
"""
BabyBuddy MCP Server
- HTTP transport (Streamable-HTTP), runs on http://localhost:8080/mcp
- OAuth 2.1 — users log in via a browser form once; no config files needed
- General-purpose: works with any BabyBuddy instance, any number of children
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
    OAuthToken,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP
from mcp.types import Icon
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, RedirectResponse, Response

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST       = os.environ.get("HOST", "localhost")
PORT       = int(os.environ.get("PORT", "8080"))
SERVER_URL = os.environ.get("SERVER_URL", f"http://{HOST}:{PORT}")
TOKEN_TTL  = int(os.environ.get("TOKEN_TTL", str(24 * 3600)))  # 24 h

# ---------------------------------------------------------------------------
# In-memory stores  (swap for a DB in production multi-user deployments)
# ---------------------------------------------------------------------------

_auth_codes:    dict[str, tuple[AuthorizationCode, dict]] = {}
_access_tokens: dict[str, tuple[AccessToken, dict]]       = {}
_refresh_tokens: dict[str, tuple[RefreshToken, dict]]     = {}
_pending_auth:  dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}
_clients:       dict[str, OAuthClientInformationFull]     = {}

# ---------------------------------------------------------------------------
# BabyBuddy API client
# ---------------------------------------------------------------------------

class BabyBuddyClient:
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self.base_url}/api{path}", headers=self._headers,
                            params=params or {}, timeout=15)
            r.raise_for_status()
            return r.json()

    async def post(self, path: str, data: dict) -> dict:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{self.base_url}/api{path}", headers=self._headers,
                             json=data, timeout=15)
            r.raise_for_status()
            return r.json()

    async def delete(self, path: str) -> None:
        async with httpx.AsyncClient() as c:
            r = await c.delete(f"{self.base_url}/api{path}", headers=self._headers, timeout=15)
            r.raise_for_status()

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session(token: str) -> dict | None:
    entry = _access_tokens.get(token)
    if not entry:
        return None
    at, session = entry
    if at.expires_at and at.expires_at < time.time():
        del _access_tokens[token]
        return None
    return session


def _client() -> BabyBuddyClient:
    """Return a BabyBuddyClient for the currently authenticated request."""
    at = get_access_token()
    if at is None:
        raise RuntimeError("Not authenticated — complete OAuth login first.")
    sess = _session(at.token)
    if sess is None:
        raise RuntimeError("Session expired — please re-authenticate.")
    return BabyBuddyClient(sess["base_url"], sess["api_token"])

# ---------------------------------------------------------------------------
# OAuth 2.1 Provider
# ---------------------------------------------------------------------------

LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>BabyBuddy MCP — Sign In</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
          background:#f0f4f8;display:flex;align-items:center;
          justify-content:center;min-height:100vh;padding:20px}}
    .card{{background:#fff;border-radius:16px;padding:40px;
           box-shadow:0 4px 24px rgba(0,0,0,.1);max-width:440px;width:100%}}
    .logo{{text-align:center;margin-bottom:8px}}
    .logo img{{width:80px;height:80px;border-radius:20%}}
    h1{{text-align:center;font-size:22px;color:#1a202c;margin-bottom:4px}}
    p.sub{{text-align:center;color:#718096;font-size:14px;margin-bottom:28px}}
    label{{display:block;font-size:13px;font-weight:600;color:#4a5568;margin-bottom:6px}}
    input{{width:100%;padding:10px 14px;border:1.5px solid #e2e8f0;
           border-radius:8px;font-size:15px;transition:border .2s}}
    input:focus{{outline:none;border-color:#667eea}}
    .hint{{font-size:12px;color:#a0aec0;margin-top:4px}}
    .field{{margin-bottom:18px}}
    button{{width:100%;padding:12px;background:#667eea;color:#fff;
            border:none;border-radius:8px;font-size:16px;font-weight:600;
            cursor:pointer;transition:background .2s;margin-top:6px}}
    button:hover{{background:#5a67d8}}
    .error{{background:#fff5f5;border:1px solid #fc8181;border-radius:8px;
            padding:10px 14px;color:#c53030;font-size:13px;
            margin-bottom:16px;display:{error_display}}}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo"><img src="/icon.png" alt="BabyBuddy MCP Icon"></div>
    <h1>BabyBuddy MCP</h1>
    <p class="sub">Connect your BabyBuddy instance to your AI assistant</p>
    <div class="error">{error_msg}</div>
    <form method="POST" action="/oauth/login">
      <input type="hidden" name="state" value="{state}">
      <div class="field">
        <label>BabyBuddy URL</label>
        <input name="base_url" type="url"
               placeholder="https://your-babybuddy.example.com"
               value="{base_url}" required>
        <div class="hint">The URL of your self-hosted BabyBuddy instance</div>
      </div>
      <div class="field">
        <label>API Token</label>
        <input name="api_token" type="password"
               placeholder="Paste your API token" required>
        <div class="hint">BabyBuddy → Settings → API → your token</div>
      </div>
      <button type="submit">Connect →</button>
    </form>
  </div>
</body>
</html>"""


class BabyBuddyOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return _clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        _clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        state = secrets.token_urlsafe(16)
        _pending_auth[state] = (client, params)
        return f"{SERVER_URL}/oauth/login?state={state}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        entry = _auth_codes.get(authorization_code)
        if not entry:
            return None
        code, _ = entry
        if code.expires_at < time.time():
            del _auth_codes[authorization_code]
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        entry = _auth_codes.pop(authorization_code.code, None)
        if not entry:
            raise TokenError("invalid_grant")
        _, session = entry

        access  = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        exp     = int(time.time()) + TOKEN_TTL

        _access_tokens[access] = (
            AccessToken(token=access, client_id=client.client_id,
                        scopes=authorization_code.scopes, expires_at=exp),
            session,
        )
        _refresh_tokens[refresh] = (
            RefreshToken(token=refresh, client_id=client.client_id,
                         scopes=authorization_code.scopes, expires_at=exp + TOKEN_TTL),
            session,
        )
        return OAuthToken(access_token=access, token_type="Bearer",
                          expires_in=TOKEN_TTL, refresh_token=refresh,
                          scope=" ".join(authorization_code.scopes))

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        entry = _refresh_tokens.get(refresh_token)
        if not entry:
            return None
        rt, _ = entry
        if rt.expires_at and rt.expires_at < time.time():
            del _refresh_tokens[refresh_token]
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        old = _refresh_tokens.pop(refresh_token.token, None)
        if not old:
            raise TokenError("invalid_grant")
        _, session = old
        use_scopes = scopes or refresh_token.scopes

        access  = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        exp     = int(time.time()) + TOKEN_TTL

        _access_tokens[access] = (
            AccessToken(token=access, client_id=client.client_id,
                        scopes=use_scopes, expires_at=exp),
            session,
        )
        _refresh_tokens[refresh] = (
            RefreshToken(token=refresh, client_id=client.client_id,
                         scopes=use_scopes, expires_at=exp + TOKEN_TTL),
            session,
        )
        return OAuthToken(access_token=access, token_type="Bearer",
                          expires_in=TOKEN_TTL, refresh_token=refresh,
                          scope=" ".join(use_scopes))

    async def load_access_token(self, token: str) -> AccessToken | None:
        entry = _access_tokens.get(token)
        if not entry:
            return None
        at, _ = entry
        if at.expires_at and at.expires_at < time.time():
            del _access_tokens[token]
            return None
        return at

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
        _access_tokens.pop(token, None)
        _refresh_tokens.pop(token, None)

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

_oauth_provider = BabyBuddyOAuthProvider()

# Ensure metadata URLs are HTTPS (FastMCP / OAuth 2.1 requirement)
_mcp_url = SERVER_URL
if _mcp_url.startswith("http://"):
    _mcp_url = _mcp_url.replace("http://", "https://", 1)

mcp = FastMCP(
    "BabyBuddy",
    auth_server_provider=_oauth_provider,
    icons=[Icon(src=f"{_mcp_url}/icon.png", media_type="image/png")],
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(_mcp_url),
        resource_server_url=AnyHttpUrl(_mcp_url),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["babybuddy"],
            default_scopes=["babybuddy"],
        ),
    ),
    host=HOST,
    port=PORT,
)

# ---------------------------------------------------------------------------
# Login form — custom routes added to the Starlette app
# ---------------------------------------------------------------------------

@mcp.custom_route("/icon.png", methods=["GET"])
async def get_icon(request: Request) -> Response:
    return FileResponse("icon.png")

@mcp.custom_route("/oauth/login", methods=["GET"])
async def login_form(request: Request) -> Response:
    state = request.query_params.get("state", "")
    # Allow a preview mode for the user to check the UI/Icon 
    if state == "preview":
        return HTMLResponse(LOGIN_HTML.format(state="preview", base_url="",
                                              error_display="none", error_msg=""))

    if state not in _pending_auth:
        return HTMLResponse("<h1>Invalid or expired state. Please restart the connection.</h1>", status_code=400)
    return HTMLResponse(LOGIN_HTML.format(state=state, base_url="",
                                          error_display="none", error_msg=""))


@mcp.custom_route("/oauth/login", methods=["POST"])
async def login_submit(request: Request) -> Response:
    form  = await request.form()
    state     = str(form.get("state", ""))
    base_url  = str(form.get("base_url", "")).rstrip("/")
    api_token = str(form.get("api_token", ""))

    if state not in _pending_auth:
        return HTMLResponse("<h1>Invalid or expired state.</h1>", status_code=400)

    # Validate the token against BabyBuddy
    try:
        async with httpx.AsyncClient() as hc:
            r = await hc.get(
                f"{base_url}/api/children/",
                headers={"Authorization": f"Token {api_token}", "Accept": "application/json"},
                timeout=10,
            )
            r.raise_for_status()
    except Exception as exc:
        return HTMLResponse(
            LOGIN_HTML.format(state=state, base_url=base_url,
                              error_display="block",
                              error_msg=f"Could not connect: {exc}"),
            status_code=200,
        )

    client, auth_params = _pending_auth.pop(state)
    session = {"base_url": base_url, "api_token": api_token}

    code = secrets.token_urlsafe(32)
    _auth_codes[code] = (
        AuthorizationCode(
            code=code,
            scopes=auth_params.scopes or ["babybuddy"],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=auth_params.code_challenge,
            redirect_uri=auth_params.redirect_uri,
            redirect_uri_provided_explicitly=auth_params.redirect_uri_provided_explicitly,
        ),
        session,
    )

    redirect_url = construct_redirect_uri(
        str(auth_params.redirect_uri), code=code, state=auth_params.state
    )
    return RedirectResponse(redirect_url, status_code=302)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Tools — Children
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_children() -> str:
    """List all children registered in BabyBuddy. Always call this first to get child IDs."""
    return _fmt(await _client().get("/children/"))

# ---------------------------------------------------------------------------
# Tools — Feedings
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_feeding(
    child: int,
    start: str,
    end: str,
    type: str,
    method: str,
    amount: float | None = None,
    notes: str | None = None,
) -> str:
    """
    Log a feeding session.

    type:   'breast milk' | 'formula' | 'fortified breast milk' | 'solid food'
    method: 'both breasts' | 'left breast' | 'right breast' | 'bottle' | 'parent fed' | 'self fed'
    start/end: ISO 8601 datetime strings.
    amount: ml (optional).
    child: child ID — use list_children() first.
    """
    payload: dict = {"child": child, "start": start, "end": end,
                     "type": type, "method": method}
    if amount is not None: payload["amount"] = amount
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/feedings/", payload))


@mcp.tool()
async def get_feedings(child: int, limit: int = 10) -> str:
    """Get recent feeding sessions for a child."""
    return _fmt(await _client().get("/feedings/",
        {"child": child, "limit": limit, "ordering": "-start"}))

# ---------------------------------------------------------------------------
# Tools — Sleep
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_sleep(
    child: int,
    start: str,
    end: str,
    nap: bool = True,
    notes: str | None = None,
) -> str:
    """
    Log a sleep session.

    nap: True = daytime nap, False = nighttime sleep.
    start/end: ISO 8601 datetime strings.
    """
    payload: dict = {"child": child, "start": start, "end": end, "nap": nap}
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/sleep/", payload))


@mcp.tool()
async def get_sleep(child: int, limit: int = 10) -> str:
    """Get recent sleep sessions for a child."""
    return _fmt(await _client().get("/sleep/",
        {"child": child, "limit": limit, "ordering": "-start"}))

# ---------------------------------------------------------------------------
# Tools — Diaper Changes
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_diaper_change(
    child: int,
    wet: bool,
    solid: bool,
    time: str | None = None,
    color: str | None = None,
    amount: str | None = None,
    notes: str | None = None,
) -> str:
    """
    Log a diaper change.

    wet: True if wet. solid: True if poop.
    color: 'black' | 'brown' | 'green' | 'yellow' | 'orange' | 'red' | 'white' | 'other'
    amount: 'small' | 'medium' | 'large'
    time: ISO 8601 (defaults to now).
    """
    payload: dict = {"child": child, "time": time or _now(), "wet": wet, "solid": solid}
    if color: payload["color"] = color
    if amount: payload["amount"] = amount
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/changes/", payload))


@mcp.tool()
async def get_diaper_changes(child: int, limit: int = 10) -> str:
    """Get recent diaper changes for a child."""
    return _fmt(await _client().get("/changes/",
        {"child": child, "limit": limit, "ordering": "-time"}))

# ---------------------------------------------------------------------------
# Tools — Temperature
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_temperature(
    child: int,
    temperature: float,
    time: str | None = None,
    notes: str | None = None,
) -> str:
    """Log a temperature reading in °C."""
    payload: dict = {"child": child, "temperature": temperature, "time": time or _now()}
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/temperature/", payload))


@mcp.tool()
async def get_temperature(child: int, limit: int = 10) -> str:
    """Get recent temperature readings for a child."""
    return _fmt(await _client().get("/temperature/",
        {"child": child, "limit": limit, "ordering": "-time"}))

# ---------------------------------------------------------------------------
# Tools — Weight
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_weight(
    child: int,
    weight: float,
    date: str | None = None,
    notes: str | None = None,
) -> str:
    """Log a weight measurement in kg."""
    payload: dict = {"child": child, "weight": weight, "date": date or _today()}
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/weight/", payload))


@mcp.tool()
async def get_weight(child: int, limit: int = 10) -> str:
    """Get weight history for a child."""
    return _fmt(await _client().get("/weight/",
        {"child": child, "limit": limit, "ordering": "-date"}))

# ---------------------------------------------------------------------------
# Tools — Height
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_height(
    child: int,
    height: float,
    date: str | None = None,
    notes: str | None = None,
) -> str:
    """Log a height measurement in cm."""
    payload: dict = {"child": child, "height": height, "date": date or _today()}
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/height/", payload))


@mcp.tool()
async def get_height(child: int, limit: int = 10) -> str:
    """Get height history for a child."""
    return _fmt(await _client().get("/height/",
        {"child": child, "limit": limit, "ordering": "-date"}))

# ---------------------------------------------------------------------------
# Tools — Head Circumference
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_head_circumference(
    child: int,
    head_circumference: float,
    date: str | None = None,
    notes: str | None = None,
) -> str:
    """Log a head circumference measurement in cm."""
    payload: dict = {"child": child, "head_circumference": head_circumference,
                     "date": date or _today()}
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/head-circumference/", payload))


@mcp.tool()
async def get_head_circumference(child: int, limit: int = 10) -> str:
    """Get head circumference history for a child."""
    return _fmt(await _client().get("/head-circumference/",
        {"child": child, "limit": limit, "ordering": "-date"}))

# ---------------------------------------------------------------------------
# Tools — Pumping
# ---------------------------------------------------------------------------

@mcp.tool()
async def log_pumping(
    child: int,
    amount: float,
    time: str | None = None,
    notes: str | None = None,
) -> str:
    """Log a pumping session. amount in ml."""
    payload: dict = {"child": child, "amount": amount, "time": time or _now()}
    if notes: payload["notes"] = notes
    return _fmt(await _client().post("/pumping/", payload))


@mcp.tool()
async def get_pumping(child: int, limit: int = 10) -> str:
    """Get recent pumping sessions for a child."""
    return _fmt(await _client().get("/pumping/",
        {"child": child, "limit": limit, "ordering": "-time"}))

# ---------------------------------------------------------------------------
# Tools — Notes
# ---------------------------------------------------------------------------

@mcp.tool()
async def add_note(child: int, note: str, time: str | None = None) -> str:
    """Add a free-text note for a child."""
    return _fmt(await _client().post("/notes/",
        {"child": child, "note": note, "time": time or _now()}))


@mcp.tool()
async def get_notes(child: int, limit: int = 10) -> str:
    """Get recent notes for a child."""
    return _fmt(await _client().get("/notes/",
        {"child": child, "limit": limit, "ordering": "-time"}))

# ---------------------------------------------------------------------------
# Tools — Timers
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_timers() -> str:
    """Get all active timers."""
    return _fmt(await _client().get("/timers/"))


@mcp.tool()
async def start_timer(child: int, name: str | None = None) -> str:
    """Start a new timer (e.g. to track an ongoing feeding or sleep)."""
    payload: dict = {"child": child}
    if name: payload["name"] = name
    return _fmt(await _client().post("/timers/", payload))


@mcp.tool()
async def stop_timer(timer_id: int) -> str:
    """Stop and delete an active timer by ID."""
    await _client().delete(f"/timers/{timer_id}/")
    return _fmt({"deleted": True, "timer_id": timer_id})

# ---------------------------------------------------------------------------
# Tools — Tags
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_tags() -> str:
    """List all tags available in BabyBuddy."""
    return _fmt(await _client().get("/tags/"))

# ---------------------------------------------------------------------------
# Tools — Daily Summary
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_daily_summary(child: int, date: str | None = None) -> str:
    """
    Get a full summary of all events for a child on a given date.
    date: YYYY-MM-DD (defaults to today).
    """
    c = _client()
    d = date or _today()
    feedings, sleep, changes, pumping, notes = await asyncio.gather(
        c.get("/feedings/", {"child": child, "start_after": f"{d}T00:00:00",
                             "start_before": f"{d}T23:59:59", "limit": 100}),
        c.get("/sleep/",    {"child": child, "start_after": f"{d}T00:00:00",
                             "start_before": f"{d}T23:59:59", "limit": 100}),
        c.get("/changes/",  {"child": child, "time_after":  f"{d}T00:00:00",
                             "time_before":  f"{d}T23:59:59", "limit": 100}),
        c.get("/pumping/",  {"child": child, "time_after":  f"{d}T00:00:00",
                             "time_before":  f"{d}T23:59:59", "limit": 100}),
        c.get("/notes/",    {"child": child, "time_after":  f"{d}T00:00:00",
                             "time_before":  f"{d}T23:59:59", "limit": 100}),
    )
    return _fmt({"date": d, "child_id": child, "feedings": feedings,
                 "sleep": sleep, "diaper_changes": changes,
                 "pumping": pumping, "notes": notes})

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print(f"🍼  BabyBuddy MCP starting — binding {HOST}:{PORT}")
    print(f"    MCP endpoint : {SERVER_URL}/mcp")
    print(f"    OAuth login  : {SERVER_URL}/oauth/login")
    uvicorn.run(mcp.streamable_http_app(), host=HOST, port=PORT)
