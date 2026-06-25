import pytest
import sys
from pathlib import Path

# Ensure the root project directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.server import app, get_db

client = TestClient(app)

def test_chat_completions_missing_auth():
    """Test that missing X-Personal-Number header results in a 401 Error."""
    response = client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "Hello"}]
    })
    assert response.status_code == 401
    assert "Personal number" in response.json()["detail"]

def test_chat_completions_empty_messages():
    """Test that an empty messages array is handled correctly."""
    response = client.post("/v1/chat/completions", 
        headers={"X-Personal-Number": "1234567"}, 
        json={"messages": []}
    )
    assert response.status_code == 400
    assert "Messages array cannot be empty" in response.json()["detail"]

def test_chat_completions_invalid_personal_number():
    """Test that an invalid personal number results in a 401 Error."""
    # This requires DB access to check if the user exists.
    # 0000000 should not exist in the seeded data.
    response = client.post("/v1/chat/completions", 
        headers={"X-Personal-Number": "0000000"}, 
        json={"messages": [{"role": "user", "content": "Hello"}]}
    )
    assert response.status_code == 401
    assert "Invalid or inactive personal number" in response.json()["detail"]
