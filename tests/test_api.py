"""
Unit Tests for FastAPI Server Endpoints (server/main.py).
"""

from __future__ import annotations

from unittest.mock import patch

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
    assert data["session_id"] == "test-session-123"
    assert data["ok"] is True


def test_api_chat_empty_message_fails():
    response = client.post("/api/chat", data={"message": "   "})
    assert response.status_code == 400
    assert "Send a message or an image" in response.json()["detail"]


def test_api_chat_success():
    mock_products = [
        {"sku": "SOBP001", "name": "Test Backpack", "in_stock": True}
    ]
    with patch("server.main.run_agent") as mock_run_agent:
        mock_run_agent.return_value = ("Onward into the unknown! ⛰️", [], mock_products)
        
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
