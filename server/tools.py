"""
CSKH Tool System for ClawDesk
Provides function calling tools for OpenAI, Anthropic, and Google
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json


# === TOOL DEFINITIONS ===

def get_tool_definitions(provider: str, tools_enabled: List[str]) -> List[Dict[str, Any]]:
    """
    Get tool definitions in the format required by each LLM provider
    provider: 'openai', 'anthropic', or 'google'
    tools_enabled: list of tool names to include
    """
    
    # Base tool schemas
    all_tools = {
        "search_knowledge": {
            "name": "search_knowledge",
            "description": "Tìm kiếm thông tin trong cơ sở kiến thức của công ty. Sử dụng khi khách hàng hỏi về sản phẩm, chính sách, hoặc thông tin doanh nghiệp.",
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "Từ khóa hoặc câu hỏi cần tìm kiếm",
                    "required": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Số lượng kết quả tối đa (mặc định: 5)",
                    "required": False
                }
            }
        },
        
        "escalate_to_human": {
            "name": "escalate_to_human",
            "description": "Chuyển hội thoại cho nhân viên hỗ trợ khi không thể giải quyết hoặc khách hàng yêu cầu nói chuyện với người thật. Gửi thông báo đến kênh escalation đã cấu hình.",
            "parameters": {
                "reason": {
                    "type": "string",
                    "description": "Lý do cần chuyển cho người (ví dụ: 'Khách hàng yêu cầu hoàn tiền', 'Vấn đề kỹ thuật phức tạp')",
                    "required": True
                },
                "priority": {
                    "type": "string",
                    "description": "Mức độ ưu tiên: 'low', 'medium', 'high', 'urgent'",
                    "required": False
                }
            }
        },
        
        "collect_customer_info": {
            "name": "collect_customer_info",
            "description": "Thu thập và lưu thông tin khách hàng một cách có cấu trúc (tên, số điện thoại, email). Sử dụng khi khách hàng cung cấp thông tin liên hệ.",
            "parameters": {
                "name": {
                    "type": "string",
                    "description": "Tên khách hàng",
                    "required": False
                },
                "phone": {
                    "type": "string",
                    "description": "Số điện thoại",
                    "required": False
                },
                "email": {
                    "type": "string",
                    "description": "Địa chỉ email",
                    "required": False
                },
                "notes": {
                    "type": "string",
                    "description": "Ghi chú thêm về khách hàng",
                    "required": False
                }
            }
        },
        
        "create_ticket": {
            "name": "create_ticket",
            "description": "Tạo ticket hỗ trợ để theo dõi vấn đề của khách hàng. Sử dụng khi cần ghi lại yêu cầu hỗ trợ, khiếu nại, hoặc báo lỗi.",
            "parameters": {
                "subject": {
                    "type": "string",
                    "description": "Tiêu đề ticket (tóm tắt vấn đề)",
                    "required": True
                },
                "description": {
                    "type": "string",
                    "description": "Mô tả chi tiết vấn đề",
                    "required": True
                },
                "priority": {
                    "type": "string",
                    "description": "Mức độ ưu tiên: 'low', 'medium', 'high', 'urgent'",
                    "required": False
                },
                "category": {
                    "type": "string",
                    "description": "Danh mục: 'general', 'technical', 'billing', 'complaint', 'feature_request'",
                    "required": False
                }
            }
        },
        
        "check_business_hours": {
            "name": "check_business_hours",
            "description": "Kiểm tra xem doanh nghiệp có đang mở cửa hay không dựa trên giờ làm việc đã cấu hình. Trả về trạng thái và giờ làm việc.",
            "parameters": {}
        },
        
        "send_faq_answer": {
            "name": "send_faq_answer",
            "description": "Tìm và gửi câu trả lời FAQ được định nghĩa sẵn. Sử dụng cho các câu hỏi thường gặp đã có sẵn câu trả lời chuẩn.",
            "parameters": {
                "question": {
                    "type": "string",
                    "description": "Câu hỏi cần tìm FAQ",
                    "required": True
                }
            }
        },
        
        "tag_conversation": {
            "name": "tag_conversation",
            "description": "Gắn thẻ cho hội thoại để phân loại (ví dụ: 'sale', 'complaint', 'question', 'feedback'). Giúp phân tích và báo cáo sau này.",
            "parameters": {
                "tags": {
                    "type": "array",
                    "description": "Danh sách các thẻ cần gắn",
                    "items": {"type": "string"},
                    "required": True
                }
            }
        },
        
        "transfer_conversation": {
            "name": "transfer_conversation",
            "description": "Chuyển hội thoại sang agent hoặc phòng ban khác. Sử dụng khi khách hàng cần hỗ trợ từ bộ phận chuyên môn.",
            "parameters": {
                "department": {
                    "type": "string",
                    "description": "Phòng ban hoặc agent đích (ví dụ: 'technical', 'sales', 'billing')",
                    "required": True
                },
                "reason": {
                    "type": "string",
                    "description": "Lý do chuyển",
                    "required": False
                }
            }
        },
        
        "send_private_reply": {
            "name": "send_private_reply",
            "description": "Gửi tin nhắn riêng (inbox) cho người dùng đã bình luận trên Facebook. Sử dụng khi khách hàng comment hỏi giá hoặc yêu cầu thông tin chi tiết.",
            "parameters": {
                "message": {
                    "type": "string",
                    "description": "Nội dung tin nhắn inbox",
                    "required": True
                }
            }
        },
        
        "hide_comment": {
            "name": "hide_comment",
            "description": "Ẩn bình luận spam hoặc tiêu cực trên Facebook. Sử dụng khi phát hiện spam, ngôn từ xúc phạm, hoặc nội dung không phù hợp.",
            "parameters": {
                "reason": {
                    "type": "string",
                    "description": "Lý do ẩn bình luận (ví dụ: 'spam', 'offensive', 'inappropriate')",
                    "required": True
                }
            }
        },
        
        "like_comment": {
            "name": "like_comment",
            "description": "Thích (like) bình luận tích cực của khách hàng. Sử dụng để tương tác và khích lệ feedback tốt.",
            "parameters": {}
        },
        
        "analyze_comment_sentiment": {
            "name": "analyze_comment_sentiment",
            "description": "Phân tích cảm xúc của bình luận (positive/neutral/negative). Trả về sentiment và mức độ tin cậy.",
            "parameters": {
                "comment_text": {
                    "type": "string",
                    "description": "Nội dung bình luận cần phân tích",
                    "required": True
                }
            }
        },
    }
    
    # Filter enabled tools
    enabled_tools = {k: v for k, v in all_tools.items() if k in tools_enabled}
    
    if provider == "openai":
        return [_tool_to_openai_format(tool) for tool in enabled_tools.values()]
    elif provider == "anthropic":
        return [_tool_to_anthropic_format(tool) for tool in enabled_tools.values()]
    elif provider == "google":
        return [_tool_to_google_format(tool) for tool in enabled_tools.values()]
    else:
        return []


def _tool_to_openai_format(tool: Dict[str, Any]) -> Dict[str, Any]:
    """Convert tool to OpenAI function calling format"""
    properties = {}
    required = []
    
    for param_name, param_def in tool["parameters"].items():
        properties[param_name] = {
            "type": param_def["type"],
            "description": param_def["description"]
        }
        if param_def.get("required"):
            required.append(param_name)
        
        if param_def["type"] == "array":
            properties[param_name]["items"] = param_def.get("items", {})
    
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


def _tool_to_anthropic_format(tool: Dict[str, Any]) -> Dict[str, Any]:
    """Convert tool to Anthropic tool format"""
    properties = {}
    required = []
    
    for param_name, param_def in tool["parameters"].items():
        properties[param_name] = {
            "type": param_def["type"],
            "description": param_def["description"]
        }
        if param_def.get("required"):
            required.append(param_name)
        
        if param_def["type"] == "array":
            properties[param_name]["items"] = param_def.get("items", {})
    
    return {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required
        }
    }


def _tool_to_google_format(tool: Dict[str, Any]) -> Dict[str, Any]:
    """Convert tool to Google Gemini format"""
    properties = {}
    required = []
    
    for param_name, param_def in tool["parameters"].items():
        properties[param_name] = {
            "type": param_def["type"].upper(),
            "description": param_def["description"]
        }
        if param_def.get("required"):
            required.append(param_name)
        
        if param_def["type"] == "array":
            properties[param_name]["items"] = param_def.get("items", {})
    
    return {
        "name": tool["name"],
        "description": tool["description"],
        "parameters": {
            "type": "OBJECT",
            "properties": properties,
            "required": required
        }
    }


# === TOOL EXECUTION ===

async def execute_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    agent: Dict[str, Any],
    conversation_id: str,
    db_functions: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute a tool call and return the result
    
    Args:
        tool_name: Name of the tool to execute
        tool_args: Arguments for the tool
        agent: Agent configuration dict
        conversation_id: Current conversation ID
        db_functions: Dictionary of database helper functions
    
    Returns:
        Dictionary with 'success' bool and 'result' or 'error' message
    """
    
    try:
        if tool_name == "search_knowledge":
            return await _execute_search_knowledge(tool_args, agent["id"], db_functions)
        
        elif tool_name == "escalate_to_human":
            return await _execute_escalate(tool_args, agent, conversation_id, db_functions)
        
        elif tool_name == "collect_customer_info":
            return await _execute_collect_info(tool_args, conversation_id, db_functions)
        
        elif tool_name == "create_ticket":
            return await _execute_create_ticket(tool_args, agent["id"], conversation_id, db_functions)
        
        elif tool_name == "check_business_hours":
            return await _execute_check_hours(agent)
        
        elif tool_name == "send_faq_answer":
            return await _execute_send_faq(tool_args, agent["id"], db_functions)
        
        elif tool_name == "tag_conversation":
            return await _execute_tag_conversation(tool_args, conversation_id, db_functions)
        
        elif tool_name == "transfer_conversation":
            return await _execute_transfer(tool_args, conversation_id, db_functions)
        
        elif tool_name == "send_private_reply":
            return await _execute_send_private_reply(tool_args, agent, conversation_id, db_functions)
        
        elif tool_name == "hide_comment":
            return await _execute_hide_comment(tool_args, conversation_id, db_functions)
        
        elif tool_name == "like_comment":
            return await _execute_like_comment(conversation_id, db_functions)
        
        elif tool_name == "analyze_comment_sentiment":
            return await _execute_analyze_sentiment(tool_args)
        
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
    
    except Exception as e:
        return {"success": False, "error": f"Tool execution error: {str(e)}"}


async def _execute_search_knowledge(args: Dict[str, Any], agent_id: str, db: Dict) -> Dict[str, Any]:
    """Execute knowledge search"""
    query = args.get("query", "")
    limit = args.get("limit", 5)
    
    results = db["search_knowledge"](agent_id, query, limit)
    
    if not results:
        return {
            "success": True,
            "result": "Không tìm thấy thông tin liên quan trong cơ sở kiến thức."
        }
    
    # Format results
    formatted = []
    for r in results:
        formatted.append(f"**{r.get('title', 'N/A')}** (Danh mục: {r.get('category', 'general')})\n{r['content']}")
    
    return {
        "success": True,
        "result": "\n\n---\n\n".join(formatted),
        "count": len(results)
    }


async def _execute_escalate(args: Dict[str, Any], agent: Dict, conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute escalate to human"""
    reason = args.get("reason", "Khách hàng yêu cầu")
    priority = args.get("priority", "medium")
    
    # Mark conversation as escalated
    sb = db["get_supabase"]()
    sb.table("conversations").update({"escalated": True}).eq("id", conv_id).execute()
    
    # Create ticket
    ticket_data = {
        "conversation_id": conv_id,
        "subject": "Escalation: " + reason,
        "description": f"Conversation escalated. Reason: {reason}",
        "priority": priority,
        "category": "escalation",
    }
    
    ticket = db["create_ticket"](agent["id"], ticket_data)
    
    escalation_config = agent.get("escalation_config", {})
    email = escalation_config.get("email", "")
    telegram = escalation_config.get("telegram_chat_id", "")
    
    notification_info = []
    if email:
        notification_info.append(f"Email: {email}")
    if telegram:
        notification_info.append(f"Telegram: {telegram}")
    
    return {
        "success": True,
        "result": f"Đã chuyển cho nhân viên hỗ trợ. Ticket #{ticket['id'][:8]} đã được tạo. {' | '.join(notification_info) if notification_info else 'Chưa cấu hình kênh thông báo.'}",
        "ticket_id": ticket["id"]
    }


async def _execute_collect_info(args: Dict[str, Any], conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute collect customer info"""
    sb = db["get_supabase"]()
    
    # Get current conversation
    conv = sb.table("conversations").select("customer_info").eq("id", conv_id).execute()
    current_info = conv.data[0].get("customer_info", {}) if conv.data else {}
    
    # Merge new info
    if args.get("name"):
        current_info["name"] = args["name"]
    if args.get("phone"):
        current_info["phone"] = args["phone"]
    if args.get("email"):
        current_info["email"] = args["email"]
    if args.get("notes"):
        current_info["notes"] = args["notes"]
    
    # Update conversation
    sb.table("conversations").update({"customer_info": current_info}).eq("id", conv_id).execute()
    
    collected = [k for k, v in args.items() if v and k != "notes"]
    
    return {
        "success": True,
        "result": f"Đã lưu thông tin khách hàng: {', '.join(collected)}",
        "customer_info": current_info
    }


async def _execute_create_ticket(args: Dict[str, Any], agent_id: str, conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute create ticket"""
    ticket_data = {
        "conversation_id": conv_id,
        "subject": args.get("subject", "Support Request"),
        "description": args.get("description", ""),
        "priority": args.get("priority", "medium"),
        "category": args.get("category", "general"),
    }
    
    ticket = db["create_ticket"](agent_id, ticket_data)
    
    return {
        "success": True,
        "result": f"Đã tạo ticket hỗ trợ #{ticket['id'][:8]}. Chúng tôi sẽ xử lý sớm nhất có thể.",
        "ticket_id": ticket["id"]
    }


async def _execute_check_hours(agent: Dict) -> Dict[str, Any]:
    """Execute check business hours"""
    business_hours = agent.get("business_hours", {})
    
    if not business_hours:
        return {
            "success": True,
            "result": "Giờ làm việc chưa được cấu hình.",
            "is_open": None
        }
    
    # Get current time (should use user's timezone, for now use UTC)
    now = datetime.utcnow()
    day_name = now.strftime("%A").lower()  # monday, tuesday, etc.
    current_time = now.strftime("%H:%M")
    
    day_hours = business_hours.get(day_name, {})
    
    if not day_hours.get("enabled", False):
        return {
            "success": True,
            "result": f"Hôm nay ({day_name}) không làm việc.",
            "is_open": False
        }
    
    open_time = day_hours.get("open", "09:00")
    close_time = day_hours.get("close", "18:00")
    
    is_open = open_time <= current_time <= close_time
    
    return {
        "success": True,
        "result": f"{'✅ Đang mở cửa' if is_open else '❌ Đã đóng cửa'}. Giờ làm việc: {open_time} - {close_time}",
        "is_open": is_open,
        "hours": f"{open_time} - {close_time}"
    }


async def _execute_send_faq(args: Dict[str, Any], agent_id: str, db: Dict) -> Dict[str, Any]:
    """Execute send FAQ answer (search knowledge base for FAQ)"""
    question = args.get("question", "")
    
    # Search knowledge base
    results = db["search_knowledge"](agent_id, question, limit=1)
    
    if not results:
        return {
            "success": True,
            "result": "Không tìm thấy câu trả lời FAQ phù hợp."
        }
    
    faq = results[0]
    return {
        "success": True,
        "result": f"**{faq.get('title', '')}**\n\n{faq['content']}",
        "faq_title": faq.get('title', '')
    }


async def _execute_tag_conversation(args: Dict[str, Any], conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute tag conversation"""
    tags = args.get("tags", [])
    
    if not tags:
        return {"success": False, "error": "No tags provided"}
    
    sb = db["get_supabase"]()
    
    # Get current tags
    conv = sb.table("conversations").select("tags").eq("id", conv_id).execute()
    current_tags = conv.data[0].get("tags", []) if conv.data else []
    
    # Merge tags (avoid duplicates)
    new_tags = list(set(current_tags + tags))
    
    # Update
    sb.table("conversations").update({"tags": new_tags}).eq("id", conv_id).execute()
    
    return {
        "success": True,
        "result": f"Đã gắn thẻ: {', '.join(tags)}",
        "tags": new_tags
    }


async def _execute_transfer(args: Dict[str, Any], conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute transfer conversation"""
    department = args.get("department", "")
    reason = args.get("reason", "")
    
    # For now, just tag the conversation with the transfer request
    # In production, this would integrate with a routing system
    
    sb = db["get_supabase"]()
    
    # Add metadata
    conv = sb.table("conversations").select("metadata").eq("id", conv_id).execute()
    metadata = conv.data[0].get("metadata", {}) if conv.data else {}
    
    metadata["transfer_request"] = {
        "department": department,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    sb.table("conversations").update({"metadata": metadata}).eq("id", conv_id).execute()
    
    return {
        "success": True,
        "result": f"Đang chuyển sang bộ phận {department}. {reason}",
        "department": department
    }


async def _execute_send_private_reply(args: Dict[str, Any], agent: Dict, conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute send private reply to commenter"""
    import httpx
    
    message = args.get("message", "")
    
    if not message:
        return {"success": False, "error": "Message is required"}
    
    try:
        sb = db["get_supabase"]()
        
        # Get conversation to find comment_id
        conv = sb.table("conversations").select("*, messages(*)").eq("id", conv_id).execute()
        if not conv.data:
            return {"success": False, "error": "Conversation not found"}
        
        # Find the latest user message with comment metadata
        messages = conv.data[0].get("messages", [])
        comment_id = None
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("metadata", {}).get("comment_id"):
                comment_id = msg["metadata"]["comment_id"]
                break
        
        if not comment_id:
            return {"success": False, "error": "Comment ID not found in conversation"}
        
        # Get Facebook channel config
        from server.db import get_channel
        channel = get_channel(agent["id"], "facebook")
        if not channel:
            return {"success": False, "error": "Facebook channel not configured"}
        
        page_token = channel.get("config", {}).get("page_token", "")
        if not page_token:
            return {"success": False, "error": "Facebook page token not found"}
        
        # Send private reply via Facebook API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{comment_id}/private_replies",
                params={"access_token": page_token},
                json={"message": message}
            )
            
            if response.status_code not in (200, 204):
                return {"success": False, "error": f"Facebook API error: {response.status_code}"}
        
        return {
            "success": True,
            "result": f"Đã gửi tin nhắn riêng cho khách hàng: {message[:50]}..."
        }
    
    except Exception as e:
        return {"success": False, "error": f"Failed to send private reply: {str(e)}"}


async def _execute_hide_comment(args: Dict[str, Any], conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute hide comment"""
    import httpx
    
    reason = args.get("reason", "spam")
    
    try:
        sb = db["get_supabase"]()
        
        # Get conversation to find comment_id and agent_id
        conv = sb.table("conversations").select("*, messages(*)").eq("id", conv_id).execute()
        if not conv.data:
            return {"success": False, "error": "Conversation not found"}
        
        agent_id = conv.data[0].get("agent_id")
        messages = conv.data[0].get("messages", [])
        comment_id = None
        
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("metadata", {}).get("comment_id"):
                comment_id = msg["metadata"]["comment_id"]
                break
        
        if not comment_id:
            return {"success": False, "error": "Comment ID not found"}
        
        # Get Facebook channel config
        from server.db import get_channel, update_facebook_comment
        channel = get_channel(agent_id, "facebook")
        if not channel:
            return {"success": False, "error": "Facebook channel not configured"}
        
        page_token = channel.get("config", {}).get("page_token", "")
        if not page_token:
            return {"success": False, "error": "Facebook page token not found"}
        
        # Hide comment via Facebook API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{comment_id}",
                params={"access_token": page_token},
                json={"is_hidden": True}
            )
            
            if response.status_code not in (200, 204):
                return {"success": False, "error": f"Facebook API error: {response.status_code}"}
        
        # Update database
        update_facebook_comment(comment_id, {
            "is_hidden": True,
            "is_spam": reason == "spam"
        })
        
        return {
            "success": True,
            "result": f"Đã ẩn bình luận (Lý do: {reason})"
        }
    
    except Exception as e:
        return {"success": False, "error": f"Failed to hide comment: {str(e)}"}


async def _execute_like_comment(conv_id: str, db: Dict) -> Dict[str, Any]:
    """Execute like comment"""
    import httpx
    
    try:
        sb = db["get_supabase"]()
        
        # Get conversation to find comment_id and agent_id
        conv = sb.table("conversations").select("*, messages(*)").eq("id", conv_id).execute()
        if not conv.data:
            return {"success": False, "error": "Conversation not found"}
        
        agent_id = conv.data[0].get("agent_id")
        messages = conv.data[0].get("messages", [])
        comment_id = None
        
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("metadata", {}).get("comment_id"):
                comment_id = msg["metadata"]["comment_id"]
                break
        
        if not comment_id:
            return {"success": False, "error": "Comment ID not found"}
        
        # Get Facebook channel config
        from server.db import get_channel, update_facebook_comment
        channel = get_channel(agent_id, "facebook")
        if not channel:
            return {"success": False, "error": "Facebook channel not configured"}
        
        page_token = channel.get("config", {}).get("page_token", "")
        if not page_token:
            return {"success": False, "error": "Facebook page token not found"}
        
        # Like comment via Facebook API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{comment_id}/likes",
                params={"access_token": page_token}
            )
            
            if response.status_code not in (200, 204):
                return {"success": False, "error": f"Facebook API error: {response.status_code}"}
        
        # Update database
        update_facebook_comment(comment_id, {"is_liked": True})
        
        return {
            "success": True,
            "result": "Đã thích bình luận"
        }
    
    except Exception as e:
        return {"success": False, "error": f"Failed to like comment: {str(e)}"}


async def _execute_analyze_sentiment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute analyze comment sentiment"""
    comment_text = args.get("comment_text", "")
    
    if not comment_text:
        return {"success": False, "error": "Comment text is required"}
    
    # Simple sentiment analysis (can be enhanced with ML models)
    text_lower = comment_text.lower()
    
    positive_words = [
        "tuyệt", "đẹp", "ok", "good", "great", "excellent", "love", "nice", 
        "amazing", "perfect", "wonderful", "👍", "❤️", "😍", "🥰", "tốt", 
        "hay", "thích", "ưng"
    ]
    
    negative_words = [
        "tệ", "dở", "bad", "poor", "terrible", "awful", "hate", "worst",
        "fake", "lừa đảo", "scam", "kém", "không tốt", "👎", "😡", "💩"
    ]
    
    neutral_indicators = ["?", "bao nhiêu", "giá", "còn hàng", "how", "what", "when"]
    
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)
    
    if neg_count > pos_count:
        sentiment = "negative"
        confidence = min(0.5 + (neg_count * 0.1), 0.95)
    elif pos_count > neg_count:
        sentiment = "positive"
        confidence = min(0.5 + (pos_count * 0.1), 0.95)
    else:
        sentiment = "neutral"
        confidence = 0.6
    
    return {
        "success": True,
        "result": f"Sentiment: {sentiment} (Confidence: {confidence:.0%})",
        "sentiment": sentiment,
        "confidence": confidence,
        "positive_signals": pos_count,
        "negative_signals": neg_count
    }
