"""ArkenLabs MCP server (v1) — read-only access to the public ArkenLabs data layer.

Exposes PRISM rankings + the native signal boards + the independent satellite feeds as MCP
tools for Claude / ChatGPT / Cursor. It only reads PUBLIC JSON (the same feeds the website
consumes), so it is fully decoupled and safe: no keys, no writes, no trading.

Run:
    pip install -r requirements.txt
    python server.py            # stdio transport (for desktop MCP clients)

Config via env (optional):
    ARKEN_SITE_BASE   default https://arkenlabs.eu
    ARKEN_GH_BASE     default https://HunHospak.github.io
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import requests
from mcp.server.fastmcp import FastMCP

SITE_BASE = os.environ.get("ARKEN_SITE_BASE", "https://arkenlabs.eu").rstrip("/")
GH_BASE = os.environ.get("ARKEN_GH_BASE", "https://HunHospak.github.io").rstrip("/")

# Native PRISM signal boards (served from the site).
BOARDS = ["buybacks", "smart_money", "capital_flow", "policy", "fundamentals", "risk_flags"]
BOARD_URL = SITE_BASE + "/public_exports/market/signal_boards/{board}.json"
RANKINGS_URL = SITE_BASE + "/public_exports/rankings/top_companies.json"

# Independent satellite services (served from GitHub Pages).
SATELLITES = [
    "big_movers", "sector_rotation", "spy_barometer", "auto_ta", "social_sentiment",
    "squeeze_radar", "congress_trades", "insider_flow", "fda_calendar", "macro_snapshot",
]
SAT_URL = GH_BASE + "/{svc}/{svc}.json"

mcp = FastMCP("ArkenLabs")


def _fetch(url: str) -> Dict[str, Any]:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "arken-mcp/1.0"})
    except Exception as exc:  # noqa: BLE001
        return {"error": f"fetch_failed: {exc!r}", "url": url}
    if r.status_code != 200:
        return {"error": f"http_{r.status_code}", "url": url}
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"error": "malformed_json", "url": url}


@mcp.tool()
def list_signals() -> Dict[str, Any]:
    """List every dataset this server can return: PRISM boards and independent satellite feeds."""
    return {
        "prism_rankings": "get_rankings(limit)",
        "signal_boards": BOARDS,
        "satellite_feeds": SATELLITES,
        "per_company": "get_company_signals(ticker)",
        "note": "All data is read-only, public, and informational only — not investment advice.",
    }


@mcp.tool()
def get_rankings(limit: int = 20) -> Dict[str, Any]:
    """Top companies by PRISM score. `limit` caps how many rows are returned (default 20)."""
    data = _fetch(RANKINGS_URL)
    if "error" in data:
        return data
    rows = data.get("companies") or data.get("rows") or data.get("data") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    return {"count": min(len(rows), limit), "companies": rows[: max(1, int(limit))]}


@mcp.tool()
def get_board(board: str) -> Dict[str, Any]:
    """Return one native PRISM signal board. Valid ids: buybacks, smart_money, capital_flow, policy, fundamentals, risk_flags."""
    if board not in BOARDS:
        return {"error": "unknown_board", "valid": BOARDS}
    return _fetch(BOARD_URL.format(board=board))


@mcp.tool()
def get_feed(service: str) -> Dict[str, Any]:
    """Return one independent satellite feed (e.g. squeeze_radar, congress_trades, insider_flow, macro_snapshot, fda_calendar)."""
    if service not in SATELLITES:
        return {"error": "unknown_service", "valid": SATELLITES}
    return _fetch(SAT_URL.format(svc=service))


@mcp.tool()
def get_company_signals(ticker: str) -> Dict[str, Any]:
    """Aggregate every by_ticker signal for one ticker across all boards and satellite feeds."""
    tk = str(ticker or "").upper().strip()
    if not tk:
        return {"error": "empty_ticker"}
    out: Dict[str, Any] = {"ticker": tk, "signals": {}}
    for board in BOARDS:
        d = _fetch(BOARD_URL.format(board=board))
        entry = ((d.get("data") or {}).get("by_ticker") or {}).get(tk) if isinstance(d, dict) else None
        if entry:
            out["signals"][board] = entry
    for svc in SATELLITES:
        d = _fetch(SAT_URL.format(svc=svc))
        entry = ((d.get("data") or {}).get("by_ticker") or {}).get(tk) if isinstance(d, dict) else None
        if entry:
            out["signals"][svc] = entry
    out["found"] = len(out["signals"])
    return out


if __name__ == "__main__":
    mcp.run()
