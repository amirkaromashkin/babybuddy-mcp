#!/usr/bin/env python3
"""
BabyBuddy MCP Server
- Directly uses BABYBUDDY_INSTANCE and BABYBUDDY_TOKEN environment variables.
- Simple and persistent: no login forms, no tokens, no 401s.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import Icon

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST       = os.environ.get("HOST", "localhost")
PORT       = int(os.environ.get("PORT", "8080"))
SERVER_URL = os.environ.get("SERVER_URL", f"http://{HOST}:{PORT}")

# Mandatory credentials
BABYBUDDY_INSTANCE = os.environ.get("BABYBUDDY_INSTANCE")
BABYBUDDY_TOKEN    = os.environ.get("BABYBUDDY_TOKEN")

if not BABYBUDDY_INSTANCE or not BABYBUDDY_TOKEN:
    import sys
    print("CRITICAL ERROR: BABYBUDDY_INSTANCE and BABYBUDDY_TOKEN must be set.")
    print("Please set them in your environment or .env file.")
    sys.exit(1)

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
# Helpers
# ---------------------------------------------------------------------------

def _client() -> BabyBuddyClient:
    """Return a BabyBuddyClient using configured environment variables."""
    # Note: Validation happens at startup, so these are guaranteed to exist here.
    return BabyBuddyClient(BABYBUDDY_INSTANCE, BABYBUDDY_TOKEN)

def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "BabyBuddy",
    icons=[Icon(src=f"{SERVER_URL}/icon.png", media_type="image/png")],
    host=HOST,
    port=PORT,
)

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


@mcp.tool()
async def delete_feeding(feeding_id: int) -> str:
    """Delete a feeding session by ID."""
    await _client().delete(f"/feedings/{feeding_id}/")
    return _fmt({"deleted": True, "feeding_id": feeding_id})

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


@mcp.tool()
async def delete_sleep(sleep_id: int) -> str:
    """Delete a sleep session by ID."""
    await _client().delete(f"/sleep/{sleep_id}/")
    return _fmt({"deleted": True, "sleep_id": sleep_id})

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


@mcp.tool()
async def delete_diaper_change(change_id: int) -> str:
    """Delete a diaper change by ID."""
    await _client().delete(f"/changes/{change_id}/")
    return _fmt({"deleted": True, "change_id": change_id})

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


@mcp.tool()
async def delete_temperature(temperature_id: int) -> str:
    """Delete a temperature reading by ID."""
    await _client().delete(f"/temperature/{temperature_id}/")
    return _fmt({"deleted": True, "temperature_id": temperature_id})

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


@mcp.tool()
async def delete_weight(weight_id: int) -> str:
    """Delete a weight measurement by ID."""
    await _client().delete(f"/weight/{weight_id}/")
    return _fmt({"deleted": True, "weight_id": weight_id})

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


@mcp.tool()
async def delete_height(height_id: int) -> str:
    """Delete a height measurement by ID."""
    await _client().delete(f"/height/{height_id}/")
    return _fmt({"deleted": True, "height_id": height_id})

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


@mcp.tool()
async def delete_head_circumference(head_circumference_id: int) -> str:
    """Delete a head circumference measurement by ID."""
    await _client().delete(f"/head-circumference/{head_circumference_id}/")
    return _fmt({"deleted": True, "head_circumference_id": head_circumference_id})

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


@mcp.tool()
async def delete_pumping(pumping_id: int) -> str:
    """Delete a pumping session by ID."""
    await _client().delete(f"/pumping/{pumping_id}/")
    return _fmt({"deleted": True, "pumping_id": pumping_id})

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


@mcp.tool()
async def delete_note(note_id: int) -> str:
    """Delete a note by ID."""
    await _client().delete(f"/notes/{note_id}/")
    return _fmt({"deleted": True, "note_id": note_id})

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
    print(f"🍼 BabyBuddy MCP starting — binding {HOST}:{PORT}")
    print(f"    Direct API authentication active.")
    uvicorn.run(mcp.streamable_http_app(), host=HOST, port=PORT)
