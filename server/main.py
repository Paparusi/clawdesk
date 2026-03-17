"""
AI Agent Platform — Multi-tenant CSKH
Upgraded with Supabase PostgreSQL + JWT Auth + RLS
"""

from fastapi import FastAPI, Body, HTTPException, Header, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pathlib
import asyncio
import httpx
import os
import uuid

# Import database helpers
from server.db import (
    get_supabase, get_supabase_anon, get_current_user,
    list_agents, get_agent, create_agent, update_agent, delete_agent, count_user_agents, increment_agent_stats,
    list_channels, get_channel, upsert_channel, delete_channel,
    list_knowledge, create_knowledge, delete_knowledge,
    get_or_create_conversation, list_conversations, update_conversation_stats,
    create_message, get_recent_messages, count_conversation_messages,
    get_user_stats, get_profile,
)

app = FastAPI(title="AI Agent Platform", version="2.0")

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


# === AUTH ENDPOINTS ===

@app.post("/api/auth/register")
async def register(body: dict = Body(...)):
    """Register new user with Supabase Auth"""
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    name = body.get("name", "")
    
    if not email or not password:
        raise HTTPException(400, "Email and password required")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    
    try:
        sb = get_supabase_anon()
        
        # Sign up with Supabase Auth
        result = sb.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "name": name or email.split("@")[0]
                }
            }
        })
        
        if not result.user:
            raise HTTPException(400, "Registration failed")
        
        return {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
            "user": {
                "id": result.user.id,
                "email": result.user.email,
                "name": result.user.user_metadata.get("name", ""),
            }
        }
    
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower():
            raise HTTPException(400, "Email already registered")
        raise HTTPException(400, f"Registration error: {error_msg}")


@app.post("/api/auth/login")
async def login(body: dict = Body(...)):
    """Login with email and password"""
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    
    if not email or not password:
        raise HTTPException(400, "Email and password required")
    
    try:
        sb = get_supabase_anon()
        result = sb.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not result.user:
            raise HTTPException(401, "Invalid email or password")
        
        # Get profile
        profile = get_profile(result.user.id)
        
        return {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
            "user": {
                "id": result.user.id,
                "email": result.user.email,
                "name": profile.get("name", "") if profile else "",
                "plan": profile.get("plan", "free") if profile else "free",
            }
        }
    
    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower():
            raise HTTPException(401, "Invalid email or password")
        raise HTTPException(400, f"Login error: {error_msg}")


@app.post("/api/auth/refresh")
async def refresh_token(body: dict = Body(...)):
    """Refresh access token using refresh token"""
    refresh_token = body.get("refresh_token", "")
    
    if not refresh_token:
        raise HTTPException(400, "Refresh token required")
    
    try:
        sb = get_supabase_anon()
        result = sb.auth.refresh_session(refresh_token)
        
        if not result.session:
            raise HTTPException(401, "Invalid refresh token")
        
        return {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
        }
    
    except Exception as e:
        raise HTTPException(401, f"Token refresh failed: {str(e)}")


@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    """Get current user profile"""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
        "plan": user.get("plan", "free"),
    }


# === AGENT ENDPOINTS ===

@app.get("/api/agents")
async def get_agents(user=Depends(get_current_user)):
    """List all agents for current user"""
    try:
        agents = list_agents(user["id"])
        
        # Get channels for each agent
        for agent in agents:
            agent["channels"] = {ch["type"]: ch for ch in list_channels(agent["id"])}
            
            # Mask API key
            if agent.get("llm_api_key"):
                agent["llm_api_key_preview"] = agent["llm_api_key"][:8] + "..."
                del agent["llm_api_key"]
        
        return {"agents": agents}
    
    except Exception as e:
        raise HTTPException(500, f"Failed to list agents: {str(e)}")


@app.post("/api/agents")
async def create_new_agent(body: dict = Body(...), user=Depends(get_current_user)):
    """Create a new AI agent"""
    try:
        # Check plan limits
        agent_count = count_user_agents(user["id"])
        plan_limits = {"free": 1, "pro": 5, "business": 20}
        user_plan = user.get("plan", "free")
        
        if agent_count >= plan_limits.get(user_plan, 1):
            raise HTTPException(403, f"Agent limit reached for {user_plan} plan")
        
        agent = create_agent(user["id"], body)
        
        if not agent:
            raise HTTPException(500, "Failed to create agent")
        
        return {"id": agent["id"], "message": "Agent created"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create agent: {str(e)}")


@app.get("/api/agents/{agent_id}")
async def get_agent_details(agent_id: str, user=Depends(get_current_user)):
    """Get agent details"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        # Get channels
        agent["channels"] = {ch["type"]: ch for ch in list_channels(agent_id)}
        
        # Get knowledge base
        agent["knowledge_base"] = list_knowledge(agent_id)
        
        # Mask API key
        if agent.get("llm_api_key"):
            agent["llm_api_key_preview"] = agent["llm_api_key"][:8] + "..."
        
        return agent
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get agent: {str(e)}")


@app.put("/api/agents/{agent_id}")
async def update_agent_details(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Update agent configuration"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        # Only allow updating specific fields
        updatable = ["name", "description", "system_prompt", "llm_provider", 
                     "llm_model", "llm_api_key", "settings", "active"]
        update_data = {k: v for k, v in body.items() if k in updatable}
        
        if update_data:
            update_agent(agent_id, update_data)
        
        return {"status": "updated"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to update agent: {str(e)}")


@app.delete("/api/agents/{agent_id}")
async def delete_agent_endpoint(agent_id: str, user=Depends(get_current_user)):
    """Delete an agent"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        delete_agent(agent_id)
        
        return {"status": "deleted"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete agent: {str(e)}")


# === KNOWLEDGE BASE ===

@app.post("/api/agents/{agent_id}/knowledge")
async def add_knowledge_entry(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Add knowledge base entry"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        entry = create_knowledge(agent_id, body)
        
        return {"status": "added", "entry": entry}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to add knowledge: {str(e)}")


@app.delete("/api/agents/{agent_id}/knowledge/{entry_id}")
async def delete_knowledge_entry(agent_id: str, entry_id: str, user=Depends(get_current_user)):
    """Delete knowledge base entry"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        delete_knowledge(entry_id)
        
        return {"status": "deleted"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete knowledge: {str(e)}")


# === CHANNEL MANAGEMENT ===

@app.post("/api/agents/{agent_id}/channels")
async def add_channel_endpoint(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Connect a channel (telegram, zalo, facebook, webchat)"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        channel_type = body.get("type")
        if channel_type not in ("telegram", "zalo", "facebook", "webchat"):
            raise HTTPException(400, "Invalid channel type. Supported: telegram, zalo, facebook, webchat")
        
        config = {}
        
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
        
        channel = upsert_channel(agent_id, channel_type, config)
        
        result = {"status": "connected", "channel": channel_type}
        if channel_type == "webchat":
            result["widget_id"] = config["widget_id"]
            result["embed_code"] = f'<script src="https://YOUR_DOMAIN/widget.js" data-agent="{agent_id}" data-widget="{config["widget_id"]}"></script>'
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to add channel: {str(e)}")


@app.delete("/api/agents/{agent_id}/channels/{channel_type}")
async def remove_channel_endpoint(agent_id: str, channel_type: str, user=Depends(get_current_user)):
    """Remove a channel"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        delete_channel(agent_id, channel_type)
        
        return {"status": "disconnected"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to remove channel: {str(e)}")


# === LLM PROXY ===

async def call_llm(agent: dict, messages: list) -> str:
    """Call LLM using the agent owner's API key"""
    provider = agent.get("llm_provider", "openai")
    api_key = agent.get("llm_api_key", "")
    model = agent.get("llm_model", "gpt-4o-mini")
    settings = agent.get("settings", {})
    
    if not api_key:
        return settings.get("fallback_message", "API key chưa được cấu hình.")
    
    # Build context with knowledge base
    kb_context = ""
    kb_entries = list_knowledge(agent["id"])
    if kb_entries:
        kb_items = [f"## {k['title']}\n{k['content']}" for k in kb_entries[:20]]
        kb_context = "\n\n---\nKiến thức tham khảo:\n" + "\n\n".join(kb_items)
    
    system_msg = agent.get("system_prompt", "Bạn là trợ lý AI.") + kb_context
    
    full_messages = [{"role": "system", "content": system_msg}] + messages
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if provider == "openai":
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": full_messages,
                        "max_tokens": settings.get("max_tokens", 500),
                        "temperature": settings.get("temperature", 0.7)
                    },
                )
                data = resp.json()
                if "error" in data:
                    return f"LLM Error: {data['error'].get('message', 'Unknown error')}"
                return data["choices"][0]["message"]["content"]
            
            elif provider == "anthropic":
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
                        "contents": [
                            {"parts": [{"text": m["content"]}], "role": "user" if m["role"] == "user" else "model"}
                            for m in full_messages if m["role"] != "system"
                        ],
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
    """Public endpoint — receive message from any channel, get AI response"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or not agent.get("active"):
            raise HTTPException(404, "Agent not found or inactive")
        
        message = body.get("message", "").strip()
        channel = body.get("channel", "webchat")
        sender_id = body.get("sender_id", "anonymous")
        sender_name = body.get("sender_name", "")
        
        if not message:
            raise HTTPException(400, "Message required")
        
        # Get or create conversation
        conversation = get_or_create_conversation(agent_id, channel, sender_id, sender_name)
        
        if not conversation:
            raise HTTPException(500, "Failed to create conversation")
        
        conv_id = conversation["id"]
        
        # Add user message
        create_message(conv_id, "user", message)
        
        # Get recent messages for context
        recent = get_recent_messages(conv_id, limit=20)
        chat_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
        
        # Call LLM
        response = await call_llm(agent, chat_messages)
        
        # Save assistant message
        create_message(conv_id, "assistant", response)
        
        # Update stats
        msg_count = count_conversation_messages(conv_id)
        update_conversation_stats(conv_id, msg_count)
        increment_agent_stats(agent_id)
        
        return {"response": response, "conversation_id": conv_id}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Chat error: {str(e)}")


# === CONVERSATIONS ===

@app.get("/api/agents/{agent_id}/conversations")
async def get_conversations(agent_id: str, user=Depends(get_current_user)):
    """List all conversations for an agent"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        conversations = list_conversations(agent_id)
        
        # Get last message for each conversation
        for conv in conversations:
            messages = get_recent_messages(conv["id"], limit=1)
            conv["last_message"] = messages[-1] if messages else None
        
        return {"conversations": conversations}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to list conversations: {str(e)}")


@app.get("/api/agents/{agent_id}/conversations/{conv_id}")
async def get_conversation(agent_id: str, conv_id: str, user=Depends(get_current_user)):
    """Get conversation messages"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        messages = get_recent_messages(conv_id, limit=100)
        
        return {"conversation_id": conv_id, "messages": messages}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get conversation: {str(e)}")


# === TELEGRAM WEBHOOK ===

@app.post("/api/webhook/telegram/{agent_id}")
async def telegram_webhook(agent_id: str, body: dict = Body(...)):
    """Receive Telegram updates"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or not agent.get("active"):
            return {"ok": True}
        
        channel = get_channel(agent_id, "telegram")
        if not channel or not channel.get("enabled"):
            return {"ok": True}
        
        # Extract message
        msg = body.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        sender_name = msg.get("from", {}).get("first_name", "")
        
        if not text or not chat_id:
            return {"ok": True}
        
        # Get or create conversation
        conversation = get_or_create_conversation(agent_id, "telegram", chat_id, sender_name)
        conv_id = conversation["id"]
        
        # Add user message
        create_message(conv_id, "user", text)
        
        # Get recent messages
        recent = get_recent_messages(conv_id, limit=20)
        chat_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
        
        # Get AI response
        response = await call_llm(agent, chat_messages)
        
        # Save assistant message
        create_message(conv_id, "assistant", response)
        
        # Update stats
        msg_count = count_conversation_messages(conv_id)
        update_conversation_stats(conv_id, msg_count)
        increment_agent_stats(agent_id)
        
        # Send reply via Telegram API
        bot_token = channel.get("config", {}).get("bot_token", "")
        if bot_token:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": int(chat_id), "text": response},
                )
        
        return {"ok": True}
    
    except Exception as e:
        print(f"Telegram webhook error: {e}")
        return {"ok": True}


# === FACEBOOK WEBHOOK ===

@app.get("/api/webhook/facebook/{agent_id}")
async def facebook_verify(agent_id: str, request: Request):
    """Facebook webhook verification"""
    try:
        agent = get_agent(agent_id)
        if not agent:
            raise HTTPException(404)
        
        channel = get_channel(agent_id, "facebook")
        if not channel:
            raise HTTPException(404)
        
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        verify_token = channel.get("config", {}).get("verify_token", "")
        
        if mode == "subscribe" and token == verify_token:
            return int(challenge)
        
        raise HTTPException(403, "Verification failed")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/webhook/facebook/{agent_id}")
async def facebook_webhook(agent_id: str, body: dict = Body(...)):
    """Receive Facebook Messenger messages"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or not agent.get("active"):
            return {"status": "ok"}
        
        channel = get_channel(agent_id, "facebook")
        if not channel or not channel.get("enabled"):
            return {"status": "ok"}
        
        for entry in body.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = str(event.get("sender", {}).get("id", ""))
                text = event.get("message", {}).get("text", "")
                
                if not text or not sender_id:
                    continue
                
                # Get or create conversation
                conversation = get_or_create_conversation(agent_id, "facebook", sender_id)
                conv_id = conversation["id"]
                
                # Add user message
                create_message(conv_id, "user", text)
                
                # Get recent messages
                recent = get_recent_messages(conv_id, limit=20)
                chat_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
                
                # Get AI response
                response = await call_llm(agent, chat_messages)
                
                # Save assistant message
                create_message(conv_id, "assistant", response)
                
                # Update stats
                msg_count = count_conversation_messages(conv_id)
                update_conversation_stats(conv_id, msg_count)
                increment_agent_stats(agent_id)
                
                # Reply via Facebook API
                page_token = channel.get("config", {}).get("page_token", "")
                if page_token:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "https://graph.facebook.com/v18.0/me/messages",
                            params={"access_token": page_token},
                            json={"recipient": {"id": sender_id}, "message": {"text": response}},
                        )
        
        return {"status": "ok"}
    
    except Exception as e:
        print(f"Facebook webhook error: {e}")
        return {"status": "ok"}


# === TELEGRAM BOT SETUP ===

@app.post("/api/agents/{agent_id}/setup-telegram")
async def setup_telegram_webhook(agent_id: str, user=Depends(get_current_user)):
    """Auto-register Telegram webhook for the agent"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        channel = get_channel(agent_id, "telegram")
        if not channel:
            raise HTTPException(400, "Telegram channel not configured")
        
        bot_token = channel.get("config", {}).get("bot_token", "")
        if not bot_token:
            raise HTTPException(400, "Telegram bot token not configured")
        
        server_url = os.getenv("SERVER_URL", "https://YOUR_DOMAIN")
        webhook_url = f"{server_url}/api/webhook/telegram/{agent_id}"
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={"url": webhook_url},
            )
            result = resp.json()
        
        return {
            "status": "ok" if result.get("ok") else "error",
            "webhook_url": webhook_url,
            "telegram_response": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Telegram setup error: {str(e)}")


# === WEBCHAT WIDGET ===

@app.get("/widget.js")
async def widget_js():
    """Serve the webchat widget script"""
    return FileResponse(str(STATIC_DIR / "widget.js"), media_type="application/javascript")


# === STATS ===

@app.get("/api/stats")
async def get_stats_endpoint(user=Depends(get_current_user)):
    """Get overview stats for user"""
    try:
        stats = get_user_stats(user["id"])
        return stats
    except Exception as e:
        raise HTTPException(500, f"Failed to get stats: {str(e)}")


# === HEALTH ===

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    try:
        # Test database connection
        sb = get_supabase()
        result = sb.table("profiles").select("id", count="exact").limit(1).execute()
        
        return {
            "status": "ok",
            "database": "connected",
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "disconnected",
            "error": str(e),
        }


# === DASHBOARD ===

@app.get("/")
async def root():
    """Serve main page"""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/dashboard")
async def dashboard():
    """Serve dashboard"""
    return FileResponse(str(STATIC_DIR / "dashboard.html"))
