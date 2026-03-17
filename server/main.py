"""
AI Agent Platform — Multi-tenant CSKH
User tự add API key (LLM + Social). Platform chỉ là hand (nền tảng).
"""

from fastapi import FastAPI, Body, HTTPException, Header, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from datetime import datetime, timedelta
from collections import defaultdict
import json
import os
import uuid
import hashlib
import hmac
import pathlib
import asyncio
import httpx

app = FastAPI(title="AI Agent Platform", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# === STATIC FILES ===
STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", "/tmp/ai-agent-platform"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# === DATABASE (JSON file for MVP, upgrade to PostgreSQL later) ===
DB_FILE = DATA_DIR / "db.json"

def load_db():
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text())
        except:
            pass
    return {"users": {}, "agents": {}, "conversations": {}, "messages": {}}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, default=str, ensure_ascii=False, indent=2))

db = load_db()


# === AUTH ===
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_id: str) -> str:
    return hashlib.sha256(f"{user_id}:{uuid.uuid4()}:{datetime.utcnow()}".encode()).hexdigest()

def get_current_user(authorization: str = Header(None)):
    """Extract user from Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    token = authorization.split(" ")[1]
    for uid, user in db["users"].items():
        if user.get("token") == token:
            return {**user, "id": uid}
    raise HTTPException(401, "Invalid token")


# === AUTH ENDPOINTS ===

@app.post("/api/auth/register")
async def register(body: dict = Body(...)):
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    name = body.get("name", "")
    
    if not email or not password:
        raise HTTPException(400, "Email and password required")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    
    # Check duplicate
    for uid, user in db["users"].items():
        if user["email"] == email:
            raise HTTPException(400, "Email already registered")
    
    user_id = str(uuid.uuid4())[:8]
    token = generate_token(user_id)
    
    db["users"][user_id] = {
        "email": email,
        "name": name or email.split("@")[0],
        "password": hash_password(password),
        "token": token,
        "plan": "free",  # free | pro | business
        "created_at": datetime.utcnow().isoformat(),
    }
    save_db(db)
    
    return {"token": token, "user": {"id": user_id, "email": email, "name": db["users"][user_id]["name"], "plan": "free"}}


@app.post("/api/auth/login")
async def login(body: dict = Body(...)):
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    
    for uid, user in db["users"].items():
        if user["email"] == email and user["password"] == hash_password(password):
            token = generate_token(uid)
            user["token"] = token
            save_db(db)
            return {"token": token, "user": {"id": uid, "email": email, "name": user["name"], "plan": user.get("plan", "free")}}
    
    raise HTTPException(401, "Invalid email or password")


@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user["name"], "plan": user.get("plan", "free")}


# === AGENT ENDPOINTS ===

@app.get("/api/agents")
async def list_agents(user=Depends(get_current_user)):
    """List all agents for current user."""
    user_agents = []
    for aid, agent in db["agents"].items():
        if agent["user_id"] == user["id"]:
            # Don't expose API keys in list
            safe_agent = {k: v for k, v in agent.items() if k not in ("llm_api_key",)}
            safe_agent["id"] = aid
            if agent.get("llm_api_key"):
                safe_agent["llm_api_key"] = agent["llm_api_key"][:8] + "..." 
            user_agents.append(safe_agent)
    return {"agents": user_agents}


@app.post("/api/agents")
async def create_agent(body: dict = Body(...), user=Depends(get_current_user)):
    """Create a new AI agent."""
    # Check limits
    user_agent_count = sum(1 for a in db["agents"].values() if a["user_id"] == user["id"])
    plan_limits = {"free": 1, "pro": 5, "business": 20}
    if user_agent_count >= plan_limits.get(user.get("plan", "free"), 1):
        raise HTTPException(403, f"Agent limit reached for {user.get('plan', 'free')} plan")
    
    agent_id = str(uuid.uuid4())[:8]
    
    db["agents"][agent_id] = {
        "user_id": user["id"],
        "name": body.get("name", "My Agent"),
        "description": body.get("description", ""),
        "system_prompt": body.get("system_prompt", "Bạn là trợ lý AI chăm sóc khách hàng. Trả lời thân thiện, chính xác, ngắn gọn."),
        "llm_provider": body.get("llm_provider", "openai"),  # openai | anthropic | google
        "llm_model": body.get("llm_model", "gpt-4o-mini"),
        "llm_api_key": body.get("llm_api_key", ""),
        "knowledge_base": [],  # list of {title, content} items
        "channels": {},  # channel_type -> config
        "settings": {
            "language": "vi",
            "max_tokens": 500,
            "temperature": 0.7,
            "fallback_message": "Xin lỗi, tôi không hiểu câu hỏi. Vui lòng liên hệ nhân viên hỗ trợ.",
        },
        "stats": {"messages_total": 0, "messages_today": 0, "last_message_at": None},
        "active": True,
        "created_at": datetime.utcnow().isoformat(),
    }
    save_db(db)
    
    return {"id": agent_id, "message": "Agent created"}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str, user=Depends(get_current_user)):
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    result = {**agent, "id": agent_id}
    if agent.get("llm_api_key"):
        result["llm_api_key_preview"] = agent["llm_api_key"][:8] + "..."
    return result


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    
    updatable = ["name", "description", "system_prompt", "llm_provider", "llm_model", 
                 "llm_api_key", "settings", "active"]
    for key in updatable:
        if key in body:
            agent[key] = body[key]
    
    save_db(db)
    return {"status": "updated"}


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, user=Depends(get_current_user)):
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    del db["agents"][agent_id]
    save_db(db)
    return {"status": "deleted"}


# === KNOWLEDGE BASE ===

@app.post("/api/agents/{agent_id}/knowledge")
async def add_knowledge(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Add knowledge base entry (FAQ, product info, etc.)."""
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    
    entry = {
        "id": str(uuid.uuid4())[:8],
        "title": body.get("title", ""),
        "content": body.get("content", ""),
        "category": body.get("category", "general"),
        "created_at": datetime.utcnow().isoformat(),
    }
    agent["knowledge_base"].append(entry)
    save_db(db)
    return {"status": "added", "entry": entry}


@app.delete("/api/agents/{agent_id}/knowledge/{entry_id}")
async def delete_knowledge(agent_id: str, entry_id: str, user=Depends(get_current_user)):
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    agent["knowledge_base"] = [k for k in agent["knowledge_base"] if k["id"] != entry_id]
    save_db(db)
    return {"status": "deleted"}


# === CHANNEL MANAGEMENT ===

@app.post("/api/agents/{agent_id}/channels")
async def add_channel(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Connect a channel (telegram, zalo, facebook, webchat)."""
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    
    channel_type = body.get("type")  # telegram | zalo | facebook | webchat
    if channel_type not in ("telegram", "zalo", "facebook", "webchat"):
        raise HTTPException(400, "Invalid channel type. Supported: telegram, zalo, facebook, webchat")
    
    config = {
        "enabled": True,
        "connected_at": datetime.utcnow().isoformat(),
    }
    
    if channel_type == "telegram":
        config["bot_token"] = body.get("bot_token", "")
        if not config["bot_token"]:
            raise HTTPException(400, "Telegram bot token required")
    
    elif channel_type == "zalo":
        config["oa_token"] = body.get("oa_token", "")
        if not config["oa_token"]:
            raise HTTPException(400, "Zalo OA token required")
    
    elif channel_type == "facebook":
        config["page_token"] = body.get("page_token", "")
        config["verify_token"] = body.get("verify_token", str(uuid.uuid4())[:16])
        if not config["page_token"]:
            raise HTTPException(400, "Facebook page token required")
    
    elif channel_type == "webchat":
        config["widget_id"] = str(uuid.uuid4())[:12]
        config["allowed_origins"] = body.get("allowed_origins", ["*"])
    
    agent["channels"][channel_type] = config
    save_db(db)
    
    result = {"status": "connected", "channel": channel_type}
    if channel_type == "webchat":
        result["widget_id"] = config["widget_id"]
        result["embed_code"] = f'<script src="https://YOUR_DOMAIN/widget.js" data-agent="{agent_id}" data-widget="{config["widget_id"]}"></script>'
    
    return result


@app.delete("/api/agents/{agent_id}/channels/{channel_type}")
async def remove_channel(agent_id: str, channel_type: str, user=Depends(get_current_user)):
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    if channel_type in agent["channels"]:
        del agent["channels"][channel_type]
        save_db(db)
    return {"status": "disconnected"}


# === LLM PROXY (call user's own API key) ===

async def call_llm(agent: dict, messages: list) -> str:
    """Call LLM using the agent owner's API key."""
    provider = agent.get("llm_provider", "openai")
    api_key = agent.get("llm_api_key", "")
    model = agent.get("llm_model", "gpt-4o-mini")
    settings = agent.get("settings", {})
    
    if not api_key:
        return agent["settings"].get("fallback_message", "API key chưa được cấu hình.")
    
    # Build context with knowledge base
    kb_context = ""
    if agent.get("knowledge_base"):
        kb_items = [f"## {k['title']}\n{k['content']}" for k in agent["knowledge_base"][:20]]
        kb_context = "\n\n---\nKiến thức tham khảo:\n" + "\n\n".join(kb_items)
    
    system_msg = agent.get("system_prompt", "Bạn là trợ lý AI.") + kb_context
    
    full_messages = [{"role": "system", "content": system_msg}] + messages
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if provider == "openai":
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": full_messages, 
                          "max_tokens": settings.get("max_tokens", 500),
                          "temperature": settings.get("temperature", 0.7)},
                )
                data = resp.json()
                if "error" in data:
                    return f"LLM Error: {data['error'].get('message', 'Unknown error')}"
                return data["choices"][0]["message"]["content"]
            
            elif provider == "anthropic":
                # Convert messages format for Anthropic
                anthropic_msgs = [m for m in full_messages if m["role"] != "system"]
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": settings.get("max_tokens", 500),
                        "system": system_msg,
                        "messages": anthropic_msgs,
                    },
                )
                data = resp.json()
                if "error" in data:
                    return f"LLM Error: {data['error'].get('message', 'Unknown error')}"
                return data["content"][0]["text"]
            
            elif provider == "google":
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                    json={
                        "contents": [{"parts": [{"text": m["content"]}], "role": "user" if m["role"] == "user" else "model"} for m in full_messages if m["role"] != "system"],
                        "systemInstruction": {"parts": [{"text": system_msg}]},
                    },
                )
                data = resp.json()
                return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No response")
            
            else:
                return "Unsupported LLM provider"
    
    except Exception as e:
        return f"Error calling LLM: {str(e)}"


# === CHAT / MESSAGE HANDLING ===

@app.post("/api/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, body: dict = Body(...)):
    """Public endpoint — receive message from any channel, get AI response."""
    agent = db["agents"].get(agent_id)
    if not agent or not agent.get("active"):
        raise HTTPException(404, "Agent not found or inactive")
    
    message = body.get("message", "").strip()
    channel = body.get("channel", "webchat")
    sender_id = body.get("sender_id", "anonymous")
    
    if not message:
        raise HTTPException(400, "Message required")
    
    # Get or create conversation
    conv_key = f"{agent_id}:{channel}:{sender_id}"
    if conv_key not in db["conversations"]:
        db["conversations"][conv_key] = {
            "agent_id": agent_id,
            "channel": channel,
            "sender_id": sender_id,
            "created_at": datetime.utcnow().isoformat(),
            "message_count": 0,
        }
    
    if conv_key not in db["messages"]:
        db["messages"][conv_key] = []
    
    # Add user message
    db["messages"][conv_key].append({
        "role": "user",
        "content": message,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    # Keep last 20 messages for context
    recent = db["messages"][conv_key][-20:]
    chat_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
    
    # Call LLM
    response = await call_llm(agent, chat_messages)
    
    # Save assistant message
    db["messages"][conv_key].append({
        "role": "assistant",
        "content": response,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    # Update stats
    agent["stats"]["messages_total"] = agent["stats"].get("messages_total", 0) + 1
    agent["stats"]["last_message_at"] = datetime.utcnow().isoformat()
    db["conversations"][conv_key]["message_count"] = len(db["messages"][conv_key])
    
    save_db(db)
    
    return {"response": response, "conversation_id": conv_key}


# === CONVERSATIONS LIST ===

@app.get("/api/agents/{agent_id}/conversations")
async def list_conversations(agent_id: str, user=Depends(get_current_user)):
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    
    convs = []
    for key, conv in db["conversations"].items():
        if conv["agent_id"] == agent_id:
            msgs = db["messages"].get(key, [])
            convs.append({
                "id": key,
                **conv,
                "last_message": msgs[-1] if msgs else None,
                "message_count": len(msgs),
            })
    convs.sort(key=lambda x: x.get("last_message", {}).get("timestamp", ""), reverse=True)
    return {"conversations": convs}


@app.get("/api/agents/{agent_id}/conversations/{conv_id:path}")
async def get_conversation(agent_id: str, conv_id: str, user=Depends(get_current_user)):
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    
    msgs = db["messages"].get(conv_id, [])
    return {"conversation_id": conv_id, "messages": msgs}


# === TELEGRAM WEBHOOK ===

@app.post("/api/webhook/telegram/{agent_id}")
async def telegram_webhook(agent_id: str, body: dict = Body(...)):
    """Receive Telegram updates."""
    agent = db["agents"].get(agent_id)
    if not agent or not agent.get("active"):
        return {"ok": True}
    
    tg_config = agent.get("channels", {}).get("telegram", {})
    if not tg_config.get("enabled"):
        return {"ok": True}
    
    # Extract message
    msg = body.get("message", {})
    text = msg.get("text", "")
    chat_id = str(msg.get("chat", {}).get("id", ""))
    
    if not text or not chat_id:
        return {"ok": True}
    
    # Get AI response
    conv_key = f"{agent_id}:telegram:{chat_id}"
    if conv_key not in db["messages"]:
        db["messages"][conv_key] = []
    if conv_key not in db["conversations"]:
        db["conversations"][conv_key] = {
            "agent_id": agent_id, "channel": "telegram",
            "sender_id": chat_id, "created_at": datetime.utcnow().isoformat(),
            "sender_name": msg.get("from", {}).get("first_name", ""),
            "message_count": 0,
        }
    
    db["messages"][conv_key].append({"role": "user", "content": text, "timestamp": datetime.utcnow().isoformat()})
    
    recent = db["messages"][conv_key][-20:]
    response = await call_llm(agent, [{"role": m["role"], "content": m["content"]} for m in recent])
    
    db["messages"][conv_key].append({"role": "assistant", "content": response, "timestamp": datetime.utcnow().isoformat()})
    agent["stats"]["messages_total"] = agent["stats"].get("messages_total", 0) + 1
    agent["stats"]["last_message_at"] = datetime.utcnow().isoformat()
    save_db(db)
    
    # Send reply via Telegram API
    bot_token = tg_config.get("bot_token", "")
    if bot_token:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": int(chat_id), "text": response},
            )
    
    return {"ok": True}


# === FACEBOOK WEBHOOK ===

@app.get("/api/webhook/facebook/{agent_id}")
async def facebook_verify(agent_id: str, request: Request):
    """Facebook webhook verification."""
    agent = db["agents"].get(agent_id)
    if not agent:
        raise HTTPException(404)
    
    fb_config = agent.get("channels", {}).get("facebook", {})
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode == "subscribe" and token == fb_config.get("verify_token"):
        return int(challenge)
    raise HTTPException(403, "Verification failed")


@app.post("/api/webhook/facebook/{agent_id}")
async def facebook_webhook(agent_id: str, body: dict = Body(...)):
    """Receive Facebook Messenger messages."""
    agent = db["agents"].get(agent_id)
    if not agent or not agent.get("active"):
        return {"status": "ok"}
    
    fb_config = agent.get("channels", {}).get("facebook", {})
    if not fb_config.get("enabled"):
        return {"status": "ok"}
    
    for entry in body.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = str(event.get("sender", {}).get("id", ""))
            text = event.get("message", {}).get("text", "")
            
            if not text or not sender_id:
                continue
            
            conv_key = f"{agent_id}:facebook:{sender_id}"
            if conv_key not in db["messages"]:
                db["messages"][conv_key] = []
            if conv_key not in db["conversations"]:
                db["conversations"][conv_key] = {
                    "agent_id": agent_id, "channel": "facebook",
                    "sender_id": sender_id, "created_at": datetime.utcnow().isoformat(),
                    "message_count": 0,
                }
            
            db["messages"][conv_key].append({"role": "user", "content": text, "timestamp": datetime.utcnow().isoformat()})
            
            recent = db["messages"][conv_key][-20:]
            response = await call_llm(agent, [{"role": m["role"], "content": m["content"]} for m in recent])
            
            db["messages"][conv_key].append({"role": "assistant", "content": response, "timestamp": datetime.utcnow().isoformat()})
            agent["stats"]["messages_total"] = agent["stats"].get("messages_total", 0) + 1
            save_db(db)
            
            # Reply via Facebook API
            page_token = fb_config.get("page_token", "")
            if page_token:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "https://graph.facebook.com/v18.0/me/messages",
                        params={"access_token": page_token},
                        json={"recipient": {"id": sender_id}, "message": {"text": response}},
                    )
    
    return {"status": "ok"}


# === WEBCHAT WIDGET ENDPOINT ===

@app.get("/widget.js")
async def widget_js():
    """Serve the webchat widget script."""
    return FileResponse(str(STATIC_DIR / "widget.js"), media_type="application/javascript")


# === DASHBOARD ===

@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/dashboard")
async def dashboard():
    return FileResponse(str(STATIC_DIR / "dashboard.html"))


# === STATS ===

@app.get("/api/stats")
async def get_stats(user=Depends(get_current_user)):
    """Get overview stats for user."""
    user_agents = [a for a in db["agents"].values() if a["user_id"] == user["id"]]
    total_messages = sum(a.get("stats", {}).get("messages_total", 0) for a in user_agents)
    total_convs = sum(1 for c in db["conversations"].values() 
                      if c["agent_id"] in [aid for aid, a in db["agents"].items() if a["user_id"] == user["id"]])
    
    return {
        "agents": len(user_agents),
        "conversations": total_convs,
        "messages": total_messages,
        "plan": user.get("plan", "free"),
    }


# === TELEGRAM BOT SETUP HELPER ===

@app.post("/api/agents/{agent_id}/setup-telegram")
async def setup_telegram_webhook(agent_id: str, user=Depends(get_current_user)):
    """Auto-register Telegram webhook for the agent."""
    agent = db["agents"].get(agent_id)
    if not agent or agent["user_id"] != user["id"]:
        raise HTTPException(404, "Agent not found")
    
    tg = agent.get("channels", {}).get("telegram", {})
    bot_token = tg.get("bot_token", "")
    if not bot_token:
        raise HTTPException(400, "Telegram bot token not configured")
    
    # Get server URL from env or request
    server_url = os.getenv("SERVER_URL", "https://YOUR_DOMAIN")
    webhook_url = f"{server_url}/api/webhook/telegram/{agent_id}"
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={"url": webhook_url},
        )
        result = resp.json()
    
    return {"status": "ok" if result.get("ok") else "error", "webhook_url": webhook_url, "telegram_response": result}


# === HEALTH ===

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "users": len(db["users"]),
        "agents": len(db["agents"]),
        "conversations": len(db["conversations"]),
    }
