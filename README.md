# ArkenLabs MCP server (v1)

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the
public ArkenLabs data layer — PRISM rankings, the native signal boards, and the independent
satellite feeds — as tools for Claude, ChatGPT, Cursor, or any MCP client.

It only reads **public JSON** (the same feeds the website consumes). No API keys, no writes,
no trading — informational only.

## Tools

- `list_signals()` — what's available
- `get_rankings(limit=20)` — top companies by PRISM score
- `get_board(board)` — a native board: `buybacks`, `smart_money`, `capital_flow`, `policy`, `fundamentals`, `risk_flags`
- `get_feed(service)` — a satellite feed: `squeeze_radar`, `congress_trades`, `insider_flow`, `macro_snapshot`, `fda_calendar`, `big_movers`, `sector_rotation`, `spy_barometer`, `auto_ta`, `social_sentiment`, `index_ticker`
- `get_company_signals(ticker)` — every `by_ticker` signal for one ticker, across all boards + feeds

## Run

```bash
pip install -r requirements.txt
python server.py
```

This starts the server over stdio (the transport desktop MCP clients use).

## Connect from Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arkenlabs": {
      "command": "python",
      "args": ["/absolute/path/to/finance/arken_mcp/server.py"]
    }
  }
}
```

Then ask, e.g., *"Use ArkenLabs to show the squeeze radar"* or *"What signals does ArkenLabs have for NVDA?"*

## Config (optional env)

- `ARKEN_SITE_BASE` — default `https://arkenlabs.eu` (boards + rankings)
- `ARKEN_GH_BASE` — default `https://HunHospak.github.io` (satellite feeds)

## Public contract and offline checks

Rankings load canonical V2 daily snapshots first and fall back to the legacy
alias only when the V2 endpoint is absent (HTTP 404). Results retain snapshot
provenance; limits must be integers 1–1000 and count reflects returned rows.
Native boards and satellite feeds reject malformed, unavailable, future-dated
and stale envelopes instead of serving them as current signals. Company tools
expose source errors/statuses; feeds without `by_ticker` are not inferred into
company signals. No scores or financial signals are reconstructed.

Run `python -m unittest discover -s tests`. Tests use mocked HTTP and an SDK
decorator harness: they verify read/contract behavior, not a complete live MCP
client/SDK transport certification. The read-only CI workflow runs these tests.
Transport diagnostics omit exception text and URL credentials/query strings.

Remaining limitation: company aggregation reads sources serially and has no
run-scoped cache. Provider economics and actual observation timestamps remain
owned by the upstream feeds; generation freshness is not PIT certification.

## Not investment advice

All data is informational and read-only.
