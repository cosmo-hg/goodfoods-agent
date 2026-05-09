"""
Tests for the agent loop: history compression and MCP tool dispatch.
These tests do not make real API calls.
"""

import json
import pytest

from agent.history import compress_history
from mcp.registry import get_mcp_client


# ---------------------------------------------------------------------------
# History compression tests
# ---------------------------------------------------------------------------

class TestCompressHistory:
    def _make_history(self, n):
        history = []
        for i in range(n):
            history.append({"role": "user", "content": f"User message {i}"})
            history.append({"role": "assistant", "content": f"Assistant reply {i}"})
        return history

    def test_short_history_unchanged(self):
        h = self._make_history(3)  # 6 messages
        result = compress_history(h)
        assert result == h

    def test_exactly_10_unchanged(self):
        h = self._make_history(5)  # 10 messages
        result = compress_history(h)
        assert result == h

    def test_11_messages_compressed(self):
        h = self._make_history(5) + [{"role": "user", "content": "extra"}]  # 11
        result = compress_history(h)
        assert len(result) < 11

    def test_compressed_retains_recent_messages(self):
        h = self._make_history(10)  # 20 messages
        result = compress_history(h)
        assert result[-1] == h[-1]
        assert result[-2] == h[-2]

    def test_compressed_starts_with_summary(self):
        h = self._make_history(10)
        result = compress_history(h)
        assert result[0]["role"] == "user"
        assert "SUMMARY" in result[0]["content"].upper() or "summary" in result[0]["content"].lower()

    def test_compressed_has_assistant_ack(self):
        h = self._make_history(10)
        result = compress_history(h)
        assert result[1]["role"] == "assistant"

    def test_empty_history_unchanged(self):
        assert compress_history([]) == []

    def test_tool_pair_boundary_safety(self):
        """Compression must never split a tool_call / tool_result pair."""
        # Build a history where the last 8 messages include a tool chain
        h = []
        for i in range(5):
            h.append({"role": "user",      "content": f"turn {i}"})
            h.append({"role": "assistant", "content": f"reply {i}"})
        # Append a tool exchange as messages 11-12
        tool_call_id = "call_abc"
        h.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": tool_call_id, "type": "function",
                            "function": {"name": "search_branches", "arguments": "{}"}}],
        })
        h.append({"role": "tool", "tool_call_id": tool_call_id, "content": "[]"})

        result = compress_history(h)
        # The verbatim tail must contain both the tool_call and its result together
        roles = [m.get("role") for m in result]
        if "tool" in roles:
            tool_idx = next(i for i, m in enumerate(result) if m.get("role") == "tool")
            # The message immediately before must be the paired assistant tool_call
            assert result[tool_idx - 1].get("role") == "assistant"
            assert result[tool_idx - 1].get("tool_calls") is not None


# ---------------------------------------------------------------------------
# MCP tool dispatch tests (replaces the old execute_tool shim tests)
# ---------------------------------------------------------------------------

class TestMCPDispatch:
    """
    Test that the MCP layer correctly routes calls and surfaces errors.
    All calls go through get_mcp_client().call_tool() — the same path the
    agent loop uses at runtime.
    """

    @pytest.fixture
    def db_path(self, tmp_path):
        from config import init_db, get_db
        path = str(tmp_path / "exec_test.db")
        init_db(path)
        conn = get_db(path)
        conn.execute(
            """INSERT INTO branches
               (name, neighborhood, cuisine, capacity, rating, latitude, longitude,
                price_range, dietary_vegetarian, dietary_vegan, dietary_gluten_free,
                dietary_halal, dietary_kosher, parking, outdoor_seating)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Test Italian Downtown", "Downtown", "Italian", 40, 4.2,
             40.71, -74.00, 2, 1, 0, 0, 0, 0, 1, 0),
        )
        conn.commit()
        conn.close()
        return path

    def _call(self, tool_name, args):
        return json.loads(get_mcp_client().call_tool(tool_name, args))

    def test_unknown_tool_returns_error(self):
        result = self._call("nonexistent_tool", {})
        assert "error" in result

    def test_missing_required_arg_returns_error(self):
        # check_availability requires branch_id, date, party_size
        result = self._call("check_availability", {})
        assert "error" in result

    def test_search_branches_dispatch(self, db_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "DB_PATH", db_path)
        result = self._call("search_branches", {"cuisine": "Italian"})
        assert isinstance(result, list)

    def test_check_availability_dispatch(self, db_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "DB_PATH", db_path)

        from config import get_db
        conn = get_db(db_path)
        branch_id = conn.execute("SELECT id FROM branches LIMIT 1").fetchone()["id"]
        conn.close()

        result = self._call(
            "check_availability",
            {"branch_id": branch_id, "date": "2026-12-01", "party_size": 2},
        )
        assert isinstance(result, list)
        assert "11:00" in result

    def test_log_search_failure_dispatch(self, db_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "DB_PATH", db_path)
        result = self._call(
            "log_search_failure",
            {"query": "Tibetan cuisine", "reason": "No cuisine match"},
        )
        assert result.get("logged") is True

    def test_get_user_profile_not_found(self, db_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "DB_PATH", db_path)
        result = self._call("get_user_profile", {"email": "nobody@example.com"})
        assert result.get("found") is False

    def test_get_corporate_account_not_found(self, db_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "DB_PATH", db_path)
        result = self._call(
            "get_corporate_account",
            {"company_name": "Nonexistent Corp"},
        )
        assert result.get("found") is False
