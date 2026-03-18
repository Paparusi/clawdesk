<div align="center">

# 🤖 ClawDesk

**AI Agent quản lý Fanpage & CSKH cho shop Việt Nam**

Tự động trả lời tin nhắn, comment, tạo bài viết, quản lý đơn hàng — tất cả bằng AI.

[Demo](https://clawdesk-api-production.up.railway.app) · [Tài liệu](#hướng-dẫn) · [Báo lỗi](https://github.com/Paparusi/clawdesk/issues)

![License](https://img.shields.io/badge/license-ELv2-blue)
![Stars](https://img.shields.io/github/stars/Paparusi/clawdesk)

</div>

## ✨ Tính năng

### 🤖 AI Agent
- Tự động trả lời tin nhắn 24/7
- Hỗ trợ OpenAI, Anthropic Claude, Google Gemini
- RAG Knowledge Base (AI đọc tài liệu shop)
- 8 công cụ CSKH (tạo ticket, escalate, thu thập info...)
- 8 mẫu agent cho từng ngành (thời trang, mỹ phẩm, F&B...)

### 📱 Đa kênh
- Facebook Messenger
- Facebook Comment (auto-reply, inbox, hide spam)
- Zalo OA
- Telegram Bot
- Webchat Widget (nhúng vào website)

### 🛒 E-Commerce
- Quản lý sản phẩm (giá, tồn kho, danh mục)
- Quản lý đơn hàng (Kanban board)
- AI tự tạo đơn khi khách chốt
- Khách hỏi "giá bao nhiêu" → AI tra catalog trả lời

### 📊 Quản lý
- Dashboard analytics
- Automation rules (IF-THEN)
- Broadcast messaging
- Customer CRM & segmentation
- Quick reply templates
- Export CSV
- Conversation search

### 🎨 Giao diện
- Dark theme premium
- Responsive (desktop + mobile)
- Vietnamese UI
- Keyboard shortcuts

## 🚀 Cài đặt

### Cloud (Khuyến nghị)
Đăng ký tại [clawdesk.ai](https://clawdesk-api-production.up.railway.app) — dùng ngay, không cần cài đặt.

### Self-host

**Yêu cầu:**
- Python 3.11+
- PostgreSQL (hoặc Supabase)
- API key từ OpenAI/Anthropic/Google

**Bước 1:** Clone repo
```bash
git clone https://github.com/Paparusi/clawdesk.git
cd clawdesk
```

**Bước 2:** Cấu hình
```bash
cp .env.example .env
# Sửa SUPABASE_URL, SUPABASE_SERVICE_KEY
```

**Bước 3:** Chạy database migrations
```sql
-- Chạy theo thứ tự trong Supabase SQL Editor:
schema.sql
migration_v2.sql
migration_v3.sql
migration_v4.sql
migration_v5.sql
migration_v6.sql
migration_v7.sql
migration_v8.sql
migration_v9.sql
```

**Bước 4:** Chạy server
```bash
pip install -r requirements.txt
python -m server.main
```

Mở http://localhost:8080

### Docker
```bash
docker-compose up -d
```

## 📸 Screenshots
(Add dashboard screenshots later)

## 🏗️ Tech Stack
- **Backend:** Python, FastAPI, Supabase (PostgreSQL)
- **Frontend:** Vanilla JS, Single-file HTML
- **AI:** OpenAI, Anthropic, Google AI
- **Channels:** Facebook Graph API, Telegram Bot API, Zalo OA API

## 📄 License

ClawDesk sử dụng [Elastic License 2.0 (ELv2)](LICENSE):
- ✅ Tự do sử dụng, sửa đổi, self-host
- ✅ Dùng cho business nội bộ
- ❌ Không được cung cấp như dịch vụ hosted cho người khác (SaaS cạnh tranh)
- ❌ Không được bỏ license key system

Nói đơn giản: **dùng cho shop/công ty của bạn = OK. Clone rồi bán lại = KHÔNG.**

## 🤝 Đóng góp
Pull requests are welcome! Vui lòng mở issue trước khi submit PR lớn.

## 📞 Liên hệ
- GitHub: [@Paparusi](https://github.com/Paparusi)
- Email: hieu766886@gmail.com

---
Made with ❤️ in Vietnam 🇻🇳
