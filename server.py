import os
import uvicorn
import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv

# Load your local config
load_dotenv("main.env")

app = FastAPI(title="Abrar AI Production Bridge")

# Local Llama Settings
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

@app.get("/")
async def root():
    """Health check to confirm the server is running and accessible."""
    return {
        "status": "Abrar AI Core is online",
        "endpoints": ["/vapi-webhook", "/chat/completions"],
        "model": OLLAMA_MODEL
    }

@app.post("/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-Compatible endpoint for Vapi.
    Vapi will send the conversation history here, and we forward it to local Llama.
    """
    payload = await request.json()
    messages = payload.get("messages", [])
    
    # Extract the latest thing the user said
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
            break
            
    # Prepare the payload for your local Ollama engine
    ollama_payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"You are Abrar Assistant. Keep your answers brief and conversational. User says: {user_text}",
        "stream": False,
        "options": {"temperature": 0.3}
    }
    
    ai_reply = "I am processing that."
    try:
        # Call the local model
        response = requests.post(OLLAMA_URL, json=ollama_payload, timeout=8)
        if response.status_code == 200:
            ai_reply = response.json().get("response", "I understand.")
    except Exception as e:
        print(f"[OLLAMA ERROR]: {str(e)}")
        ai_reply = "I am having trouble connecting to my local brain."

    # Return the exact JSON structure Vapi expects from a Custom LLM
    return {
        "id": "chatcmpl-abrar-local",
        "object": "chat.completion",
        "created": 1700000000,
        "model": OLLAMA_MODEL,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": ai_reply,
            },
            "finish_reason": "stop"
        }]
    }

@app.post("/vapi-webhook")
async def vapi_webhook(request: Request):
    """
    Main Telephony Webhook.
    Vapi hits this when the phone rings to ask what it should do.
    """
    data = await request.json()
    message = data.get("message", {})
    msg_type = message.get("type")
    
    # 1. When the call connects, Vapi asks for Assistant Instructions
    if msg_type == "assistant-request":
        # Automatically detect your current Ngrok/Cloudflare URL
        host = request.headers.get("host")
        scheme = request.headers.get("x-forwarded-proto", "https")
        custom_llm_url = f"{scheme}://{host}/chat/completions"
        
        print(f"Incoming call routed. Pointing Vapi to Local LLM at: {custom_llm_url}")
        
        # Tell Vapi to use YOUR server as its brain
        return {
            "assistant": {
                "name": "Abrar Local Assistant",
                "model": {
                    "provider": "custom-llm",
                    "url": custom_llm_url,
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant."
                        }
                    ]
                }
            }
        }
        
    # 2. Log real-time transcripts to your terminal
    if msg_type == "transcript":
        transcript = message.get("transcript")
        if transcript:
            print(f"[CALLER]: {transcript}")
        return {"status": "ok"}
        
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)