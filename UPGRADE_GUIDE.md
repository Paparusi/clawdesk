# Upgrade Guide: JSON → Supabase PostgreSQL

ClawDesk has been upgraded from JSON file storage to production-grade Supabase PostgreSQL with JWT authentication and Row Level Security (RLS).

## What Changed

### Backend
- **Authentication**: Replaced simple token-based auth with Supabase Auth (JWT tokens)
- **Database**: Migrated from JSON file storage to PostgreSQL with proper schema
- **Security**: Added Row Level Security (RLS) policies to protect user data
- **Token Management**: Access tokens + refresh tokens for secure session handling

### Database Schema
New tables created:
- `profiles` - User profiles (linked to Supabase Auth)
- `agents` - AI agent configurations
- `channels` - Communication channels (Telegram, Facebook, Zalo, Webchat)
- `knowledge_base` - Knowledge base entries per agent
- `conversations` - Chat conversations
- `messages` - Individual messages in conversations

### API Changes
**Auth endpoints:**
- `POST /api/auth/register` - Now returns `access_token` + `refresh_token` instead of `token`
- `POST /api/auth/login` - Now returns `access_token` + `refresh_token` instead of `token`
- `POST /api/auth/refresh` - NEW: Refresh access token using refresh token
- `GET /api/auth/me` - Verify token and get user profile

**Frontend changes:**
- Stores `access_token` and `refresh_token` in localStorage (instead of `token`)
- Automatic token refresh on 401 errors
- Token verification on dashboard load

## Migration Steps

### 1. Create Supabase Project
1. Go to https://supabase.com and create a new project
2. Wait for database provisioning to complete

### 2. Run Database Schema
1. Open Supabase SQL Editor
2. Copy and paste the entire content of `database/schema.sql`
3. Run the SQL script
4. Verify tables were created in the Table Editor

### 3. Get Supabase Credentials
From your Supabase project settings (Settings > API):
- **SUPABASE_URL**: Your project URL (e.g., `https://xxxxx.supabase.co`)
- **SUPABASE_ANON_KEY**: The `anon` `public` key
- **SUPABASE_SERVICE_KEY**: The `service_role` `secret` key (⚠️ keep secret!)
- **SUPABASE_JWT_SECRET**: From Settings > API > JWT Settings

### 4. Configure Environment
1. Copy `.env.example` to `.env`
2. Fill in your Supabase credentials:
```bash
SERVER_URL=https://your-domain.com
PORT=8080

SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGc...  # service_role key
SUPABASE_ANON_KEY=eyJhbGc...     # anon key
SUPABASE_JWT_SECRET=your-jwt-secret-here
```

### 5. Install Dependencies
```bash
pip install -r requirements.txt
```

### 6. Start the Server
```bash
uvicorn server.main:app --host 0.0.0.0 --port 8080
```

### 7. Test the System
1. Open the app in your browser
2. Register a new account
3. Create an agent
4. Test the chat endpoint

## Data Migration (Optional)

If you have existing data in `db.json`, you need to migrate it manually:

### Migrate Users
```python
import json
from supabase import create_client

# Load old data
with open('db.json') as f:
    old_db = json.load(f)

# Connect to Supabase
sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# For each user, create account in Supabase Auth
# Then migrate their agents, channels, knowledge base, etc.
# (Manual process - adapt to your needs)
```

## Breaking Changes

### Frontend
- `localStorage.getItem('token')` → `localStorage.getItem('access_token')`
- Need to store and handle `refresh_token` separately
- All API calls need `Authorization: Bearer <access_token>` header

### Backend
- Auth endpoints now return different token structure
- Protected endpoints verify JWT tokens (not simple tokens)
- Database operations use Supabase client (not JSON file)

## Security Notes

⚠️ **Important:**
- Never expose `SUPABASE_SERVICE_KEY` to the frontend or public
- Only use `SUPABASE_ANON_KEY` in frontend code
- RLS policies protect data access (users can only see their own data)
- Webhooks use service_role client to bypass RLS
- Always use HTTPS in production

## Rollback Plan

If you need to rollback:
1. Keep the old `db.json` file as backup
2. The old code is in git history before commit `46d22e8`
3. Revert with: `git revert HEAD` or `git checkout <old-commit>`

## Support

If you encounter issues:
1. Check Supabase logs (Dashboard > Logs)
2. Check server logs for Python errors
3. Verify environment variables are set correctly
4. Ensure database schema was created successfully

## Next Steps

After migration:
- [ ] Test all endpoints
- [ ] Migrate existing data (if any)
- [ ] Update deployment scripts
- [ ] Configure production secrets
- [ ] Set up database backups
- [ ] Monitor performance and optimize queries
- [ ] Consider adding database indexes for performance
- [ ] Set up Supabase Auth email templates
- [ ] Configure rate limiting for API endpoints
