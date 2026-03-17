"""
Database helper module for Supabase PostgreSQL
Provides clean separation of DB operations
"""

import os
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from jose import jwt, JWTError
from fastapi import HTTPException, Header
from datetime import datetime

# Singleton clients
_supabase_service: Optional[Client] = None
_supabase_anon: Optional[Client] = None

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


def get_supabase() -> Client:
    """Get Supabase client with service_role key (for backend operations)"""
    global _supabase_service
    if _supabase_service is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment")
        _supabase_service = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase_service


def get_supabase_anon() -> Client:
    """Get Supabase client with anon key (for auth operations)"""
    global _supabase_anon
    if _supabase_anon is None:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment")
        _supabase_anon = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _supabase_anon


def verify_jwt(token: str) -> Dict[str, Any]:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


def get_current_user(authorization: str = Header(None)) -> Dict[str, Any]:
    """Extract and verify user from Authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")
    
    token = authorization.split(" ")[1]
    payload = verify_jwt(token)
    user_id = payload.get("sub")
    
    if not user_id:
        raise HTTPException(401, "Invalid token payload")
    
    # Get user profile
    sb = get_supabase()
    result = sb.table("profiles").select("*").eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(404, "User profile not found")
    
    return result.data[0]


# === PROFILE OPERATIONS ===

def get_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile by ID"""
    sb = get_supabase()
    result = sb.table("profiles").select("*").eq("id", user_id).execute()
    return result.data[0] if result.data else None


# === AGENT OPERATIONS ===

def list_agents(user_id: str) -> List[Dict[str, Any]]:
    """List all agents for a user"""
    sb = get_supabase()
    result = sb.table("agents").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return result.data


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """Get agent by ID (no auth check - use for webhooks)"""
    sb = get_supabase()
    result = sb.table("agents").select("*").eq("id", agent_id).execute()
    return result.data[0] if result.data else None


def create_agent(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new agent"""
    sb = get_supabase()
    agent_data = {
        "user_id": user_id,
        "name": data.get("name", "My Agent"),
        "description": data.get("description", ""),
        "system_prompt": data.get("system_prompt", "Bạn là trợ lý AI chăm sóc khách hàng. Trả lời thân thiện, chính xác, ngắn gọn."),
        "llm_provider": data.get("llm_provider", "openai"),
        "llm_model": data.get("llm_model", "gpt-4o-mini"),
        "llm_api_key": data.get("llm_api_key", ""),
        "settings": data.get("settings", {
            "language": "vi",
            "max_tokens": 500,
            "temperature": 0.7,
            "fallback_message": "Xin lỗi, tôi không hiểu câu hỏi. Vui lòng liên hệ nhân viên hỗ trợ."
        }),
        "active": True,
    }
    result = sb.table("agents").insert(agent_data).execute()
    return result.data[0] if result.data else None


def update_agent(agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update an agent"""
    sb = get_supabase()
    result = sb.table("agents").update(data).eq("id", agent_id).execute()
    return result.data[0] if result.data else None


def delete_agent(agent_id: str):
    """Delete an agent"""
    sb = get_supabase()
    sb.table("agents").delete().eq("id", agent_id).execute()


def count_user_agents(user_id: str) -> int:
    """Count agents for a user"""
    sb = get_supabase()
    result = sb.table("agents").select("id", count="exact").eq("user_id", user_id).execute()
    return result.count or 0


def increment_agent_stats(agent_id: str):
    """Increment agent message stats"""
    sb = get_supabase()
    agent = get_agent(agent_id)
    if agent:
        sb.table("agents").update({
            "messages_total": (agent.get("messages_total") or 0) + 1,
            "last_message_at": datetime.utcnow().isoformat(),
        }).eq("id", agent_id).execute()


# === CHANNEL OPERATIONS ===

def list_channels(agent_id: str) -> List[Dict[str, Any]]:
    """List all channels for an agent"""
    sb = get_supabase()
    result = sb.table("channels").select("*").eq("agent_id", agent_id).execute()
    return result.data


def get_channel(agent_id: str, channel_type: str) -> Optional[Dict[str, Any]]:
    """Get a specific channel"""
    sb = get_supabase()
    result = sb.table("channels").select("*").eq("agent_id", agent_id).eq("type", channel_type).execute()
    return result.data[0] if result.data else None


def upsert_channel(agent_id: str, channel_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a channel"""
    sb = get_supabase()
    channel_data = {
        "agent_id": agent_id,
        "type": channel_type,
        "config": config,
        "enabled": True,
        "connected_at": datetime.utcnow().isoformat(),
    }
    result = sb.table("channels").upsert(channel_data, on_conflict="agent_id,type").execute()
    return result.data[0] if result.data else None


def delete_channel(agent_id: str, channel_type: str):
    """Delete a channel"""
    sb = get_supabase()
    sb.table("channels").delete().eq("agent_id", agent_id).eq("type", channel_type).execute()


# === KNOWLEDGE BASE OPERATIONS ===

def list_knowledge(agent_id: str) -> List[Dict[str, Any]]:
    """List knowledge base entries for an agent"""
    sb = get_supabase()
    result = sb.table("knowledge_base").select("*").eq("agent_id", agent_id).order("created_at", desc=True).execute()
    return result.data


def create_knowledge(agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a knowledge base entry"""
    sb = get_supabase()
    kb_data = {
        "agent_id": agent_id,
        "title": data.get("title", ""),
        "content": data.get("content", ""),
        "category": data.get("category", "general"),
    }
    result = sb.table("knowledge_base").insert(kb_data).execute()
    return result.data[0] if result.data else None


def delete_knowledge(entry_id: str):
    """Delete a knowledge base entry"""
    sb = get_supabase()
    sb.table("knowledge_base").delete().eq("id", entry_id).execute()


# === CONVERSATION OPERATIONS ===

def get_or_create_conversation(agent_id: str, channel: str, sender_id: str, sender_name: str = "") -> Dict[str, Any]:
    """Get existing conversation or create new one"""
    sb = get_supabase()
    
    # Try to get existing
    result = sb.table("conversations").select("*").eq("agent_id", agent_id).eq("channel", channel).eq("sender_id", sender_id).execute()
    
    if result.data:
        return result.data[0]
    
    # Create new
    conv_data = {
        "agent_id": agent_id,
        "channel": channel,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_count": 0,
    }
    result = sb.table("conversations").insert(conv_data).execute()
    return result.data[0] if result.data else None


def list_conversations(agent_id: str) -> List[Dict[str, Any]]:
    """List all conversations for an agent with last message"""
    sb = get_supabase()
    result = sb.table("conversations").select("*").eq("agent_id", agent_id).order("last_message_at", desc=True).execute()
    return result.data


def update_conversation_stats(conversation_id: str, message_count: int):
    """Update conversation message count and last_message_at"""
    sb = get_supabase()
    sb.table("conversations").update({
        "message_count": message_count,
        "last_message_at": datetime.utcnow().isoformat(),
    }).eq("id", conversation_id).execute()


# === MESSAGE OPERATIONS ===

def create_message(conversation_id: str, role: str, content: str) -> Dict[str, Any]:
    """Create a message in a conversation"""
    sb = get_supabase()
    msg_data = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }
    result = sb.table("messages").insert(msg_data).execute()
    return result.data[0] if result.data else None


def get_recent_messages(conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent messages from a conversation"""
    sb = get_supabase()
    result = sb.table("messages").select("*").eq("conversation_id", conversation_id).order("created_at", desc=False).limit(limit).execute()
    return result.data


def count_conversation_messages(conversation_id: str) -> int:
    """Count messages in a conversation"""
    sb = get_supabase()
    result = sb.table("messages").select("id", count="exact").eq("conversation_id", conversation_id).execute()
    return result.count or 0


# === STATS ===

def get_user_stats(user_id: str) -> Dict[str, Any]:
    """Get overview stats for a user"""
    sb = get_supabase()
    
    # Count agents
    agents_result = sb.table("agents").select("id", count="exact").eq("user_id", user_id).execute()
    agent_count = agents_result.count or 0
    
    # Get agent IDs
    agents = sb.table("agents").select("id, messages_total").eq("user_id", user_id).execute()
    agent_ids = [a["id"] for a in agents.data] if agents.data else []
    
    # Count conversations
    conv_count = 0
    total_messages = 0
    
    if agent_ids:
        conv_result = sb.table("conversations").select("id", count="exact").in_("agent_id", agent_ids).execute()
        conv_count = conv_result.count or 0
        
        # Sum messages from agents
        total_messages = sum(a.get("messages_total", 0) for a in agents.data)
    
    # Get user plan
    profile = get_profile(user_id)
    plan = profile.get("plan", "free") if profile else "free"
    
    return {
        "agents": agent_count,
        "conversations": conv_count,
        "messages": total_messages,
        "plan": plan,
    }
