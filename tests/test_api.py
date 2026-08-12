"""
Unit Tests for FastAPI Server Endpoints (server/main.py).
"""

from __future__ import annotations

from unittest.mock import patch
import json

from fastapi.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_api_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_history_new_session():
    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["messages"] == []


def test_api_reset_session():
    response = client.post("/api/reset", headers={"x-session-id": "test-session-123"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["handed_off"] is False
    assert data["nudged"] is False
    assert data["session_id"]
    assert data["session_id"] != "test-session-123"


def test_api_chat_empty_message_fails():
    response = client.post("/api/chat", data={"message": "   "})
    assert response.status_code == 400
    assert "Send a message or an image" in response.json()["detail"]


def test_api_chat_success():
    mock_products = [
        {"sku": "SOBP001", "name": "Test Backpack", "in_stock": True}
    ]
    with patch("server.main.run_agent") as mock_run_agent:
        mock_run_agent.return_value = (
            "Onward into the unknown! ⛰️",
            [],
            mock_products,
            {"handed_off": False},
        )
        
        response = client.post(
            "/api/chat",
            data={"message": "Recommend a backpack"},
            headers={"x-session-id": "test-session-456"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-456"
        assert "Onward into the unknown!" in data["message"]
        assert data["products"] == mock_products


def test_serve_asset_not_found():
    response = client.get("/assets/non_existent_file_9999.png")
    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found"


def test_api_config_exposes_idle_seconds():
    response = client.get("/api/config")
    assert response.status_code == 200
    seconds = response.json()["nudge_idle_seconds"]
    assert isinstance(seconds, int)
    assert 5 <= seconds <= 3600


def test_nudge_skipped_without_exchange():
    response = client.post("/api/nudge", headers={"x-session-id": "nudge-empty-sid"})
    assert response.status_code == 200
    data = response.json()
    assert data["skipped"] is True
    assert data["reason"] == "no_exchange"


def test_nudge_is_one_shot_and_reset_clears_it():
    sid = "nudge-once-sid"
    with patch("server.main.run_agent") as mock_agent:
        mock_agent.return_value = (
            "Order is delivered.",
            [],
            None,
            {"handed_off": False},
        )
        client.post(
            "/api/chat",
            data={"message": "status of W001"},
            headers={"x-session-id": sid},
        )

    with patch("server.main.run_nudge") as mock_nudge:
        mock_nudge.return_value = ("Still on the trail?", [])
        first = client.post("/api/nudge", headers={"x-session-id": sid})
        assert first.json()["already_sent"] is False
        assert first.json()["message"] == "Still on the trail?"
        second = client.post("/api/nudge", headers={"x-session-id": sid})
        assert second.json()["already_sent"] is True
        assert mock_nudge.call_count == 1

    reset = client.post("/api/reset", headers={"x-session-id": sid})
    assert reset.json()["nudged"] is False
    assert reset.json()["handed_off"] is False
    fresh = reset.json()["session_id"]
    after = client.post("/api/nudge", headers={"x-session-id": fresh})
    assert after.json()["skipped"] is True


def test_handoff_mutes_agent_until_reset():
    sid = "handoff-mute-sid"
    with patch("server.main.run_agent") as mock_agent:
        mock_agent.return_value = (
            "A human trail guide will pick this up shortly.",
            [],
            None,
            {"handed_off": True, "handoff_reason": "explicit_request"},
        )
        first = client.post(
            "/api/chat",
            data={"message": "I want to talk to a person about a refund"},
            headers={"x-session-id": sid},
        )
        assert first.json()["handed_off"] is True
        assert first.json()["kind"] == "handoff"
        assert mock_agent.call_count == 1

        note = client.post(
            "/api/chat",
            data={"message": "My order was damaged"},
            headers={"x-session-id": sid},
        )
        assert note.json()["muted"] is True
        assert note.json()["kind"] == "handoff_ack"
        assert mock_agent.call_count == 1

    reset = client.post("/api/reset", headers={"x-session-id": sid})
    fresh = reset.json()["session_id"]
    assert reset.json()["handed_off"] is False
    with patch("server.main.run_agent") as mock_agent:
        mock_agent.return_value = ("Back on the trail!", [], None, {"handed_off": False})
        again = client.post(
            "/api/chat",
            data={"message": "hi"},
            headers={"x-session-id": fresh},
        )
        assert again.json()["handed_off"] is False
        assert again.json()["muted"] is False
        assert mock_agent.call_count == 1


def test_rating_writes_mock_store(monkeypatch, tmp_path):
    monkeypatch.setattr("server.ratings.DATA_DIR", tmp_path)
    monkeypatch.setattr("server.ratings.RATINGS_PATH", tmp_path / "ratings.json")
    monkeypatch.setattr("server.ratings._ratings", [])
    monkeypatch.setattr("server.ratings._loaded", True)

    sid = "rating-sid"
    response = client.post(
        "/api/rating",
        json={"rating": "up", "comment": "found my order fast"},
        headers={"x-session-id": sid},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    stored = json.loads((tmp_path / "ratings.json").read_text())
    assert stored[0]["rating"] == "up"
    assert stored[0]["comment"] == "found my order fast"

    again = client.post(
        "/api/rating",
        json={"rating": "down"},
        headers={"x-session-id": sid},
    )
    assert again.json()["already_rated"] is True
    stored = json.loads((tmp_path / "ratings.json").read_text())
    assert len(stored) == 1
