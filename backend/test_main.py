import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app

client = TestClient(app)

# Helper to generate unique session IDs for isolation
def get_session_id(test_name):
    return f"test_sess_{test_name}"

# --- TEST 1: ONBOARDING FLOW (Happy Path) ---
def test_happy_path_onboarding():
    sid = get_session_id("happy")

    # 1. Init
    res = client.post("/chat", json={"session_id": sid, "message": ""})
    assert res.status_code == 200
    assert "name" in res.json()["response"].lower()
    assert res.json()["state"] == "collecting_name"

    # 2. Name
    res = client.post("/chat", json={"session_id": sid, "message": "John Doe"})
    assert res.json()["state"] == "collecting_email"

    # 3. Email (Valid)
    res = client.post("/chat", json={"session_id": sid, "message": "john@example.com"})
    assert res.json()["state"] == "collecting_phone"

    # 4. Phone (Valid)
    res = client.post("/chat", json={"session_id": sid, "message": "1234567890"})
    assert res.json()["state"] == "completed"
    assert "fully onboarded" in res.json()["response"]

# --- TEST 2: VALIDATION LOGIC (Constraint: Valid/Invalid Email & Phone) ---
def test_validation_logic():
    sid = get_session_id("validation")
    
    # Skip to email step
    client.post("/chat", json={"session_id": sid, "message": ""}) # Init
    client.post("/chat", json={"session_id": sid, "message": "John"}) # Name

    # Invalid Email
    res = client.post("/chat", json={"session_id": sid, "message": "not_an_email"})
    assert "doesn't look like a valid email" in res.json()["response"]
    assert res.json()["state"] == "collecting_email" # State shouldn't advance

    # Valid Email
    client.post("/chat", json={"session_id": sid, "message": "john@test.com"})
    
    # Invalid Phone
    res = client.post("/chat", json={"session_id": sid, "message": "abcde"})
    assert "valid phone number" in res.json()["response"]
    assert res.json()["state"] == "collecting_phone"

# --- TEST 3: NUDGES (Constraint: Chat nudges user) ---
def test_nudge_mechanism():
    sid = get_session_id("nudge")
    client.post("/chat", json={"session_id": sid, "message": ""}) # Init
    
    # User ignores "What is your name?" and asks a question instead
    # We mock the LLM to return a static answer so we don't hit the API
    with patch("main.query_llm") as mock_llm:
        mock_llm.return_value = "Occams Advisory provides financial services."
        
        res = client.post("/chat", json={"session_id": sid, "message": "What do you do?"})
        
        # Check for Answer + Nudge
        answer = res.json()["response"]
        assert "Occams Advisory provides" in answer # The answer
        assert "(By the way, I still need your name" in answer # The nudge

# --- TEST 4: UNKNOWN QUESTION / FALLBACK (Constraint: Safe Fallback) ---
def test_offline_fallback():
    sid = get_session_id("fallback")
    
    # Initialize the chat first so the bot enters "collecting_name" mode
    client.post("/chat", json={"session_id": sid, "message": ""})
    
    # We force the LLM function to return the "Offline" message
    with patch("main.query_llm") as mock_llm:
        mock_llm.return_value = "[Offline Mode] I couldn't connect..."
        
        # Now ask the question
        res = client.post("/chat", json={"session_id": sid, "message": "Tell me about taxes?"})
        
        # Debug print if it fails again
        print("Bot Response:", res.json()["response"])
        
        assert "[Offline Mode]" in res.json()["response"]