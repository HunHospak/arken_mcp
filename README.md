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
- `get_feed(service)` — a satellite feed: `squeeze_radar`, `congress_trades`, `insider_flow`, `macro_snapshot`, `fda_calendar`, `big_movers`, `sector_rotation`, `spy_barometer`, `auto_ta`, `social_sentiment`
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

## Not investment advice

All data is informational and read-only.
