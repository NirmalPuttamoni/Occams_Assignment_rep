import json
import re
import os
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Initialize App
app = FastAPI(title="Occams AI Assistant")

# Enable CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- IN-MEMORY DATABASE (Minimal Stack) ---
# In a real production app, use Redis or SQLite.
# Structure: { "session_id": { "step": "name", "data": {...}, "history": [] } }
sessions: Dict[str, Dict] = {}

# Load Knowledge Base (Offline Brain)
try:
    with open("knowledge.json", "r", encoding="utf-8") as f:
        KNOWLEDGE_BASE = json.load(f)
except FileNotFoundError:
    print("WARNING: knowledge.json not found. Run ingest.py first.")
    KNOWLEDGE_BASE = []

# --- MODELS ---
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    state: str  # e.g., "collecting_name", "completed", etc.

# --- HELPER FUNCTIONS ---

def find_best_match(query: str) -> str:
    """
    OFFLINE FALLBACK & GROUNDING [cite: 20]
    Simple keyword search against knowledge.json. 
    Returns the most relevant text chunk.
    """
    query_words = set(query.lower().split())
    best_score = 0
    best_content = ""

    # Handle both single object and array formats
    items = KNOWLEDGE_BASE if isinstance(KNOWLEDGE_BASE, list) else [KNOWLEDGE_BASE]

    for item in items:
        content = item.get("content", "")
        # Count overlapping words (Jaccard-ish)
        score = sum(1 for word in query_words if word in content.lower())
        
        if score > best_score:
            best_score = score
            best_content = content

    # Threshold to prevent hallucinations on irrelevant data
    if best_score < 1: 
        return None
    
    # Return a truncated chunk (Simplicity)
    return best_content[:1000] 

def query_llm(context: str, user_query: str) -> str:
    """
    LLM WRAPPER [cite: 18, 19]
    1. Uses context from scraping.
    2. Handles offline errors gracefully.
    """
    # 1. Check for API Key (or Mock it)
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return f"I'm in offline mode. Based on my internal data: {context[:300]}..."

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        system_prompt = (
            "You are an assistant for Occams Advisory. "
            "Answer the question strictly based on the provided context. "
            "If the answer is not in the context, say 'I don't have that information'."
            "Be concise."
            "Answer in 3 to 4 lines."
        )
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context: {context}\n\nQuestion: {user_query}"}
            ],
            timeout=5  # Fail fast for offline demo
        )
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"LLM Error: {e}")
        # Graceful degradation [cite: 20]
        return f"(Network unavailable) Here is what I found in my records: {context[:400]}..."

# --- ONBOARDING LOGIC [cite: 6, 8] ---

def handle_onboarding(session_id: str, message: str):
    session = sessions[session_id]
    step = session["step"]
    
    # Regex Patterns
    email_pattern = r"[^@]+@[^@]+\.[^@]+"
    phone_pattern = r"\d{10,}" # Simple 10+ digit check

    if step == "init":
        session["step"] = "collecting_name"
        return "Welcome to Occams Advisory! To get started, may I have your name?"

    if step == "collecting_name":
        # Assume input is name (Simplification for MVP)
        session["data"]["name"] = message
        session["step"] = "collecting_email"
        return f"Nice to meet you, {message}. What is your email address?"

    if step == "collecting_email":
        if re.search(email_pattern, message):
            session["data"]["email"] = message
            session["step"] = "collecting_phone"
            return "Got it. Finally, what is a good phone number to reach you?"
        else:
            # Nudge user [cite: 34]
            return "That doesn't look like a valid email. Could you please try again?"

    if step == "collecting_phone":
        if re.search(phone_pattern, message):
            session["data"]["phone"] = message
            session["step"] = "completed"
            return "All set! You're fully onboarded. Feel free to ask me anything about our services."
        else:
            return "Please enter a valid phone number (digits only)."

    return None

# --- API ENDPOINTS ---

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    sid = request.session_id
    msg = request.message.strip()

    # Create session if not exists
    if sid not in sessions:
        sessions[sid] = {"step": "init", "data": {}, "history": []}
        greeting = handle_onboarding(sid, "")
        # Trigger first greeting
        return ChatResponse(response=greeting, state=sessions[sid]["step"])
        # return ChatResponse(response=handle_onboarding(sid, ""), state="init")

    # 1. INTERCEPT: Is this an answer to an onboarding question?
    current_step = sessions[sid]["step"]
    
    # Simple heuristic: If we are not complete, treat input as potential onboarding data
    # UNLESS the user asks a question (contains "?")
    is_question = "?" in msg
    
    if current_step != "completed" and not is_question:
        response = handle_onboarding(sid, msg)
        if response:
             return ChatResponse(response=response, state=sessions[sid]["step"])

    # 2. RAG LOGIC: User asked a question or ignored the nudge
    context = find_best_match(msg)
    
    if context:
        answer = query_llm(context, msg)
    else:
        answer = "I'm sorry, I couldn't find information about that on our website."

    # 3. NUDGE: If not onboarded, append a reminder [cite: 34]
    if current_step != "completed":
        # Identify what is missing
        missing = "name" if current_step == "collecting_name" else \
                  "email" if current_step == "collecting_email" else "phone"
        
        answer += f"\n\n(By the way, I still need your {missing} to finish your setup!)"

    return ChatResponse(response=answer, state=current_step)

@app.get("/debug/{session_id}")
async def get_state(session_id: str):
    """Helper to view captured state without logging it to console."""
    return sessions.get(session_id, {})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)