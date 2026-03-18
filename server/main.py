"""
AI Agent Platform — Multi-tenant CSKH
Upgraded with Supabase PostgreSQL + JWT Auth + RLS
"""

from fastapi import FastAPI, Body, HTTPException, Header, Depends, Query, Request, BackgroundTasks
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
import json

# Import database helpers
from server.db import (
    get_supabase, get_supabase_anon, get_current_user,
    list_agents, get_agent, create_agent, update_agent, delete_agent, count_user_agents, increment_agent_stats,
    list_channels, get_channel, upsert_channel, delete_channel,
    list_knowledge, create_knowledge, delete_knowledge,
    get_or_create_conversation, list_conversations, update_conversation_stats,
    create_message, get_recent_messages, count_conversation_messages,
    get_user_stats, get_profile,
    # RAG functions
    create_knowledge_chunks, search_knowledge,
    # Brainstorm functions
    get_brainstorm_session, create_brainstorm_session, add_brainstorm_message, finalize_brainstorm,
    # Ticket functions
    list_tickets, get_ticket, create_ticket, update_ticket, get_ticket_stats,
    # Conversation mode & status
    update_conversation_mode, update_conversation_status, get_conversation,
    set_typing_indicator, get_typing_indicator,
    # Facebook comment functions
    create_facebook_comment, get_facebook_comment, list_facebook_comments,
    update_facebook_comment, delete_facebook_comment, get_comment_analytics,
    get_top_commented_posts, get_top_commenters,
)

# Import tool system
from server.tools import get_tool_definitions, execute_tool

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
    """Add knowledge base entry with automatic chunking"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        entry = create_knowledge(agent_id, body)
        
        # Create chunks for RAG
        if entry:
            chunk_count = create_knowledge_chunks(
                entry["id"],
                agent_id,
                entry["content"]
            )
            entry["chunk_count"] = chunk_count
        
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


@app.post("/api/agents/{agent_id}/knowledge/search")
async def search_knowledge_endpoint(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Search knowledge base with RAG"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        query = body.get("query", "")
        limit = body.get("limit", 5)
        
        if not query:
            raise HTTPException(400, "Query required")
        
        results = search_knowledge(agent_id, query, limit)
        
        return {"results": results, "count": len(results)}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to search knowledge: {str(e)}")


# === BRAINSTORM ONBOARDING ===

BRAINSTORM_SYSTEM_PROMPT = """Bạn là trợ lý thiết lập agent AI cho doanh nghiệp. Nhiệm vụ của bạn là hỏi các câu hỏi thông minh để hiểu rõ doanh nghiệp và tạo cấu hình agent tự động.

Hãy hỏi từng câu một, ngắn gọn, thân thiện. Thu thập các thông tin sau:

1. **Loại hình kinh doanh**: Bán gì? Dịch vụ gì? Đối tượng khách hàng?
2. **Giọng điệu**: Formal, casual, hay friendly? Tiếng Việt hay song ngữ?
3. **Giờ làm việc**: Mở cửa lúc mấy giờ? Các ngày nào trong tuần?
4. **Liên hệ**: Email, số điện thoại, địa chỉ?
5. **Câu hỏi thường gặp**: Khách hay hỏi về gì? (giá, giao hàng, bảo hành, đổi trả...)
6. **Chính sách**: Chính sách đổi trả? Bảo hành? Thanh toán?
7. **Escalation**: Làm gì khi không trả lời được? Chuyển cho ai?

Khi user nói "done", "xong", "finish", hoặc bạn cảm thấy đã đủ thông tin (ít nhất 5-6 câu trả lời), hãy tóm tắt lại và hỏi xác nhận.

Bắt đầu bằng cách giới thiệu bản thân và hỏi câu đầu tiên ngay!
"""

@app.post("/api/agents/{agent_id}/brainstorm")
async def brainstorm_chat(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Chat with brainstorm bot to configure agent"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        message = body.get("message", "").strip()
        if not message:
            raise HTTPException(400, "Message required")
        
        # Get or create brainstorm session
        session = get_brainstorm_session(agent_id)
        if not session:
            session = create_brainstorm_session(agent_id)
        
        # Add user message
        add_brainstorm_message(session["id"], "user", message)
        
        # Build conversation for LLM
        messages = session.get("messages", [])
        chat_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        
        # Call LLM using agent's API key
        api_key = agent.get("llm_api_key", "")
        provider = agent.get("llm_provider", "openai")
        model = agent.get("llm_model", "gpt-4o-mini")
        
        if not api_key:
            return {"response": "Vui lòng cấu hình API key cho agent trước."}
        
        # Call LLM
        bot_response = await call_llm_simple(
            provider,
            api_key,
            model,
            BRAINSTORM_SYSTEM_PROMPT,
            chat_messages
        )
        
        # Add assistant message
        add_brainstorm_message(session["id"], "assistant", bot_response)
        
        return {
            "response": bot_response,
            "session_id": session["id"],
            "message_count": len(messages) + 2
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Brainstorm error: {str(e)}")


@app.post("/api/agents/{agent_id}/brainstorm/finalize")
async def finalize_brainstorm_session(agent_id: str, user=Depends(get_current_user)):
    """Finalize brainstorm and generate agent config"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        session = get_brainstorm_session(agent_id)
        if not session:
            raise HTTPException(404, "No active brainstorm session")
        
        # Build conversation
        messages = session.get("messages", [])
        chat_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        
        # Call LLM to generate config
        generation_prompt = """Dựa trên cuộc trò chuyện trên, hãy tạo cấu hình agent theo format JSON sau:

{
  "system_prompt": "Prompt hệ thống chi tiết cho agent (200-300 từ, bao gồm: vai trò, giọng điệu, kiến thức sản phẩm/dịch vụ, chính sách, cách xử lý khi không biết)",
  "faq_entries": [
    {"title": "Câu hỏi", "content": "Câu trả lời", "category": "general"},
    ...
  ],
  "business_profile": {
    "business_type": "Mô tả ngắn",
    "contact": {"email": "", "phone": "", "address": ""},
    "business_hours": {
      "monday": {"open": "09:00", "close": "18:00", "enabled": true},
      "tuesday": {"open": "09:00", "close": "18:00", "enabled": true},
      ...
    },
    "policies": {
      "return": "Chính sách đổi trả",
      "warranty": "Chính sách bảo hành",
      "payment": "Phương thức thanh toán"
    }
  }
}

Trả về ONLY JSON, không có text khác. Đảm bảo system_prompt chi tiết và thực tế."""

        api_key = agent.get("llm_api_key", "")
        provider = agent.get("llm_provider", "openai")
        model = agent.get("llm_model", "gpt-4o-mini")
        
        bot_response = await call_llm_simple(
            provider,
            api_key,
            model,
            "You are a JSON generator. Return only valid JSON.",
            chat_messages + [{"role": "user", "content": generation_prompt}]
        )
        
        # Parse JSON
        import json
        import re
        
        # Extract JSON from response (might have ```json wrapper)
        json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', bot_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = bot_response
        
        generated_config = json.loads(json_str)
        
        # Finalize session
        finalize_brainstorm(session["id"], generated_config)
        
        # Apply config to agent
        update_data = {
            "system_prompt": generated_config.get("system_prompt", ""),
            "business_hours": generated_config.get("business_profile", {}).get("business_hours", {}),
            "brainstorm_completed": True,
        }
        
        update_agent(agent_id, update_data)
        
        # Create FAQ entries
        for faq in generated_config.get("faq_entries", [])[:10]:  # Limit to 10
            create_knowledge(agent_id, faq)
            # Chunk immediately
            kb_entries = list_knowledge(agent_id)
            if kb_entries:
                latest = kb_entries[0]
                create_knowledge_chunks(latest["id"], agent_id, latest["content"])
        
        return {
            "status": "success",
            "config": generated_config
        }
    
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse generated config: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Finalize error: {str(e)}")


@app.get("/api/agents/{agent_id}/brainstorm")
async def get_brainstorm_status(agent_id: str, user=Depends(get_current_user)):
    """Get current brainstorm session"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        session = get_brainstorm_session(agent_id)
        
        if not session:
            return {"session": None, "brainstorm_completed": agent.get("brainstorm_completed", False)}
        
        return {
            "session": session,
            "brainstorm_completed": agent.get("brainstorm_completed", False)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get brainstorm: {str(e)}")


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

async def call_llm_simple(provider: str, api_key: str, model: str, system_prompt: str, messages: list) -> str:
    """Simple LLM call without tools (for brainstorm)"""
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if provider == "openai":
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": full_messages,
                        "max_tokens": 1000,
                        "temperature": 0.7
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
                        "max_tokens": 1000,
                        "system": system_prompt,
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
                        "systemInstruction": {"parts": [{"text": system_prompt}]},
                    },
                )
                data = resp.json()
                return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No response")
            
            else:
                return "Unsupported LLM provider"
    
    except Exception as e:
        return f"Error calling LLM: {str(e)}"


async def run_agent(agent: dict, messages: list, conversation_id: str) -> str:
    """
    Run agent with RAG + Tool support
    This replaces the old call_llm function
    """
    provider = agent.get("llm_provider", "openai")
    api_key = agent.get("llm_api_key", "")
    model = agent.get("llm_model", "gpt-4o-mini")
    settings = agent.get("settings", {})
    tools_enabled = agent.get("tools_enabled", [])
    
    if not api_key:
        return settings.get("fallback_message", "API key chưa được cấu hình.")
    
    # === STEP 1: RAG - Search knowledge base ===
    rag_context = ""
    if messages and "search_knowledge" in tools_enabled:
        last_user_msg = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
        if last_user_msg:
            kb_results = search_knowledge(agent["id"], last_user_msg, limit=3)
            if kb_results:
                rag_items = [f"**{r.get('title', '')}**: {r['content']}" for r in kb_results]
                rag_context = "\n\n---\n**Kiến thức tham khảo:**\n" + "\n\n".join(rag_items)
    
    # Build system prompt with RAG context
    system_msg = agent.get("system_prompt", "Bạn là trợ lý AI.") + rag_context
    
    # === STEP 2: Get tool definitions ===
    tools = get_tool_definitions(provider, tools_enabled) if tools_enabled else []
    
    # === STEP 3: Call LLM with tools (max 3 iterations) ===
    full_messages = messages.copy()
    max_iterations = 3
    
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for iteration in range(max_iterations):
                
                if provider == "openai":
                    # OpenAI function calling
                    payload = {
                        "model": model,
                        "messages": [{"role": "system", "content": system_msg}] + full_messages,
                        "max_tokens": settings.get("max_tokens", 800),
                        "temperature": settings.get("temperature", 0.7)
                    }
                    
                    if tools:
                        payload["tools"] = tools
                        payload["tool_choice"] = "auto"
                    
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                    )
                    data = resp.json()
                    
                    if "error" in data:
                        return f"LLM Error: {data['error'].get('message', 'Unknown error')}"
                    
                    message = data["choices"][0]["message"]
                    
                    # Check if tool calls
                    if message.get("tool_calls"):
                        full_messages.append(message)
                        
                        # Execute tools
                        for tool_call in message["tool_calls"]:
                            tool_name = tool_call["function"]["name"]
                            tool_args = json.loads(tool_call["function"]["arguments"])
                            
                            # Execute tool
                            db_functions = {
                                "search_knowledge": search_knowledge,
                                "create_ticket": create_ticket,
                                "get_supabase": get_supabase,
                            }
                            
                            result = await execute_tool(tool_name, tool_args, agent, conversation_id, db_functions)
                            
                            # Add tool result to conversation
                            full_messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": json.dumps(result, ensure_ascii=False)
                            })
                        
                        continue  # Next iteration
                    else:
                        # No tools, return response
                        return message.get("content", "")
                
                elif provider == "anthropic":
                    # Anthropic tool use
                    payload = {
                        "model": model,
                        "max_tokens": settings.get("max_tokens", 800),
                        "system": system_msg,
                        "messages": full_messages,
                    }
                    
                    if tools:
                        payload["tools"] = tools
                    
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json=payload,
                    )
                    data = resp.json()
                    
                    if "error" in data:
                        return f"LLM Error: {data['error'].get('message', 'Unknown error')}"
                    
                    content = data["content"]
                    
                    # Check if tool use
                    tool_uses = [c for c in content if c.get("type") == "tool_use"]
                    
                    if tool_uses:
                        # Add assistant message with tool_use
                        full_messages.append({"role": "assistant", "content": content})
                        
                        # Execute tools
                        tool_results = []
                        for tool_use in tool_uses:
                            tool_name = tool_use["name"]
                            tool_args = tool_use["input"]
                            
                            db_functions = {
                                "search_knowledge": search_knowledge,
                                "create_ticket": create_ticket,
                                "get_supabase": get_supabase,
                            }
                            
                            result = await execute_tool(tool_name, tool_args, agent, conversation_id, db_functions)
                            
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use["id"],
                                "content": json.dumps(result, ensure_ascii=False)
                            })
                        
                        # Add tool results
                        full_messages.append({"role": "user", "content": tool_results})
                        
                        continue  # Next iteration
                    else:
                        # No tools, return text
                        text_blocks = [c.get("text", "") for c in content if c.get("type") == "text"]
                        return " ".join(text_blocks)
                
                elif provider == "google":
                    # Google Gemini (basic support, tools require more complex setup)
                    # For now, run without tools
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
            
            # Max iterations reached, return last message
            return "Đã đạt giới hạn lượt xử lý. Vui lòng thử lại."
    
    except Exception as e:
        return f"Error running agent: {str(e)}"


# === CHAT / MESSAGE HANDLING ===

async def send_channel_message(agent_id: str, conversation: dict, message: str) -> bool:
    """Send a message to customer via their original channel"""
    channel = conversation["channel"]
    sender_id = conversation["sender_id"]
    
    ch_config = get_channel(agent_id, channel)
    if not ch_config:
        return False
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if channel == "telegram":
                bot_token = ch_config.get("config", {}).get("bot_token", "")
                if not bot_token:
                    return False
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": sender_id, "text": message},
                )
                return resp.json().get("ok", False)
            
            elif channel == "facebook":
                page_token = ch_config.get("config", {}).get("page_token", "")
                if not page_token:
                    return False
                resp = await client.post(
                    "https://graph.facebook.com/v18.0/me/messages",
                    params={"access_token": page_token},
                    json={"recipient": {"id": sender_id}, "message": {"text": message}},
                )
                return "message_id" in resp.json()
            
            elif channel == "zalo":
                access_token = ch_config.get("config", {}).get("access_token", "")
                if not access_token:
                    return False
                resp = await client.post(
                    "https://openapi.zalo.me/v3.0/oa/message/cs",
                    headers={"access_token": access_token},
                    json={
                        "recipient": {"user_id": sender_id},
                        "message": {"text": message}
                    },
                )
                return resp.json().get("error") == 0
            
            elif channel == "webchat":
                # For webchat, message is stored and widget will poll for it
                return True
        
        return True
    
    except Exception as e:
        print(f"Channel message send error: {e}")
        return False


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
        
        # Check conversation mode
        conv_mode = conversation.get("mode", "ai")
        
        # Add user message
        create_message(conv_id, "user", message)
        
        # Only auto-reply if mode is 'ai'
        if conv_mode == "ai":
            # Get recent messages for context
            recent = get_recent_messages(conv_id, limit=20)
            chat_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
            
            # Run agent with RAG + Tools
            response = await run_agent(agent, chat_messages, conv_id)
            
            # Save assistant message (AI-generated)
            create_message(conv_id, "assistant", response, metadata={"manual": False})
            
            # Update stats
            msg_count = count_conversation_messages(conv_id)
            update_conversation_stats(conv_id, msg_count)
            increment_agent_stats(agent_id)
            
            return {"response": response, "conversation_id": conv_id}
        
        elif conv_mode == "manual":
            # Manual mode: no AI response, staff will reply
            msg_count = count_conversation_messages(conv_id)
            update_conversation_stats(conv_id, msg_count)
            return {
                "response": None,
                "conversation_id": conv_id,
                "message": "Tin nhắn đã được gửi. Nhân viên sẽ trả lời sớm.",
                "mode": "manual"
            }
        
        elif conv_mode == "hybrid":
            # Hybrid mode: generate AI draft but don't send
            recent = get_recent_messages(conv_id, limit=20)
            chat_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
            
            draft = await run_agent(agent, chat_messages, conv_id)
            
            msg_count = count_conversation_messages(conv_id)
            update_conversation_stats(conv_id, msg_count)
            
            return {
                "response": None,
                "conversation_id": conv_id,
                "draft": draft,
                "mode": "hybrid",
                "message": "AI đã tạo bản nháp. Nhân viên sẽ xem xét và gửi."
            }
    
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
async def get_conversation_messages(agent_id: str, conv_id: str, user=Depends(get_current_user)):
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


# === LIVE CHAT - MANUAL REPLY ===

@app.post("/api/agents/{agent_id}/conversations/{conv_id}/reply")
async def send_manual_reply(agent_id: str, conv_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Send manual reply from staff to customer"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        conversation = get_conversation(conv_id)
        if not conversation or conversation["agent_id"] != agent_id:
            raise HTTPException(404, "Conversation not found")
        
        message = body.get("message", "").strip()
        if not message:
            raise HTTPException(400, "Message required")
        
        staff_name = user.get("name", "Staff")
        
        # Save manual reply message
        create_message(
            conv_id, 
            "assistant", 
            message, 
            metadata={"manual": True, "staff_name": staff_name}
        )
        
        # Send via channel
        sent = await send_channel_message(agent_id, conversation, message)
        
        if not sent:
            # Still save locally even if send failed
            pass
        
        # Update stats
        msg_count = count_conversation_messages(conv_id)
        update_conversation_stats(conv_id, msg_count)
        
        # Set status to active if it was waiting
        if conversation.get("status") == "waiting":
            update_conversation_status(conv_id, "active")
        
        # Clear typing indicator
        set_typing_indicator(conv_id, False)
        
        return {
            "status": "sent" if sent else "saved_locally",
            "message": message,
            "staff_name": staff_name
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to send reply: {str(e)}")


@app.put("/api/agents/{agent_id}/conversations/{conv_id}/mode")
async def change_conversation_mode(agent_id: str, conv_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Toggle conversation mode: ai/manual/hybrid"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        conversation = get_conversation(conv_id)
        if not conversation or conversation["agent_id"] != agent_id:
            raise HTTPException(404, "Conversation not found")
        
        mode = body.get("mode", "ai")
        if mode not in ["ai", "manual", "hybrid"]:
            raise HTTPException(400, "Invalid mode. Must be: ai, manual, or hybrid")
        
        updated = update_conversation_mode(conv_id, mode)
        
        return {"status": "updated", "mode": mode, "conversation": updated}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to update mode: {str(e)}")


@app.put("/api/agents/{agent_id}/conversations/{conv_id}/status")
async def change_conversation_status(agent_id: str, conv_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Update conversation status: active/waiting/resolved/closed"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        conversation = get_conversation(conv_id)
        if not conversation or conversation["agent_id"] != agent_id:
            raise HTTPException(404, "Conversation not found")
        
        status = body.get("status", "active")
        if status not in ["active", "waiting", "resolved", "closed"]:
            raise HTTPException(400, "Invalid status")
        
        updated = update_conversation_status(conv_id, status)
        
        return {"status": "updated", "conversation_status": status, "conversation": updated}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to update status: {str(e)}")


@app.post("/api/agents/{agent_id}/conversations/{conv_id}/handback")
async def handback_to_ai(agent_id: str, conv_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Return conversation to AI after staff resolution"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        conversation = get_conversation(conv_id)
        if not conversation or conversation["agent_id"] != agent_id:
            raise HTTPException(404, "Conversation not found")
        
        context_note = body.get("note", "")
        
        # Set mode back to AI
        update_conversation_mode(conv_id, "ai")
        update_conversation_status(conv_id, "resolved")
        
        # Optionally add context note for AI
        if context_note:
            create_message(
                conv_id,
                "system",
                f"[Staff note: {context_note}]",
                metadata={"type": "handback_note"}
            )
        
        return {"status": "handed_back", "mode": "ai", "conversation_status": "resolved"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to hand back: {str(e)}")


# === TEST CHAT ===

@app.post("/api/agents/{agent_id}/test-chat")
async def test_agent_chat(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Test chat with agent from dashboard (no conversation persistence)"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        message = body.get("message", "").strip()
        history = body.get("history", [])  # [{"role": "user", "content": "..."}, ...]
        
        if not message:
            raise HTTPException(400, "Message required")
        
        # Build chat messages
        chat_messages = history + [{"role": "user", "content": message}]
        
        # Run agent (use "test" as conv_id for logging/tools)
        response = await run_agent(agent, chat_messages, conv_id="test")
        
        return {
            "response": response,
            "message": message,
            "test": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Test chat error: {str(e)}")


# === TYPING INDICATORS ===

@app.post("/api/agents/{agent_id}/conversations/{conv_id}/typing")
async def set_typing(agent_id: str, conv_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Signal that staff is typing"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        is_typing = body.get("is_typing", True)
        staff_name = user.get("name", "Staff")
        
        set_typing_indicator(conv_id, is_typing, staff_name)
        
        return {"status": "ok", "is_typing": is_typing}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to set typing: {str(e)}")


@app.get("/api/agents/{agent_id}/conversations/{conv_id}/typing")
async def get_typing(agent_id: str, conv_id: str):
    """Check if agent/staff is typing (public endpoint for widget)"""
    try:
        indicator = get_typing_indicator(conv_id)
        
        if indicator and indicator.get("is_typing"):
            return {
                "is_typing": True,
                "staff_name": indicator.get("staff_name", "Agent")
            }
        
        return {"is_typing": False}
    
    except Exception as e:
        return {"is_typing": False}


# === WEBCHAT - NEW MESSAGES POLLING ===

@app.get("/api/agents/{agent_id}/conversations/{conv_id}/new-messages")
async def poll_new_messages(
    agent_id: str,
    conv_id: str,
    after: Optional[str] = Query(None)
):
    """Widget polls for new messages (staff replies) - Public endpoint"""
    try:
        # Get messages after timestamp
        sb = get_supabase()
        query = sb.table("messages").select("*").eq("conversation_id", conv_id).order("created_at", desc=False)
        
        if after:
            query = query.gt("created_at", after)
        
        result = query.limit(50).execute()
        messages = result.data or []
        
        # Filter to only assistant messages (replies from staff/AI)
        new_replies = [m for m in messages if m["role"] == "assistant"]
        
        return {"messages": new_replies, "count": len(new_replies)}
    
    except Exception as e:
        raise HTTPException(500, f"Failed to poll messages: {str(e)}")


# === TICKETS ===

@app.get("/api/agents/{agent_id}/tickets")
async def get_tickets_endpoint(
    agent_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    user=Depends(get_current_user)
):
    """List tickets for an agent"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        tickets = list_tickets(agent_id, status, priority)
        
        return {"tickets": tickets, "count": len(tickets)}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to list tickets: {str(e)}")


@app.put("/api/agents/{agent_id}/tickets/{ticket_id}")
async def update_ticket_endpoint(
    agent_id: str,
    ticket_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user)
):
    """Update ticket status or details"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        ticket = get_ticket(ticket_id)
        if not ticket or ticket["agent_id"] != agent_id:
            raise HTTPException(404, "Ticket not found")
        
        # Only allow updating specific fields
        updatable = ["status", "priority", "category", "assigned_to", "tags"]
        update_data = {k: v for k, v in body.items() if k in updatable}
        
        if update_data:
            updated = update_ticket(ticket_id, update_data)
            return {"status": "updated", "ticket": updated}
        
        return {"status": "no changes"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to update ticket: {str(e)}")


@app.get("/api/agents/{agent_id}/tickets/stats")
async def get_ticket_stats_endpoint(agent_id: str, user=Depends(get_current_user)):
    """Get ticket statistics"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        stats = get_ticket_stats(agent_id)
        
        return stats
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get ticket stats: {str(e)}")


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
        
        # Get AI response with RAG + Tools
        response = await run_agent(agent, chat_messages, conv_id)
        
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
    """Receive Facebook Messenger messages AND post comments"""
    try:
        agent = get_agent(agent_id)
        
        if not agent or not agent.get("active"):
            return {"status": "ok"}
        
        channel = get_channel(agent_id, "facebook")
        if not channel or not channel.get("enabled"):
            return {"status": "ok"}
        
        for entry in body.get("entry", []):
            # Handle Page messages (existing)
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
                
                # Get AI response with RAG + Tools
                response = await run_agent(agent, chat_messages, conv_id)
                
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
            
            # Handle Post comments (NEW)
            for change in entry.get("changes", []):
                if change.get("field") == "feed":
                    value = change.get("value", {})
                    item = value.get("item")
                    verb = value.get("verb")
                    
                    if item == "comment" and verb in ("add", "edited"):
                        comment_id = value.get("comment_id")
                        post_id = value.get("post_id")
                        sender_id = str(value.get("from", {}).get("id", ""))
                        sender_name = value.get("from", {}).get("name", "")
                        message = value.get("message", "")
                        parent_id = value.get("parent_id")
                        
                        if not message or not sender_id or not comment_id:
                            continue
                        
                        # Don't reply to own comments (page's comments)
                        page_id = post_id.split("_")[0] if "_" in post_id else ""
                        if sender_id == page_id:
                            continue
                        
                        # Process comment with AI agent
                        await handle_facebook_comment(
                            agent_id, post_id, comment_id,
                            sender_id, sender_name, message,
                            parent_id, channel
                        )
        
        return {"status": "ok"}
    
    except Exception as e:
        print(f"Facebook webhook error: {e}")
        return {"status": "ok"}


async def handle_facebook_comment(
    agent_id: str,
    post_id: str,
    comment_id: str,
    sender_id: str,
    sender_name: str,
    message: str,
    parent_comment_id: Optional[str],
    channel: dict
):
    """Handle Facebook comment - AI reply + optional inbox"""
    try:
        agent = get_agent(agent_id)
        page_token = channel.get("config", {}).get("page_token", "")
        
        if not page_token:
            return
        
        # Check if comment already exists (deduplication)
        existing = get_facebook_comment(comment_id)
        if existing:
            return
        
        # Get comment settings from agent
        comment_settings = agent.get("settings", {}).get("facebook_comments", {})
        auto_reply = comment_settings.get("auto_reply", True)
        auto_inbox = comment_settings.get("auto_inbox", False)
        reply_delay = comment_settings.get("reply_delay_seconds", 30)
        
        # Detect comment intent
        intent, keywords = detect_comment_intent(message, comment_settings)
        sentiment = detect_sentiment(message)
        
        # Create comment record
        create_facebook_comment(
            agent_id, post_id, comment_id,
            sender_id, sender_name, message,
            parent_comment_id,
            metadata={"intent": intent, "keywords": keywords}
        )
        
        # Auto-hide spam
        if intent == "SPAM" and comment_settings.get("auto_hide_spam", False):
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://graph.facebook.com/v18.0/{comment_id}",
                    params={"access_token": page_token},
                    json={"is_hidden": True}
                )
            
            update_facebook_comment(comment_id, {
                "is_hidden": True,
                "is_spam": True,
                "sentiment": "negative"
            })
            return
        
        # Don't auto-reply if disabled
        if not auto_reply:
            update_facebook_comment(comment_id, {"sentiment": sentiment})
            return
        
        # Get or create conversation for this commenter
        conversation = get_or_create_conversation(
            agent_id, "facebook_comment", sender_id, sender_name
        )
        conv_id = conversation["id"]
        
        # Add user message with context
        context_msg = f"[Comment on post {post_id}]\n{message}"
        create_message(conv_id, "user", context_msg, metadata={
            "comment_id": comment_id,
            "post_id": post_id,
            "type": "comment",
            "intent": intent
        })
        
        # Get recent messages for context
        recent = get_recent_messages(conv_id, limit=10)
        chat_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
        
        # Add system context about comment intent
        if intent in ("PRICE_INQUIRY", "STOCK_CHECK", "ORDER_INTENT"):
            chat_messages.insert(0, {
                "role": "system",
                "content": f"Customer is asking about {intent.lower().replace('_', ' ')}. Provide helpful, concise answer."
            })
        
        # Delay to look natural
        if reply_delay > 0:
            await asyncio.sleep(reply_delay)
        
        # Run AI agent to get response
        response = await run_agent(agent, chat_messages, conv_id)
        
        # Save response
        create_message(conv_id, "assistant", response, metadata={"type": "comment_reply"})
        
        # Reply to the comment on Facebook
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://graph.facebook.com/v18.0/{comment_id}/comments",
                params={"access_token": page_token},
                json={"message": response}
            )
        
        # Update comment with AI reply
        update_facebook_comment(comment_id, {
            "ai_reply": response,
            "ai_replied_at": datetime.utcnow().isoformat(),
            "sentiment": sentiment
        })
        
        # Send private message (inbox) for certain intents
        should_inbox = auto_inbox and intent in ("PRICE_INQUIRY", "ORDER_INTENT", "INBOX_REQUEST")
        
        if should_inbox:
            inbox_msg = comment_settings.get("inbox_message", 
                "Cảm ơn bạn đã quan tâm! Để tư vấn chi tiết hơn, mình xin phép inbox bạn nhé.")
            
            try:
                # Use private_replies API
                await client.post(
                    f"https://graph.facebook.com/v18.0/{comment_id}/private_replies",
                    params={"access_token": page_token},
                    json={"message": f"{inbox_msg}\n\n{response}"}
                )
            except Exception as e:
                print(f"Failed to send private reply: {e}")
        
        # Auto-like positive comments
        if sentiment == "positive" and comment_settings.get("auto_like_positive", False):
            try:
                await client.post(
                    f"https://graph.facebook.com/v18.0/{comment_id}/likes",
                    params={"access_token": page_token}
                )
                update_facebook_comment(comment_id, {"is_liked": True})
            except Exception as e:
                print(f"Failed to like comment: {e}")
        
        # Update stats
        increment_agent_stats(agent_id)
    
    except Exception as e:
        print(f"Error handling Facebook comment: {e}")


def detect_comment_intent(message: str, settings: dict) -> tuple:
    """Detect intent from comment text (Vietnamese + English)"""
    msg_lower = message.lower()
    
    # Get custom keywords from settings
    inbox_keywords = settings.get("inbox_trigger_keywords", [
        "giá", "bao nhiêu", "inbox", "pm", "ib", "giá bao nhiêu", "price"
    ])
    blacklist = settings.get("blacklist_keywords", ["lừa đảo", "scam", "fake"])
    
    # Check blacklist first (spam)
    for word in blacklist:
        if word.lower() in msg_lower:
            return ("SPAM", [word])
    
    # Price inquiry
    price_keywords = ["giá", "bao nhiêu", "giá bao nhiêu", "bao nhiêu tiền", "price", "cost", "얼마"]
    if any(kw in msg_lower for kw in price_keywords):
        return ("PRICE_INQUIRY", [kw for kw in price_keywords if kw in msg_lower])
    
    # Stock check
    stock_keywords = ["còn hàng", "còn không", "còn size", "có màu", "available", "in stock"]
    if any(kw in msg_lower for kw in stock_keywords):
        return ("STOCK_CHECK", [kw for kw in stock_keywords if kw in msg_lower])
    
    # Inbox request
    if any(kw in msg_lower for kw in inbox_keywords):
        return ("INBOX_REQUEST", [kw for kw in inbox_keywords if kw in msg_lower])
    
    # Order intent
    order_keywords = ["đặt hàng", "mua", "order", "buy", "muốn mua", "chốt đơn"]
    if any(kw in msg_lower for kw in order_keywords):
        return ("ORDER_INTENT", [kw for kw in order_keywords if kw in msg_lower])
    
    # General question
    question_keywords = ["?", "không", "sao", "thế nào", "how", "what", "why"]
    if any(kw in msg_lower for kw in question_keywords):
        return ("QUESTION", [])
    
    return ("GENERAL", [])


def detect_sentiment(message: str) -> str:
    """Detect sentiment: positive/neutral/negative (simple heuristic)"""
    msg_lower = message.lower()
    
    positive_words = ["tuyệt", "đẹp", "ok", "good", "great", "love", "nice", "👍", "❤️", "😍", "🥰"]
    negative_words = ["tệ", "dở", "bad", "poor", "fake", "lừa đảo", "scam", "👎", "😡", "💩"]
    
    pos_count = sum(1 for word in positive_words if word in msg_lower)
    neg_count = sum(1 for word in negative_words if word in msg_lower)
    
    if neg_count > pos_count:
        return "negative"
    elif pos_count > neg_count:
        return "positive"
    else:
        return "neutral"


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


# === ZALO OA WEBHOOK ===

@app.post("/api/webhook/zalo/{agent_id}")
async def zalo_webhook(agent_id: str, body: dict = Body(...)):
    """Receive Zalo OA webhook events"""
    try:
        event_name = body.get("event_name", "")
        
        if event_name == "user_send_text":
            sender_id = body.get("sender", {}).get("id", "")
            message_text = body.get("message", {}).get("text", "")
            
            if not sender_id or not message_text:
                return {"status": "ok"}
            
            # Get agent
            agent = get_agent(agent_id)
            if not agent:
                return {"status": "ok"}
            
            # Get Zalo channel config
            channel = get_channel(agent_id, "zalo")
            if not channel:
                return {"status": "ok"}
            
            access_token = channel.get("config", {}).get("access_token", "")
            oa_id = channel.get("config", {}).get("oa_id", "")
            
            if not access_token:
                return {"status": "ok"}
            
            # Create or get conversation
            conv_id = get_or_create_conversation(
                agent_id=agent_id,
                channel="zalo",
                sender_id=sender_id,
                sender_name=body.get("sender", {}).get("name", f"Zalo User {sender_id[:8]}")
            )
            
            # Save user message
            create_message(conv_id, "user", message_text, {"zalo_sender": sender_id})
            
            # Get conversation context
            history = get_recent_messages(conv_id, limit=10)
            context_messages = [{"role": m["role"], "content": m["content"]} for m in history]
            
            # Call LLM
            from anthropic import Anthropic
            anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            
            system_prompt = agent.get("system_prompt", "")
            tools = get_tool_definitions(agent_id) if agent.get("tools_enabled") else None
            
            llm_messages = context_messages + [{"role": "user", "content": message_text}]
            
            llm_response = anthropic.messages.create(
                model=agent.get("model", "claude-3-5-sonnet-20241022"),
                max_tokens=2048,
                system=system_prompt,
                messages=llm_messages,
                tools=tools or [],
            )
            
            # Process response
            response_text = ""
            for block in llm_response.content:
                if block.type == "text":
                    response_text += block.text
                elif block.type == "tool_use" and tools:
                    tool_result = await execute_tool(agent_id, block.name, block.input)
                    response_text += f"\n[{block.name}: {tool_result.get('summary', 'Done')}]"
            
            if not response_text:
                response_text = "Xin lỗi, tôi không hiểu yêu cầu của bạn."
            
            # Save assistant message
            create_message(conv_id, "assistant", response_text, {"model": agent.get("model")})
            
            # Update stats
            msg_count = count_conversation_messages(conv_id)
            update_conversation_stats(conv_id, msg_count)
            increment_agent_stats(agent_id)
            
            # Reply via Zalo API
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://openapi.zalo.me/v3.0/oa/message/cs",
                    headers={"access_token": access_token},
                    json={
                        "recipient": {"user_id": sender_id},
                        "message": {"text": response_text}
                    },
                )
        
        return {"status": "ok"}
    
    except Exception as e:
        print(f"Zalo webhook error: {e}")
        return {"status": "ok"}


# === WEBCHAT WIDGET ===

@app.get("/widget.js")
async def widget_js():
    """Serve the webchat widget script"""
    return FileResponse(str(STATIC_DIR / "widget.js"), media_type="application/javascript")


@app.get("/api/widget/{agent_id}/info")
async def widget_info(agent_id: str):
    """Get agent info for widget (public endpoint)"""
    try:
        agent = get_agent(agent_id)
        if not agent:
            raise HTTPException(404, "Agent not found")
        
        settings = agent.get("settings", {})
        
        return {
            "name": agent.get("name", "AI Assistant"),
            "avatar": settings.get("avatar"),
            "emoji": settings.get("emoji", "🤖"),
            "welcome_message": settings.get("welcome_message", "Xin chào! Tôi có thể giúp gì cho bạn?"),
            "quick_replies": settings.get("quick_replies", []),
            "status": "online" if agent.get("is_active", True) else "offline"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/widget/{agent_id}/upload")
async def widget_upload(agent_id: str, request: Request):
    """Handle file uploads from widget"""
    try:
        form = await request.form()
        file = form.get("file")
        sender_id = form.get("sender_id")
        
        if not file or not sender_id:
            raise HTTPException(400, "Missing file or sender_id")
        
        # Store file (simplified - in production use S3/storage)
        filename = f"upload_{agent_id}_{sender_id}_{file.filename}"
        # For now, just acknowledge
        
        return {
            "status": "ok",
            "reply": f"Đã nhận file: {file.filename}"
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# === NOTIFICATIONS ===

@app.get("/api/notifications")
async def get_notifications(user=Depends(get_current_user), limit: int = 20):
    """Get recent notifications for user"""
    try:
        sb = get_supabase()
        result = sb.table("notifications")\
            .select("*")\
            .eq("user_id", user["id"])\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        
        return result.data
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/notifications/unread")
async def get_unread_count(user=Depends(get_current_user)):
    """Get unread notification count"""
    try:
        sb = get_supabase()
        result = sb.table("notifications")\
            .select("id", count="exact")\
            .eq("user_id", user["id"])\
            .eq("is_read", False)\
            .execute()
        
        return {"count": result.count or 0}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user=Depends(get_current_user)):
    """Mark notification as read"""
    try:
        sb = get_supabase()
        sb.table("notifications")\
            .update({"is_read": True})\
            .eq("id", notification_id)\
            .eq("user_id", user["id"])\
            .execute()
        
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


# === SAVED REPLIES ===

@app.get("/api/agents/{agent_id}/replies")
async def get_saved_replies(agent_id: str, user=Depends(get_current_user)):
    """Get saved replies for agent"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        settings = agent.get("settings", {})
        return settings.get("saved_replies", [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/agents/{agent_id}/replies")
async def create_saved_reply(agent_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Add a saved reply"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        settings = agent.get("settings", {})
        saved_replies = settings.get("saved_replies", [])
        
        new_reply = {
            "id": str(uuid.uuid4()),
            "title": body.get("title", ""),
            "content": body.get("content", ""),
            "shortcut": body.get("shortcut", ""),
            "created_at": datetime.utcnow().isoformat()
        }
        
        saved_replies.append(new_reply)
        settings["saved_replies"] = saved_replies
        
        update_agent(agent_id, {"settings": settings})
        
        return new_reply
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/agents/{agent_id}/replies/{reply_id}")
async def delete_saved_reply(agent_id: str, reply_id: str, user=Depends(get_current_user)):
    """Delete a saved reply"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        settings = agent.get("settings", {})
        saved_replies = settings.get("saved_replies", [])
        
        saved_replies = [r for r in saved_replies if r.get("id") != reply_id]
        settings["saved_replies"] = saved_replies
        
        update_agent(agent_id, {"settings": settings})
        
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# === CUSTOMER MANAGEMENT ===

@app.get("/api/agents/{agent_id}/customers")
async def get_customers(agent_id: str, user=Depends(get_current_user), search: str = ""):
    """Get unique customers for agent"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        
        query = sb.table("conversations")\
            .select("sender_id, sender_name, channel, created_at, metadata")\
            .eq("agent_id", agent_id)
        
        if search:
            query = query.ilike("sender_name", f"%{search}%")
        
        result = query.order("created_at", desc=True).execute()
        
        # Group by sender_id
        customers = {}
        for conv in result.data:
            sid = conv["sender_id"]
            if sid not in customers:
                # Count conversations and messages
                conv_count = sb.table("conversations")\
                    .select("id", count="exact")\
                    .eq("agent_id", agent_id)\
                    .eq("sender_id", sid)\
                    .execute()
                
                msg_count = sb.table("messages")\
                    .select("id", count="exact")\
                    .eq("conversation_id", conv["id"])\
                    .execute()
                
                customers[sid] = {
                    "sender_id": sid,
                    "name": conv["sender_name"],
                    "channels": [conv["channel"]],
                    "total_conversations": conv_count.count or 0,
                    "total_messages": msg_count.count or 0,
                    "first_seen": conv["created_at"],
                    "metadata": conv.get("metadata", {})
                }
            else:
                if conv["channel"] not in customers[sid]["channels"]:
                    customers[sid]["channels"].append(conv["channel"])
        
        return list(customers.values())
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/agents/{agent_id}/customers/{sender_id}")
async def get_customer_detail(agent_id: str, sender_id: str, user=Depends(get_current_user)):
    """Get customer detail with all conversations"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        
        # Get all conversations for this customer
        convs = sb.table("conversations")\
            .select("*")\
            .eq("agent_id", agent_id)\
            .eq("sender_id", sender_id)\
            .order("created_at", desc=True)\
            .execute()
        
        if not convs.data:
            raise HTTPException(404, "Customer not found")
        
        return {
            "sender_id": sender_id,
            "name": convs.data[0]["sender_name"],
            "conversations": convs.data,
            "metadata": convs.data[0].get("metadata", {})
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/agents/{agent_id}/customers/{sender_id}")
async def update_customer(agent_id: str, sender_id: str, body: dict = Body(...), user=Depends(get_current_user)):
    """Update customer info"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        
        # Update all conversations for this sender
        updates = {}
        if "name" in body:
            updates["sender_name"] = body["name"]
        if "metadata" in body:
            updates["metadata"] = body["metadata"]
        
        if updates:
            sb.table("conversations")\
                .update(updates)\
                .eq("agent_id", agent_id)\
                .eq("sender_id", sender_id)\
                .execute()
        
        return {"status": "ok"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# === AGENT ANALYTICS ===

@app.get("/api/agents/{agent_id}/analytics")
async def get_agent_analytics(agent_id: str, user=Depends(get_current_user)):
    """Get analytics for agent"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        
        # Messages per day (last 7 days)
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        convs = sb.table("conversations")\
            .select("id, created_at")\
            .eq("agent_id", agent_id)\
            .gte("created_at", seven_days_ago)\
            .execute()
        
        messages_by_day = {}
        for conv in convs.data:
            msgs = sb.table("messages")\
                .select("created_at")\
                .eq("conversation_id", conv["id"])\
                .gte("created_at", seven_days_ago)\
                .execute()
            
            for msg in msgs.data:
                day = msg["created_at"][:10]
                messages_by_day[day] = messages_by_day.get(day, 0) + 1
        
        # Channel breakdown
        channel_stats = {}
        all_convs = sb.table("conversations")\
            .select("channel")\
            .eq("agent_id", agent_id)\
            .execute()
        
        for conv in all_convs.data:
            ch = conv["channel"]
            channel_stats[ch] = channel_stats.get(ch, 0) + 1
        
        # Response time average (simplified)
        response_time_avg = "< 1s"
        
        # Top queries (simplified - would need NLP clustering in production)
        top_queries = ["Giờ làm việc", "Giá sản phẩm", "Chính sách đổi trả"]
        
        return {
            "messages_per_day": messages_by_day,
            "response_time_avg": response_time_avg,
            "top_queries": top_queries,
            "channel_breakdown": channel_stats,
            "total_conversations": len(all_convs.data),
            "total_messages": agent.get("stats", {}).get("total_messages", 0)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# === FACEBOOK COMMENT MANAGEMENT ===

@app.get("/api/agents/{agent_id}/comments")
async def list_comments(
    agent_id: str,
    replied: Optional[bool] = Query(None),
    is_spam: Optional[bool] = Query(None),
    is_hidden: Optional[bool] = Query(None),
    sentiment: Optional[str] = Query(None),
    post_id: Optional[str] = Query(None),
    sender_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """List Facebook comments for an agent"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        filters = {}
        if replied is not None:
            filters["replied"] = replied
        if is_spam is not None:
            filters["is_spam"] = is_spam
        if is_hidden is not None:
            filters["is_hidden"] = is_hidden
        if sentiment:
            filters["sentiment"] = sentiment
        if post_id:
            filters["post_id"] = post_id
        if sender_id:
            filters["sender_id"] = sender_id
        
        comments = list_facebook_comments(agent_id, filters, limit, offset)
        
        return {
            "comments": comments,
            "total": len(comments),
            "limit": limit,
            "offset": offset
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/agents/{agent_id}/comments/{comment_id}/reply")
async def reply_to_comment(
    agent_id: str,
    comment_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user)
):
    """Manually reply to a Facebook comment"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        comment = get_facebook_comment(comment_id)
        if not comment or comment["agent_id"] != agent_id:
            raise HTTPException(404, "Comment not found")
        
        reply_text = body.get("message", "").strip()
        if not reply_text:
            raise HTTPException(400, "Message is required")
        
        # Get channel config
        channel = get_channel(agent_id, "facebook")
        if not channel:
            raise HTTPException(400, "Facebook channel not configured")
        
        page_token = channel.get("config", {}).get("page_token", "")
        if not page_token:
            raise HTTPException(400, "Facebook page token not found")
        
        # Reply on Facebook
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{comment_id}/comments",
                params={"access_token": page_token},
                json={"message": reply_text}
            )
            
            if response.status_code != 200:
                raise HTTPException(500, "Failed to reply on Facebook")
        
        # Update comment record
        update_facebook_comment(comment_id, {
            "ai_reply": reply_text,
            "ai_replied_at": datetime.utcnow().isoformat()
        })
        
        return {"success": True, "message": "Reply sent"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/agents/{agent_id}/comments/{comment_id}/hide")
async def hide_comment(
    agent_id: str,
    comment_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user)
):
    """Hide a Facebook comment"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        comment = get_facebook_comment(comment_id)
        if not comment or comment["agent_id"] != agent_id:
            raise HTTPException(404, "Comment not found")
        
        is_hidden = body.get("is_hidden", True)
        
        # Get channel config
        channel = get_channel(agent_id, "facebook")
        if not channel:
            raise HTTPException(400, "Facebook channel not configured")
        
        page_token = channel.get("config", {}).get("page_token", "")
        if not page_token:
            raise HTTPException(400, "Facebook page token not found")
        
        # Hide/unhide on Facebook
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{comment_id}",
                params={"access_token": page_token},
                json={"is_hidden": is_hidden}
            )
            
            if response.status_code not in (200, 204):
                raise HTTPException(500, "Failed to hide comment on Facebook")
        
        # Update comment record
        update_facebook_comment(comment_id, {"is_hidden": is_hidden})
        
        return {"success": True, "is_hidden": is_hidden}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/agents/{agent_id}/comments/{comment_id}/like")
async def like_comment(
    agent_id: str,
    comment_id: str,
    user=Depends(get_current_user)
):
    """Like a Facebook comment"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        comment = get_facebook_comment(comment_id)
        if not comment or comment["agent_id"] != agent_id:
            raise HTTPException(404, "Comment not found")
        
        # Get channel config
        channel = get_channel(agent_id, "facebook")
        if not channel:
            raise HTTPException(400, "Facebook channel not configured")
        
        page_token = channel.get("config", {}).get("page_token", "")
        if not page_token:
            raise HTTPException(400, "Facebook page token not found")
        
        # Like on Facebook
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{comment_id}/likes",
                params={"access_token": page_token}
            )
            
            if response.status_code not in (200, 204):
                raise HTTPException(500, "Failed to like comment on Facebook")
        
        # Update comment record
        update_facebook_comment(comment_id, {"is_liked": True})
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/agents/{agent_id}/comments/{comment_id}")
async def delete_comment_endpoint(
    agent_id: str,
    comment_id: str,
    user=Depends(get_current_user)
):
    """Delete a Facebook comment"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        comment = get_facebook_comment(comment_id)
        if not comment or comment["agent_id"] != agent_id:
            raise HTTPException(404, "Comment not found")
        
        # Get channel config
        channel = get_channel(agent_id, "facebook")
        if not channel:
            raise HTTPException(400, "Facebook channel not configured")
        
        page_token = channel.get("config", {}).get("page_token", "")
        if not page_token:
            raise HTTPException(400, "Facebook page token not found")
        
        # Delete on Facebook
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"https://graph.facebook.com/v18.0/{comment_id}",
                params={"access_token": page_token}
            )
            
            if response.status_code not in (200, 204):
                raise HTTPException(500, "Failed to delete comment on Facebook")
        
        # Delete from database
        delete_facebook_comment(comment_id)
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/agents/{agent_id}/comments/{comment_id}/spam")
async def mark_spam(
    agent_id: str,
    comment_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user)
):
    """Mark comment as spam"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        comment = get_facebook_comment(comment_id)
        if not comment or comment["agent_id"] != agent_id:
            raise HTTPException(404, "Comment not found")
        
        is_spam = body.get("is_spam", True)
        
        # Update comment record
        update_facebook_comment(comment_id, {
            "is_spam": is_spam,
            "sentiment": "negative" if is_spam else comment.get("sentiment", "neutral")
        })
        
        return {"success": True, "is_spam": is_spam}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/agents/{agent_id}/comments/analytics")
async def comment_analytics(
    agent_id: str,
    days: int = Query(7, ge=1, le=90),
    user=Depends(get_current_user)
):
    """Get comment analytics for an agent"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        analytics = get_comment_analytics(agent_id, days)
        top_posts = get_top_commented_posts(agent_id, limit=10)
        top_commenters = get_top_commenters(agent_id, limit=10)
        
        return {
            "analytics": analytics,
            "top_posts": top_posts,
            "top_commenters": top_commenters,
            "period_days": days
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# === POSTS ===

@app.post("/api/agents/{agent_id}/posts")
async def create_post(
    agent_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user)
):
    """Create and optionally schedule a Facebook/Zalo post"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        content = body.get("content")
        if not content:
            raise HTTPException(400, "Content is required")
        
        image_url = body.get("image_url")
        scheduled_at = body.get("scheduled_at")
        channel = body.get("channel", "facebook")
        status = body.get("status", "draft")
        
        if channel not in ["facebook", "zalo"]:
            raise HTTPException(400, "Invalid channel")
        
        if status not in ["draft", "scheduled", "published"]:
            raise HTTPException(400, "Invalid status")
        
        sb = get_supabase()
        post_data = {
            "agent_id": agent_id,
            "channel": channel,
            "content": content,
            "image_url": image_url,
            "status": status,
            "scheduled_at": scheduled_at,
        }
        
        result = sb.table("posts").insert(post_data).execute()
        
        if not result.data:
            raise HTTPException(500, "Failed to create post")
        
        return result.data[0]
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/agents/{agent_id}/posts")
async def list_posts(
    agent_id: str,
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user)
):
    """List all posts for an agent"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        query = sb.table("posts").select("*").eq("agent_id", agent_id)
        
        if status:
            query = query.eq("status", status)
        
        query = query.order("created_at", desc=True).limit(limit)
        result = query.execute()
        
        return result.data
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/agents/{agent_id}/posts/{post_id}")
async def get_post(
    agent_id: str,
    post_id: str,
    user=Depends(get_current_user)
):
    """Get a specific post"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        result = sb.table("posts").select("*").eq("id", post_id).eq("agent_id", agent_id).execute()
        
        if not result.data:
            raise HTTPException(404, "Post not found")
        
        return result.data[0]
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/agents/{agent_id}/posts/{post_id}")
async def update_post(
    agent_id: str,
    post_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user)
):
    """Update a draft/scheduled post"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        # Only allow updating draft/scheduled posts
        sb = get_supabase()
        check = sb.table("posts").select("status").eq("id", post_id).eq("agent_id", agent_id).execute()
        
        if not check.data:
            raise HTTPException(404, "Post not found")
        
        if check.data[0]["status"] not in ["draft", "scheduled"]:
            raise HTTPException(400, "Can only update draft or scheduled posts")
        
        update_data = {}
        if "content" in body:
            update_data["content"] = body["content"]
        if "image_url" in body:
            update_data["image_url"] = body["image_url"]
        if "scheduled_at" in body:
            update_data["scheduled_at"] = body["scheduled_at"]
        if "status" in body:
            update_data["status"] = body["status"]
        if "channel" in body:
            update_data["channel"] = body["channel"]
        
        result = sb.table("posts").update(update_data).eq("id", post_id).execute()
        
        if not result.data:
            raise HTTPException(500, "Failed to update post")
        
        return result.data[0]
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/agents/{agent_id}/posts/{post_id}")
async def delete_post(
    agent_id: str,
    post_id: str,
    user=Depends(get_current_user)
):
    """Delete a draft/scheduled post"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        # Only allow deleting draft/scheduled posts
        sb = get_supabase()
        check = sb.table("posts").select("status").eq("id", post_id).eq("agent_id", agent_id).execute()
        
        if not check.data:
            raise HTTPException(404, "Post not found")
        
        if check.data[0]["status"] == "published":
            raise HTTPException(400, "Cannot delete published posts")
        
        sb.table("posts").delete().eq("id", post_id).execute()
        
        return {"success": True}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/agents/{agent_id}/posts/{post_id}/publish")
async def publish_post(
    agent_id: str,
    post_id: str,
    user=Depends(get_current_user)
):
    """Publish a post immediately to Facebook/Zalo"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        post = sb.table("posts").select("*").eq("id", post_id).eq("agent_id", agent_id).execute()
        
        if not post.data:
            raise HTTPException(404, "Post not found")
        
        post_data = post.data[0]
        
        if post_data["status"] == "published":
            raise HTTPException(400, "Post already published")
        
        # Get agent's Facebook credentials
        fb_settings = agent.get("settings", {}).get("facebook", {})
        page_access_token = fb_settings.get("page_access_token")
        page_id = fb_settings.get("page_id")
        
        if not page_access_token or not page_id:
            raise HTTPException(400, "Facebook credentials not configured")
        
        # Publish to Facebook
        import httpx
        
        graph_url = f"https://graph.facebook.com/v18.0/{page_id}/feed"
        
        payload = {
            "message": post_data["content"],
            "access_token": page_access_token
        }
        
        if post_data.get("image_url"):
            # Use photo endpoint if image is provided
            graph_url = f"https://graph.facebook.com/v18.0/{page_id}/photos"
            payload["url"] = post_data["image_url"]
            payload["caption"] = post_data["content"]
            del payload["message"]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(graph_url, data=payload)
            
            if response.status_code != 200:
                error_msg = response.json().get("error", {}).get("message", "Unknown error")
                raise HTTPException(500, f"Facebook API error: {error_msg}")
            
            fb_response = response.json()
            external_post_id = fb_response.get("id") or fb_response.get("post_id")
        
        # Update post status
        update_data = {
            "status": "published",
            "published_at": "now()",
            "external_post_id": external_post_id
        }
        
        result = sb.table("posts").update(update_data).eq("id", post_id).execute()
        
        return result.data[0]
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/agents/{agent_id}/posts/generate")
async def generate_post_content(
    agent_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user)
):
    """AI generates post content based on prompt"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        prompt = body.get("prompt")
        if not prompt:
            raise HTTPException(400, "Prompt is required")
        
        post_type = body.get("type", "general")
        
        # Get agent's LLM settings
        llm_config = agent.get("llm_config", {})
        api_key = llm_config.get("api_key")
        model = llm_config.get("model", "gpt-4o-mini")
        base_url = llm_config.get("base_url", "https://api.openai.com/v1")
        
        if not api_key:
            raise HTTPException(400, "LLM API key not configured for this agent")
        
        # Build system prompt based on type
        type_prompts = {
            "promotion": "Bạn là chuyên gia viết content quảng cáo. Hãy tạo bài viết quảng cáo hấp dẫn, thu hút và có CTA rõ ràng.",
            "announcement": "Bạn là chuyên gia viết thông báo. Hãy tạo thông báo chuyên nghiệp, rõ ràng và dễ hiểu.",
            "engagement": "Bạn là chuyên gia viết content tương tác. Hãy tạo bài viết thú vị, khuyến khích người xem tương tác (like, comment, share).",
            "general": "Bạn là chuyên gia viết content mạng xã hội. Hãy tạo bài viết phù hợp với yêu cầu."
        }
        
        system_prompt = type_prompts.get(post_type, type_prompts["general"])
        system_prompt += "\n\nHãy tạo 2-3 phiên bản khác nhau của bài viết. Mỗi phiên bản ngăn cách bởi '---'."
        
        # Call LLM
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.9,
                    "max_tokens": 500
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise HTTPException(500, f"LLM API error: {response.text}")
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Split into variations
            variations = [v.strip() for v in content.split("---") if v.strip()]
            
            return {"variations": variations}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# === BROADCAST ===

@app.post("/api/agents/{agent_id}/broadcast")
async def send_broadcast(
    agent_id: str,
    body: dict = Body(...),
    user=Depends(get_current_user),
    background_tasks: BackgroundTasks
):
    """Send message to multiple customers"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        message = body.get("message")
        if not message:
            raise HTTPException(400, "Message is required")
        
        channel_filter = body.get("channel_filter", "all")
        tag_filter = body.get("tag_filter", [])
        limit = body.get("limit", 100)
        
        # Create broadcast record
        sb = get_supabase()
        broadcast_data = {
            "agent_id": agent_id,
            "message": message,
            "channel_filter": channel_filter,
            "tag_filter": tag_filter,
            "status": "pending"
        }
        
        result = sb.table("broadcasts").insert(broadcast_data).execute()
        broadcast = result.data[0]
        broadcast_id = broadcast["id"]
        
        # Queue the broadcast for background processing
        background_tasks.add_task(process_broadcast, broadcast_id, agent_id, message, channel_filter, tag_filter, limit)
        
        return broadcast
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


async def process_broadcast(broadcast_id: str, agent_id: str, message: str, channel_filter: str, tag_filter: list, limit: int):
    """Background task to process broadcast"""
    import asyncio
    
    try:
        sb = get_supabase()
        
        # Update status to sending
        sb.table("broadcasts").update({"status": "sending"}).eq("id", broadcast_id).execute()
        
        # Get customers
        query = sb.table("customers").select("*").eq("agent_id", agent_id)
        
        if channel_filter != "all":
            query = query.eq("channel", channel_filter)
        
        if tag_filter:
            query = query.contains("tags", tag_filter)
        
        query = query.limit(limit)
        customers_result = query.execute()
        customers = customers_result.data
        
        sent_count = 0
        failed_count = 0
        skipped_count = 0
        
        for customer in customers:
            try:
                channel = customer.get("channel")
                customer_id = customer.get("external_id")
                
                if not customer_id:
                    skipped_count += 1
                    continue
                
                # Send message based on channel
                if channel == "telegram":
                    # Send via Telegram
                    import os
                    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
                    if bot_token:
                        import httpx
                        async with httpx.AsyncClient() as client:
                            await client.post(
                                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                json={"chat_id": customer_id, "text": message}
                            )
                        sent_count += 1
                    else:
                        skipped_count += 1
                
                elif channel == "facebook":
                    # Send via Facebook Messenger - requires page access token
                    agent = get_agent(agent_id)
                    fb_settings = agent.get("settings", {}).get("facebook", {})
                    page_access_token = fb_settings.get("page_access_token")
                    
                    if page_access_token:
                        import httpx
                        async with httpx.AsyncClient() as client:
                            await client.post(
                                "https://graph.facebook.com/v18.0/me/messages",
                                params={"access_token": page_access_token},
                                json={
                                    "recipient": {"id": customer_id},
                                    "message": {"text": message}
                                }
                            )
                        sent_count += 1
                    else:
                        skipped_count += 1
                
                else:
                    skipped_count += 1
                
                # Rate limiting: 1 msg/sec
                await asyncio.sleep(1)
            
            except Exception:
                failed_count += 1
                continue
        
        # Update broadcast status
        sb.table("broadcasts").update({
            "status": "completed",
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "completed_at": "now()"
        }).eq("id", broadcast_id).execute()
    
    except Exception as e:
        # Update to failed status
        sb = get_supabase()
        sb.table("broadcasts").update({"status": "failed"}).eq("id", broadcast_id).execute()


@app.get("/api/agents/{agent_id}/broadcast/history")
async def broadcast_history(
    agent_id: str,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user)
):
    """List past broadcasts"""
    try:
        agent = get_agent(agent_id)
        if not agent or agent["user_id"] != user["id"]:
            raise HTTPException(404, "Agent not found")
        
        sb = get_supabase()
        result = sb.table("broadcasts").select("*").eq("agent_id", agent_id).order("created_at", desc=True).limit(limit).execute()
        
        return result.data
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


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
