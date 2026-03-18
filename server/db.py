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
    """Verify JWT token via Supabase REST API (ES256 compatible)"""
    import httpx as _httpx
    try:
        r = _httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return {"sub": data["id"], "email": data.get("email", "")}
        raise HTTPException(401, "Invalid or expired token")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(401, f"Token verification failed: {str(e)}")


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


# === CONVERSATION MODE & STATUS OPERATIONS ===

def update_conversation_mode(conv_id: str, mode: str) -> Optional[Dict[str, Any]]:
    """Update conversation mode (ai/manual/hybrid)"""
    sb = get_supabase()
    result = sb.table("conversations").update({"mode": mode}).eq("id", conv_id).execute()
    return result.data[0] if result.data else None


def update_conversation_status(conv_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Update conversation status (active/waiting/resolved/closed)"""
    sb = get_supabase()
    result = sb.table("conversations").update({"status": status}).eq("id", conv_id).execute()
    return result.data[0] if result.data else None


def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    """Get single conversation by ID"""
    sb = get_supabase()
    result = sb.table("conversations").select("*").eq("id", conv_id).execute()
    return result.data[0] if result.data else None


def set_typing_indicator(conv_id: str, is_typing: bool, staff_name: str = "") -> bool:
    """Set or clear typing indicator for a conversation"""
    sb = get_supabase()
    try:
        sb.table("typing_indicators").upsert({
            "conversation_id": conv_id,
            "is_typing": is_typing,
            "staff_name": staff_name if is_typing else None,
        }).execute()
        return True
    except Exception:
        return False


def get_typing_indicator(conv_id: str) -> Optional[Dict[str, Any]]:
    """Get typing indicator status"""
    sb = get_supabase()
    result = sb.table("typing_indicators").select("*").eq("conversation_id", conv_id).execute()
    if result.data:
        indicator = result.data[0]
        # Clear if older than 10 seconds
        from datetime import datetime, timedelta
        if indicator["is_typing"]:
            updated_at = datetime.fromisoformat(indicator["updated_at"].replace("Z", "+00:00"))
            if datetime.now(updated_at.tzinfo) - updated_at > timedelta(seconds=10):
                set_typing_indicator(conv_id, False)
                return {"is_typing": False, "staff_name": None}
        return indicator
    return None


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

def create_message(conversation_id: str, role: str, content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create a message in a conversation with optional metadata"""
    sb = get_supabase()
    msg_data = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
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


# === KNOWLEDGE CHUNKS (RAG) ===

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks"""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings near the chunk boundary
            for punct in ['. ', '! ', '? ', '\n\n', '\n']:
                last_punct = text.rfind(punct, start, end)
                if last_punct != -1:
                    end = last_punct + len(punct)
                    break
        
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    
    return chunks


def create_knowledge_chunks(knowledge_id: str, agent_id: str, content: str):
    """Create chunks for a knowledge base entry"""
    sb = get_supabase()
    
    # Delete old chunks
    sb.table("knowledge_chunks").delete().eq("knowledge_id", knowledge_id).execute()
    
    # Create new chunks
    chunks = chunk_text(content)
    chunk_data = [
        {
            "knowledge_id": knowledge_id,
            "agent_id": agent_id,
            "content": chunk,
            "chunk_index": i,
        }
        for i, chunk in enumerate(chunks)
    ]
    
    if chunk_data:
        sb.table("knowledge_chunks").insert(chunk_data).execute()
    
    # Update chunk count
    sb.table("knowledge_base").update({"chunk_count": len(chunks)}).eq("id", knowledge_id).execute()
    
    return len(chunks)


def search_knowledge(agent_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search knowledge base using PostgreSQL full-text search"""
    sb = get_supabase()
    
    try:
        # Try full-text search with to_tsquery
        # Note: Supabase client doesn't support textSearchQuery directly, so we use rpc or raw query
        # For now, use ILIKE fallback (production should use stored procedure)
        
        # Fallback to ILIKE keyword matching
        keywords = query.split()[:5]  # Limit to 5 keywords
        
        results = []
        seen_knowledge_ids = set()
        
        for keyword in keywords:
            if len(keyword) < 2:
                continue
            
            chunk_results = sb.table("knowledge_chunks") \
                .select("id, knowledge_id, content, chunk_index") \
                .eq("agent_id", agent_id) \
                .ilike("content", f"%{keyword}%") \
                .limit(limit) \
                .execute()
            
            for chunk in chunk_results.data:
                kid = chunk["knowledge_id"]
                if kid not in seen_knowledge_ids:
                    # Get knowledge entry title
                    kb_entry = sb.table("knowledge_base").select("title, category").eq("id", kid).execute()
                    if kb_entry.data:
                        chunk["title"] = kb_entry.data[0].get("title", "")
                        chunk["category"] = kb_entry.data[0].get("category", "")
                        results.append(chunk)
                        seen_knowledge_ids.add(kid)
                        
                        if len(results) >= limit:
                            break
            
            if len(results) >= limit:
                break
        
        return results[:limit]
    
    except Exception as e:
        print(f"Knowledge search error: {e}")
        return []


# === BRAINSTORM SESSIONS ===

def get_brainstorm_session(agent_id: str) -> Optional[Dict[str, Any]]:
    """Get active brainstorm session for agent"""
    sb = get_supabase()
    result = sb.table("brainstorm_sessions") \
        .select("*") \
        .eq("agent_id", agent_id) \
        .eq("status", "active") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    return result.data[0] if result.data else None


def create_brainstorm_session(agent_id: str) -> Dict[str, Any]:
    """Create a new brainstorm session"""
    sb = get_supabase()
    session_data = {
        "agent_id": agent_id,
        "messages": [],
        "status": "active",
    }
    result = sb.table("brainstorm_sessions").insert(session_data).execute()
    return result.data[0] if result.data else None


def add_brainstorm_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    """Add message to brainstorm session"""
    sb = get_supabase()
    
    # Get current session
    session = sb.table("brainstorm_sessions").select("*").eq("id", session_id).execute()
    if not session.data:
        return None
    
    messages = session.data[0].get("messages", [])
    messages.append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    result = sb.table("brainstorm_sessions").update({"messages": messages}).eq("id", session_id).execute()
    return result.data[0] if result.data else None


def finalize_brainstorm(session_id: str, generated_config: Dict[str, Any]) -> Dict[str, Any]:
    """Finalize brainstorm session with generated config"""
    sb = get_supabase()
    result = sb.table("brainstorm_sessions").update({
        "status": "finalized",
        "generated_config": generated_config,
    }).eq("id", session_id).execute()
    return result.data[0] if result.data else None


# === TICKETS ===

def list_tickets(agent_id: str, status: Optional[str] = None, priority: Optional[str] = None) -> List[Dict[str, Any]]:
    """List tickets for an agent with optional filters"""
    sb = get_supabase()
    query = sb.table("tickets").select("*").eq("agent_id", agent_id)
    
    if status:
        query = query.eq("status", status)
    if priority:
        query = query.eq("priority", priority)
    
    result = query.order("created_at", desc=True).execute()
    return result.data


def get_ticket(ticket_id: str) -> Optional[Dict[str, Any]]:
    """Get ticket by ID"""
    sb = get_supabase()
    result = sb.table("tickets").select("*").eq("id", ticket_id).execute()
    return result.data[0] if result.data else None


def create_ticket(agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a support ticket"""
    sb = get_supabase()
    ticket_data = {
        "agent_id": agent_id,
        "conversation_id": data.get("conversation_id"),
        "customer_name": data.get("customer_name"),
        "customer_phone": data.get("customer_phone"),
        "customer_email": data.get("customer_email"),
        "subject": data.get("subject", "Support Request"),
        "description": data.get("description", ""),
        "priority": data.get("priority", "medium"),
        "category": data.get("category", "general"),
        "tags": data.get("tags", []),
    }
    result = sb.table("tickets").insert(ticket_data).execute()
    return result.data[0] if result.data else None


def update_ticket(ticket_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update ticket"""
    sb = get_supabase()
    
    # Auto-set resolved_at if status is resolved/closed
    if data.get("status") in ("resolved", "closed"):
        ticket = get_ticket(ticket_id)
        if ticket and not ticket.get("resolved_at"):
            data["resolved_at"] = datetime.utcnow().isoformat()
    
    result = sb.table("tickets").update(data).eq("id", ticket_id).execute()
    return result.data[0] if result.data else None


def get_ticket_stats(agent_id: str) -> Dict[str, Any]:
    """Get ticket statistics for agent"""
    sb = get_supabase()
    
    tickets = list_tickets(agent_id)
    
    stats = {
        "total": len(tickets),
        "open": sum(1 for t in tickets if t["status"] == "open"),
        "in_progress": sum(1 for t in tickets if t["status"] == "in_progress"),
        "resolved": sum(1 for t in tickets if t["status"] == "resolved"),
        "closed": sum(1 for t in tickets if t["status"] == "closed"),
        "by_priority": {
            "low": sum(1 for t in tickets if t["priority"] == "low"),
            "medium": sum(1 for t in tickets if t["priority"] == "medium"),
            "high": sum(1 for t in tickets if t["priority"] == "high"),
            "urgent": sum(1 for t in tickets if t["priority"] == "urgent"),
        }
    }
    
    # Calculate average resolution time
    resolved_tickets = [t for t in tickets if t.get("resolved_at")]
    if resolved_tickets:
        total_seconds = 0
        for ticket in resolved_tickets:
            created = datetime.fromisoformat(ticket["created_at"].replace("Z", "+00:00"))
            resolved = datetime.fromisoformat(ticket["resolved_at"].replace("Z", "+00:00"))
            total_seconds += (resolved - created).total_seconds()
        
        avg_hours = (total_seconds / len(resolved_tickets)) / 3600
        stats["avg_resolution_hours"] = round(avg_hours, 1)
    else:
        stats["avg_resolution_hours"] = 0
    
    return stats


# === FACEBOOK COMMENT OPERATIONS ===

def create_facebook_comment(
    agent_id: str,
    post_id: str,
    comment_id: str,
    sender_id: str,
    sender_name: str,
    message: str,
    parent_comment_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a new Facebook comment record"""
    sb = get_supabase()
    
    data = {
        "agent_id": agent_id,
        "post_id": post_id,
        "comment_id": comment_id,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message": message,
        "parent_comment_id": parent_comment_id,
        "metadata": metadata or {}
    }
    
    result = sb.table("facebook_comments").insert(data).execute()
    return result.data[0] if result.data else None


def get_facebook_comment(comment_id: str) -> Optional[Dict[str, Any]]:
    """Get a Facebook comment by comment_id"""
    sb = get_supabase()
    result = sb.table("facebook_comments").select("*").eq("comment_id", comment_id).execute()
    return result.data[0] if result.data else None


def list_facebook_comments(
    agent_id: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """List Facebook comments with optional filters"""
    sb = get_supabase()
    
    query = sb.table("facebook_comments").select("*").eq("agent_id", agent_id)
    
    if filters:
        if filters.get("post_id"):
            query = query.eq("post_id", filters["post_id"])
        
        if filters.get("replied") is True:
            query = query.is_("ai_replied_at", "not.null")
        elif filters.get("replied") is False:
            query = query.is_("ai_replied_at", "null")
        
        if filters.get("is_spam") is not None:
            query = query.eq("is_spam", filters["is_spam"])
        
        if filters.get("is_hidden") is not None:
            query = query.eq("is_hidden", filters["is_hidden"])
        
        if filters.get("sentiment"):
            query = query.eq("sentiment", filters["sentiment"])
        
        if filters.get("sender_id"):
            query = query.eq("sender_id", filters["sender_id"])
    
    query = query.order("created_at", desc=True).limit(limit).offset(offset)
    
    result = query.execute()
    return result.data


def update_facebook_comment(comment_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update a Facebook comment"""
    sb = get_supabase()
    result = sb.table("facebook_comments").update(data).eq("comment_id", comment_id).execute()
    return result.data[0] if result.data else None


def delete_facebook_comment(comment_id: str) -> bool:
    """Delete a Facebook comment"""
    sb = get_supabase()
    result = sb.table("facebook_comments").delete().eq("comment_id", comment_id).execute()
    return bool(result.data)


def get_comment_analytics(agent_id: str, days: int = 7) -> Dict[str, Any]:
    """Get comment analytics for an agent"""
    sb = get_supabase()
    
    try:
        result = sb.rpc("get_comment_analytics", {
            "p_agent_id": agent_id,
            "p_days": days
        }).execute()
        
        return result.data if result.data else {}
    except Exception:
        # Fallback if function doesn't exist yet
        comments = list_facebook_comments(agent_id, limit=1000)
        
        total = len(comments)
        replied = sum(1 for c in comments if c.get("ai_replied_at"))
        
        return {
            "total_comments": total,
            "replied_count": replied,
            "unreplied_count": total - replied,
            "reply_rate": round(100.0 * replied / total, 2) if total > 0 else 0,
            "spam_count": sum(1 for c in comments if c.get("is_spam")),
            "positive_count": sum(1 for c in comments if c.get("sentiment") == "positive"),
            "neutral_count": sum(1 for c in comments if c.get("sentiment") == "neutral"),
            "negative_count": sum(1 for c in comments if c.get("sentiment") == "negative"),
        }


def get_top_commented_posts(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get top posts by comment count"""
    sb = get_supabase()
    
    comments = list_facebook_comments(agent_id, limit=1000)
    
    # Group by post_id
    post_counts = {}
    for comment in comments:
        post_id = comment["post_id"]
        if post_id not in post_counts:
            post_counts[post_id] = {
                "post_id": post_id,
                "comment_count": 0,
                "latest_comment": comment["message"]
            }
        post_counts[post_id]["comment_count"] += 1
    
    # Sort and return top
    sorted_posts = sorted(post_counts.values(), key=lambda x: x["comment_count"], reverse=True)
    return sorted_posts[:limit]


def get_top_commenters(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get most active commenters"""
    sb = get_supabase()
    
    comments = list_facebook_comments(agent_id, limit=1000)
    
    # Group by sender_id
    commenter_counts = {}
    for comment in comments:
        sender_id = comment["sender_id"]
        if sender_id not in commenter_counts:
            commenter_counts[sender_id] = {
                "sender_id": sender_id,
                "sender_name": comment["sender_name"],
                "comment_count": 0
            }
        commenter_counts[sender_id]["comment_count"] += 1
    
    # Sort and return top
    sorted_commenters = sorted(commenter_counts.values(), key=lambda x: x["comment_count"], reverse=True)
    return sorted_commenters[:limit]
