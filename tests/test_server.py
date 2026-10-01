"""Offline transport/contract tests; no real network or MCP client required."""

import datetime as dt
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


# Use a tiny decorator harness to inspect the functions independently of the SDK.
class StubMCP:
    def __init__(self, name):
        self.name = name

    def tool(self):
        return lambda function: function


modules = {name: types.ModuleType(name) for name in ["mcp", "mcp.server", "mcp.server.fastmcp"]}
modules["mcp.server.fastmcp"].FastMCP = StubMCP
spec = importlib.util.spec_from_file_location("arken_server_test", Path(__file__).resolve().parents[1] / "server.py")
server = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, modules):
    spec.loader.exec_module(server)


def feed(service="index_ticker", status="active"):
    return {
        "service": service,
        "schema_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "ttl_hours": 30,
        "data": {"by_ticker": {"AAA": {"signal": 1}}},
    }


class ServerTests(unittest.TestCase):
    def test_v2_rankings_and_count(self):
        with patch.object(
            server,
            "_fetch",
            return_value={
                "schema_version": "2.0",
                "status": "active",
                "snapshot_date": "2026-10-01",
                "data": {"companies": [{"ticker": "AAA"}]},
            },
        ) as get:
            result = server.get_rankings(20)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["companies"][0]["ticker"], "AAA")
        self.assertIn("v2/snapshots/daily", get.call_args.args[0])

    def test_legacy_fallback_only_on_missing_endpoint(self):
        with patch.object(server, "_fetch", side_effect=[{"error": "http_404"}, {"companies": []}]) as get:
            self.assertEqual(server.get_rankings()["count"], 0)
            self.assertEqual(get.call_count, 2)
        with patch.object(server, "_fetch", return_value={"error": "http_500"}) as get:
            self.assertEqual(server.get_rankings()["error"], "http_500")
            self.assertEqual(get.call_count, 1)

    def test_bad_limits_and_payloads(self):
        for value in [-1, 0, True, "20", 1001]:
            self.assertEqual(server.get_rankings(value)["error"], "invalid_limit")
        for data in [{"data": []}, {"companies": ["bad"]}]:
            with patch.object(server, "_fetch", return_value=data):
                self.assertEqual(server.get_rankings()["error"], "malformed_rankings")

    def test_fetch_rejects_nonobject_and_redacts_transport_errors(self):
        response = types.SimpleNamespace(status_code=200, json=lambda: [])
        with patch.object(server.requests, "get", return_value=response):
            self.assertEqual(server._fetch("https://example.com/feed")["error"], "malformed_json")
        with patch.object(server.requests, "get", side_effect=server.requests.ConnectionError("secret-value")):
            result = server._fetch("https://user:secret-value@example.com/feed?key=secret-value")
        self.assertNotIn("secret-value", str(result))

    def test_fresh_partial_and_stale_feed(self):
        self.assertNotIn("error", server._usable_feed(feed(), "index_ticker"))
        self.assertNotIn("error", server._usable_feed(feed(status="partial")))
        stale = {**feed(), "generated_at": "2001-01-01T00:00:00Z"}
        self.assertEqual(server._usable_feed(stale)["error"], "stale_feed")
        self.assertEqual(server._usable_feed(feed(status="unavailable"))["error"], "service_unavailable")

    def test_malformed_and_future_feed(self):
        for key, value in [
            ("status", "other"),
            ("ttl_hours", 0),
            ("ttl_hours", True),
            ("ttl_hours", float("nan")),
            ("data", []),
            ("generated_at", "bad"),
            ("generated_at", "1970-01-01T00:00:00Z"),
            ("generated_at", "2999-01-01T00:00:00Z"),
        ]:
            self.assertEqual(server._usable_feed({**feed(), key: value})["error"], "malformed_feed")
        self.assertEqual(server._usable_feed(feed(), "different")["error"], "malformed_feed")

    def test_company_missing_sources_are_visible_and_not_signals(self):
        with (
            patch.object(server, "get_board", return_value={"error": "stale_feed"}),
            patch.object(server, "get_feed", return_value={"error": "service_unavailable"}),
        ):
            result = server.get_company_signals("aaa")
        self.assertEqual(result["found"], 0)
        self.assertEqual(len(result["source_errors"]), len(server.BOARDS) + len(server.SATELLITES))
        self.assertIn("index_ticker", server.SATELLITES)


if __name__ == "__main__":
    unittest.main()
