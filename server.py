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

import datetime as dt
import math
import os
import re
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

import requests
from mcp.server.fastmcp import FastMCP

SITE_BASE = os.environ.get("ARKEN_SITE_BASE", "https://arkenlabs.eu").rstrip("/")
GH_BASE = os.environ.get("ARKEN_GH_BASE", "https://HunHospak.github.io").rstrip("/")

# Native PRISM signal boards (served from the site).
BOARDS = ["buybacks", "smart_money", "capital_flow", "policy", "fundamentals", "risk_flags"]
BOARD_URL = SITE_BASE + "/public_exports/market/signal_boards/{board}.json"
RANKINGS_URL = SITE_BASE + "/public_exports/v2/snapshots/daily/rankings.json"
LEGACY_RANKINGS_URL = SITE_BASE + "/public_exports/rankings/top_companies.json"

# Independent satellite services (served from GitHub Pages).
SATELLITES = [
    "big_movers",
    "sector_rotation",
    "spy_barometer",
    "auto_ta",
    "social_sentiment",
    "squeeze_radar",
    "congress_trades",
    "insider_flow",
    "fda_calendar",
    "macro_snapshot",
    "index_ticker",
]
SAT_URL = GH_BASE + "/{svc}/{svc}.json"

mcp = FastMCP("ArkenLabs")


def _public_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _fetch(url: str) -> Dict[str, Any]:
    public_url = _public_url(url)
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "arken-mcp/1.0"})
    except requests.RequestException:
        return {"error": "fetch_failed", "url": public_url}
    if r.status_code != 200:
        return {"error": f"http_{r.status_code}", "url": public_url}
    try:
        data = r.json()
    except ValueError:
        return {"error": "malformed_json", "url": public_url}
    if not isinstance(data, dict):
        return {"error": "malformed_json", "url": public_url}
    return data


def _usable_feed(feed: Dict[str, Any], service: str | None = None) -> Dict[str, Any]:
    """Reject invalid/stale envelopes; this does not certify their signal economics."""
    if "error" in feed:
        return feed
    try:
        if not isinstance(feed.get("service"), str) or not re.fullmatch(r"[a-z][a-z0-9_]*", feed["service"]):
            raise ValueError("invalid_service")
        if not isinstance(feed.get("schema_version"), str) or not re.fullmatch(r"1\.\d+", feed["schema_version"]):
            raise ValueError("unsupported_schema")
        ttl = feed["ttl_hours"]
        stamp_text = feed["generated_at"]
        if not isinstance(stamp_text, str):
            raise ValueError("invalid_timestamp")
        stamp = dt.datetime.fromisoformat(stamp_text.replace("Z", "+00:00"))
        if (service and feed.get("service") != service) or feed.get("status") not in {
            "active",
            "partial",
            "unavailable",
        }:
            raise ValueError("invalid_identity_or_status")
        if (
            not isinstance(feed.get("data"), dict)
            or isinstance(ttl, bool)
            or not isinstance(ttl, (int, float))
            or not math.isfinite(ttl)
            or ttl <= 0
        ):
            raise ValueError("invalid_payload_or_ttl")
        if stamp.tzinfo is None or stamp.year < 2000:
            raise ValueError("invalid_timestamp")
        age = (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds()
        if age < -300:
            raise ValueError("future_timestamp")
    except (KeyError, TypeError, ValueError):
        return {"error": "malformed_feed"}
    if feed["status"] == "unavailable":
        return {"error": "service_unavailable", "notes": feed.get("notes")}
    if age > ttl * 3600:
        return {"error": "stale_feed", "generated_at": stamp_text}
    return feed


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
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        return {"error": "invalid_limit", "allowed_range": [1, 1000]}
    data = _fetch(RANKINGS_URL)
    source_url = RANKINGS_URL
    if data.get("error") == "http_404":
        data = _fetch(LEGACY_RANKINGS_URL)
        source_url = LEGACY_RANKINGS_URL
    if "error" in data:
        return data
    if data.get("status") == "unavailable":
        return {"error": "rankings_unavailable", "reason_code": data.get("reason_code")}
    payload = data.get("data", data)
    if not isinstance(payload, dict):
        return {"error": "malformed_rankings"}
    rows = payload.get("companies", payload.get("rows", []))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return {"error": "malformed_rankings"}
    selected = rows[:limit]
    return {
        "count": len(selected),
        "companies": selected,
        "source_url": _public_url(source_url),
        "snapshot_date": data.get("snapshot_date", payload.get("last_updated")),
        "snapshot_mode": data.get("snapshot_mode", payload.get("source_snapshot_mode")),
        "status": data.get("status", "legacy"),
        "warnings": data.get("warnings", []),
    }


@mcp.tool()
def get_board(board: str) -> Dict[str, Any]:
    """Return one native PRISM signal board. Valid ids: buybacks, smart_money, capital_flow, policy, fundamentals, risk_flags."""
    if board not in BOARDS:
        return {"error": "unknown_board", "valid": BOARDS}
    return _usable_feed(_fetch(BOARD_URL.format(board=board)))


@mcp.tool()
def get_feed(service: str) -> Dict[str, Any]:
    """Return one independent satellite feed (e.g. squeeze_radar, congress_trades, insider_flow, macro_snapshot, fda_calendar)."""
    if service not in SATELLITES:
        return {"error": "unknown_service", "valid": SATELLITES}
    return _usable_feed(_fetch(SAT_URL.format(svc=service)), service)


@mcp.tool()
def get_company_signals(ticker: str) -> Dict[str, Any]:
    """Aggregate every by_ticker signal for one ticker across all boards and satellite feeds."""
    tk = str(ticker or "").upper().strip()
    if not tk:
        return {"error": "empty_ticker"}
    out: Dict[str, Any] = {"ticker": tk, "signals": {}, "source_errors": {}, "source_statuses": {}}
    for board in BOARDS:
        d = get_board(board)
        if "error" in d:
            out["source_errors"][board] = d["error"]
        out["source_statuses"][board] = d.get("status", "unavailable")
        index = (d.get("data") or {}).get("by_ticker") or {}
        entry = index.get(tk) if isinstance(index, dict) else None
        if entry:
            out["signals"][board] = entry
    for svc in SATELLITES:
        d = get_feed(svc)
        if "error" in d:
            out["source_errors"][svc] = d["error"]
        out["source_statuses"][svc] = d.get("status", "unavailable")
        index = (d.get("data") or {}).get("by_ticker") or {}
        entry = index.get(tk) if isinstance(index, dict) else None
        if entry:
            out["signals"][svc] = entry
    out["found"] = len(out["signals"])
    return out


if __name__ == "__main__":
    mcp.run()
