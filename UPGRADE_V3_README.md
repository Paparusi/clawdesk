# ClawDesk V3 Upgrade - Production-Ready CSKH Platform

## 🎯 What's New

This upgrade batch focuses on production-ready features for a complete customer service platform.

## ✨ Features Added

### 1. 🌐 Premium Webchat Widget (widget.js)
Complete rewrite with enterprise features:
- **Visual Enhancements:**
  - Customizable colors via `data-color` attribute
  - Agent avatar & name from API
  - Online/offline status indicator
  - Sound notifications for new messages
  - Unread message badge
  - Light/dark theme support
  
- **Chat UX:**
  - Dynamic welcome message from agent config
  - Suggested quick replies
  - Typing indicator with animated dots
  - Message timestamps
  - Lightweight markdown rendering (bold, italic, links, lists)
  - File/image upload support
  - Emoji picker (30 common emojis)
  - Pre-chat form (optional name/email collection)
  - Resize handle & mobile full-screen mode
  
- **Technical:**
  - Auto-reconnect on API failure
  - Rate limiting (max 1 msg/sec)
  - Message history in localStorage (last 50)
  - Auto-scroll with "scroll to bottom" button
  - Full keyboard navigation & ARIA labels
  - Zero dependencies, single file, <28KB
  - CSP-safe (no eval, inline styles via JS)

### 2. 📱 Zalo OA Webhook (Backend)
- New endpoint: `POST /api/webhook/zalo/{agent_id}`
- Receives Zalo Official Account events
- Auto-replies via Zalo API
- Full conversation tracking

### 3. 💬 Enhanced Conversation Management (Dashboard)
**Conversation List:**
- Real-time unread count badge
- Search by customer name/content
- Filter by: channel, status, date range
- Sort by: latest, most messages, escalated
- Bulk actions: mark resolved, export, delete

**Conversation Detail:**
- Full message history with timestamps
- Customer info sidebar (name, phone, email, channel stats)
- Manual reply capability (sends via channel API)
- Internal notes (staff-only, not visible to customer)
- Quick actions: escalate, resolve, tag, create ticket
- Tool usage display (shows when AI used tools)

### 4. 📊 Agent Analytics (Dashboard)
New Analytics tab for each agent showing:
- Messages per day chart (last 7 days, pure CSS bars)
- Response time average
- Top queries (most common customer questions)
- Channel breakdown (% by platform)
- Peak hours heatmap
- Total conversations & messages

### 5. 🔔 Notification System
**Backend:**
- `GET /api/notifications` - list recent events
- `GET /api/notifications/unread` - count unread
- `PUT /api/notifications/{id}/read` - mark as read
- Auto-triggered on escalations, new conversations, tickets

**Frontend:**
- Bell icon in topbar with unread badge
- Dropdown notification panel
- Click notification → navigate to relevant page
- Auto-polling every 30 seconds
- Support for browser desktop notifications

### 6. 💬 Quick Replies / Saved Responses
**Backend:**
- Stored in agent `settings.saved_replies` (JSONB)
- `GET /api/agents/{agent_id}/replies` - list
- `POST /api/agents/{agent_id}/replies` - create
- `DELETE /api/agents/{agent_id}/replies/{reply_id}` - delete

**Frontend:**
- New "Câu trả lời nhanh" tab in agent settings
- Create templates with title, content, shortcut
- Type "/" in conversation to see saved replies dropdown
- One-click insert into message box

### 7. 👥 Customer Management (CRM)
**Backend:**
- `GET /api/agents/{agent_id}/customers` - list unique customers
- `GET /api/agents/{agent_id}/customers/{sender_id}` - detail
- `PUT /api/agents/{agent_id}/customers/{sender_id}` - update info
- Customer profile: name, phone, email, channels, total conversations, messages, first/last seen, tags, notes

**Frontend:**
- New "👥 Khách hàng" sidebar nav item
- Customer list with search
- Customer detail page: all conversations, info, notes
- Edit customer metadata (name, tags, notes)
- View all conversation history per customer

## 🗄️ Database Changes

New migration file: `database/migration_v3.sql`

**New Tables:**
- `notifications` - Real-time event notifications

**Updated Tables:**
- `conversations` - Added `tags[]`, `notes` columns

**New Views:**
- `daily_message_stats` - Aggregated analytics
- `customer_summary` - Unique customer summaries

**New Functions:**
- `create_notification()` - Helper for creating notifications
- `notify_on_escalation()` - Auto-trigger on escalations

## 📋 Migration Steps

1. **Run database migration:**
   ```bash
   psql $DATABASE_URL -f database/migration_v3.sql
   ```

2. **Update widget embed code:**
   ```html
   <script src="https://YOUR_DOMAIN/widget.js" 
           data-agent="AGENT_ID" 
           data-color="#818cf8" 
           data-theme="dark"
           data-prechat="false"></script>
   ```

3. **Configure Zalo OA (if using):**
   - Add Zalo channel to agent
   - Set `access_token` and `oa_id` in channel config
   - Configure webhook URL in Zalo Developer Console:
     `https://YOUR_DOMAIN/api/webhook/zalo/{agent_id}`

## 🎨 Design Principles

- **Vietnamese-first:** All UI strings in Vietnamese
- **Dark theme:** Consistent zinc + indigo accent colors
- **Zero external dependencies:** Widget is pure vanilla JS
- **Pure CSS charts:** No Chart.js or heavy libraries
- **Mobile-friendly:** Responsive design, full-screen on mobile
- **Accessible:** Keyboard navigation, ARIA labels
- **Performance:** Lazy loading, efficient queries, minimal JS

## 🔐 Security

- All API endpoints require JWT auth (except webhooks & widget)
- Row-level security (RLS) on all Supabase tables
- CSP-safe widget implementation
- Rate limiting on widget messages (1 msg/sec)
- File upload validation (10MB max)

## 📦 File Changes

- ✅ `static/widget.js` - Complete rewrite (199 → 27.5KB)
- ✅ `server/main.py` - Added ~450 lines (webhooks, notifications, customers, analytics)
- ✅ `static/dashboard.html` - Added ~250 lines (customers view, analytics, notifications, saved replies)
- ✅ `database/migration_v3.sql` - New migration file

## 🚀 What's Working

- ✅ Premium widget with all features
- ✅ Zalo OA webhook integration
- ✅ Real-time notifications
- ✅ Customer management CRM
- ✅ Agent analytics dashboard
- ✅ Saved replies system
- ✅ Enhanced conversation management

## 🔜 Future Enhancements (Not in this batch)

- WhatsApp Business API integration
- Advanced NLP for top queries clustering
- Real-time websocket for live updates
- Ticket assignment & SLA tracking
- Multi-language support (English, etc.)
- Sentiment analysis on conversations

---

**Upgraded by:** AI Assistant (ClawDesk Subagent)  
**Date:** 2026-03-18  
**Version:** 3.0.0  
**Status:** ✅ Production Ready
