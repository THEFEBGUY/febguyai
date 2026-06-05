# FebGuy AI — Updated Professional Upgrade Plan

## Current project status

This plan assumes the project has already completed these steps:

- AI model migration from local Ollama to cloud APIs is done.
- Normal chat uses Groq API.
- Code Studio uses Groq coding model.
- Vision/image support uses Gemini and/or Groq vision fallback.
- Voice mode uses cloud API flow where needed.
- Git is installed.
- `.gitignore` is updated.
- Private/generated files are removed from Git tracking.
- Backend `.env` already contains Supabase values:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `DATABASE_URL`
- `DATABASE_URL` should use Supabase Transaction Pooler URI for deployment compatibility.
- Existing project features must not be removed.

---

# Important rules for Codex

Before starting any phase, Codex must follow these rules:

1. Do not remove existing FebGuy AI features.
2. Do not expose API keys or secrets.
3. Do not edit `.env` values directly.
4. Do not commit secrets, database files, processed files, backups, node_modules, or build files.
5. Preserve:
   - Normal chat
   - Code Studio
   - Voice mode
   - File upload
   - DOCX to PDF conversion
   - PDF reading/OCR
   - Image/vision support
   - Web search
   - Weather
   - Calculator
   - Memory
   - Settings
   - Chat persistence
   - Code chat persistence
   - Download system
   - Existing UI
6. Work phase by phase.
7. After every phase, explain:
   - Files changed
   - What changed
   - How to test
   - What should be committed
8. Do not start the next phase until the current phase is tested.

---

# Recommended Codex intelligence

Use this:

```text
Small bug fix                     → Medium
Frontend UI only                  → High
Database/auth/security/session    → Extra High
Supabase migration                → Extra High
Guest/session/profile ownership   → Extra High
Testing/refactor                  → High
```

---

# First command to give Codex

Use this before any implementation:

```text
Read FEATURE_PLAN_UPDATED.md completely. Summarize the current project status, requirements, risks, and phase order. Do not edit code yet.
```

---

# Phase 0 — Safety check before changes

## Goal

Confirm the project is safe before new database/auth/profile work.

## Codex prompt

```text
Phase 0 only: Safety check.

Check current project state before making changes.

Verify:
1. Git is clean or show current changed files.
2. `.gitignore` protects `.env`, database files, processed_files, backups, node_modules, and build folders.
3. Cloud API model migration is working:
   - normal chat
   - Code Studio
   - image/vision
   - voice mode if implemented
4. Backend `.env` expects Supabase values:
   - SUPABASE_URL
   - SUPABASE_ANON_KEY
   - SUPABASE_SERVICE_ROLE_KEY
   - DATABASE_URL
5. Do not edit code yet unless a small safety issue is found.

Return:
- Current risk list
- Files likely to change in next phases
- Exact test checklist before Phase 0.5
```

---

# Phase 0.5 — Supabase/Postgres database connection

## Goal

Connect backend to Supabase Postgres safely before changing auth/profile logic.

SQLite may remain as local fallback temporarily, but production should use Supabase Postgres.

## Codex prompt

```text
Implement Phase 0.5 only: Supabase/Postgres database connection.

Context:
I already added these values in backend/.env:
- SUPABASE_URL
- SUPABASE_ANON_KEY
- SUPABASE_SERVICE_ROLE_KEY
- DATABASE_URL using Supabase Transaction Pooler

Important:
- Do not start Guest Mode.
- Do not start Google login/profile phases.
- Do not change UI unless absolutely needed.
- Do not remove existing features.
- Keep current Groq/Gemini/Groq Vision API model system working.
- Keep chat, Code Studio, voice, file upload, image vision, weather, search, calculator, memory, summaries, and downloads working.
- Do not expose SUPABASE_SERVICE_ROLE_KEY to frontend.
- Do not print or commit .env values.

Tasks:
1. Add Supabase/Postgres connection support.
2. Add required Python dependencies if needed.
3. Add database health check, preferably extending /health.
4. Add a clean database abstraction layer if needed.
5. Provide SQL schema I must run in Supabase SQL Editor.
6. Do not migrate all existing app logic yet unless it is safe.
7. If full migration is risky, stop after connection + schema + health check.

After editing, tell me:
- Files changed
- Dependencies added
- SQL to run in Supabase
- How to test database connection
- How to verify connection in Supabase dashboard
- What still uses SQLite
```

## Required env values

```env
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
```

## Expected test

```text
GET /health should show database status: connected
```

---

# Phase 0.6 — Supabase schema creation

## Goal

Create production-ready tables in Supabase.

## Codex prompt

```text
Implement Phase 0.6 only: Supabase schema creation.

Do not change app behavior yet.

Create SQL schema for:
- users
- devices
- guest_sessions
- profiles
- sessions
- chats
- code_chats
- messages
- code_messages
- memories
- memory_facts
- settings
- documents
- files
- usage_limits

Requirements:
1. Use UUID primary keys where appropriate.
2. Add created_at and updated_at.
3. Add ownership fields:
   - user_id
   - guest_id
   - profile_id
   - device_id
4. Add indexes for owner-based queries.
5. Add RLS-safe structure.
6. Do not expose service role key.
7. Give me SQL that I can run in Supabase SQL Editor.
8. Do not remove SQLite code yet unless required.

After generating SQL, explain:
- Which tables are for guest users
- Which tables are for signed-in users
- Which tables are for profiles
- Which tables store chat/code/file data
```

---

# Phase 0.7 — Database adapter migration

## Goal

Move app database operations from direct SQLite-only usage to a clean adapter pattern.

## Codex prompt

```text
Implement Phase 0.7 only: Database adapter migration.

Goal:
Create a clean database layer so the app can use Supabase/Postgres in production and optionally SQLite locally.

Important:
- Preserve all existing features.
- Do not change UI.
- Do not start Guest Mode yet.
- Do not start Google login/profile phases yet.
- Do not break current profiles/chats/code chats.

Tasks:
1. Create database adapter/helper functions.
2. Use DATABASE_URL for Supabase/Postgres.
3. Keep SQLite fallback only if safe.
4. Move repeated DB logic into helper functions.
5. Keep existing data behavior working.
6. Add clear ownership-ready fields but do not enforce guest/profile ownership yet.
7. Update /health to show which database backend is active.

After editing:
- List changed files.
- Tell me how to test normal chat, Code Studio, memory, settings, and file upload.
- Tell me what still uses old SQLite logic.
```

---

# Phase 1 — Device ID system

## Goal

Every browser/device should have a stable device ID.

## Codex prompt

```text
Implement Phase 1 only: device_id system.

Requirements:
1. Frontend creates/loads stable device ID from localStorage key:
   febguy_device_id
2. If missing, generate UUID and save it.
3. Send device_id with:
   - guest start later
   - login later
   - profile requests later
   - chat
   - code chat
   - file upload
4. Backend accepts and validates device_id.
5. Backend stores/updates device info in database where appropriate.
6. Do not start Guest Mode.
7. Do not start Google login/profile phases.
8. Preserve all existing features.

After editing:
- Tell me files changed.
- Tell me how to check localStorage.
- Tell me how to confirm backend receives device_id.
```

---

# Phase 2 — Guest Mode

## Goal

New users can open the website and use FebGuy AI instantly without login.

## Codex prompt

```text
Implement Phase 2 only: Guest Mode.

Requirements:
1. On first website visit, frontend loads/creates febguy_device_id.
2. Frontend calls POST /guest/start.
3. Backend creates or loads guest session linked to device_id.
4. Guest user enters main workspace immediately.
5. Guest user does not need PIN/password.
6. Guest user can only have one temporary profile/session.
7. Guest data is isolated by guest_id + device_id.
8. Guest user sees Guest badge.
9. Guest cannot access signed-in profile list.
10. Do not start Google login/profile phases yet.

Guest limits should exist in database but can be simple:
- 15 normal chat messages total
- 4 Code Studio messages total
- 2 file uploads total

After editing:
- Tell me how guest session is created.
- Tell me where guest data is stored.
- Tell me how to test first visit in incognito.
```

---

# Phase 3 — Guest Code Studio limits

## Goal

Guest users can use Code Studio as a limited demo.

## Codex prompt

```text
Implement Phase 3 only: Guest Code Studio logic.

Guest Code Studio can:
- ask coding questions
- generate small code snippets
- debug small examples
- explain code
- convert small code between languages

Guest Code Studio cannot:
- run server code
- save long-term projects
- create multiple code workspaces
- upload large project folders
- use unlimited coding model requests

Backend requirements:
1. Enforce 4 guest code messages before calling code model.
2. If limit reached, return structured error:
{
  "error": "GUEST_LIMIT_REACHED",
  "limit_type": "code",
  "message": "Guest Code Studio limit reached. Sign in to continue coding and save your work."
}
3. Frontend should show this message clearly.
4. Do not affect signed-in/full Code Studio logic.

After editing:
- Tell me how to test guest code limit.
```

---

# Phase 4 — Guest chat/file limits + upgrade modal

## Goal

Guests hit limits and are asked to sign in.

## Codex prompt

```text
Implement Phase 4 only: Guest limit UI and backend checks.

Requirements:
1. Enforce guest limits on backend:
   - chat messages
   - code messages
   - file uploads
2. Frontend displays remaining limits:
   - Chat messages left
   - Code messages left
   - File uploads left
3. When limit is reached, show sign-in/upgrade modal.
4. Modal should explain:
   - Sign in to continue
   - Save chats
   - Unlock profiles
   - Unlock full Code Studio
   - Unlock more file tools
5. Do not delete guest chats.
6. Do not start Google login yet unless placeholder button is needed.
7. Backend must enforce limits, not frontend only.

After editing:
- Tell me how to test each limit.
```

---

# Phase 5 — Google/email auth foundation

## Goal

Add account-level login foundation.

## Codex prompt

```text
Implement Phase 5 only: Google/email account foundation.

Important:
- Use Supabase/Auth or backend-managed OAuth only if already planned.
- Do not expose secrets to frontend.
- Do not remove Guest Mode.
- Do not remove current profile system until replacement is working.

Requirements:
1. Add account identity:
   - user_id
   - email
   - provider
   - provider_id
   - onboarding_completed
2. Add auth/session flow for signed-in accounts.
3. Add endpoints:
   - GET /me
   - GET /onboarding/status
   - POST /onboarding/complete
4. After login, user is in account mode, not profile mode yet.
5. Do not start device-bound profiles yet.
6. Preserve guest mode and existing features.

After editing:
- Tell me how login is implemented.
- Tell me what is placeholder and what is production-ready.
- Tell me how to test.
```

---

# Phase 6 — Onboarding page

## Goal

After first login, explain profile system.

## Codex prompt

```text
Implement Phase 6 only: onboarding/instruction page.

After first login:
1. If onboarding_completed is false, show onboarding page.
2. Explain:
   - Profiles are private workspaces.
   - Each profile has a PIN.
   - Max 3 profiles per account per device.
   - Profiles protect privacy on shared/stolen devices.
   - Profiles are device-bound by default.
3. After user clicks continue, call POST /onboarding/complete.
4. Then show profile selection/creation page.
5. Show onboarding only once per account.

Do not change guest mode or AI model logic.
```

---

# Phase 7 — Device-bound private profiles

## Goal

Profiles belong to user + device and are PIN-protected.

## Codex prompt

```text
Implement Phase 7 only: device-bound private profiles.

Requirements:
1. Each signed-in account can create max 3 profiles per device.
2. Profile belongs to:
   - user_id
   - device_id
3. /profiles returns only profiles for current user_id + current device_id.
4. Backend must never return all profiles publicly.
5. Same profile name and same PIN can exist on different devices/accounts.
6. Different device cannot access another device profile.
7. If profile does not belong to current user/device, return:
   "Profile does not exist on this device."
8. PIN must be hashed with salt.
9. Never store or return raw PIN.
10. Use constant-time comparison.

After editing:
- Tell me how to test profile isolation.
- Tell me how to test same profile name/PIN on different devices.
```

---

# Phase 8 — Session model cleanup

## Goal

Support guest, account, and profile sessions cleanly.

## Codex prompt

```text
Implement Phase 8 only: session model cleanup.

Session modes:
- guest
- account
- profile

Requirements:
1. Guest routes require guest session.
2. Account routes require account/profile session.
3. Profile routes require profile session.
4. Chat ownership should use current active mode.
5. Logout invalidates backend session.
6. Do not allow profile routes from guest sessions.
7. Do not allow guest data to leak into signed-in profiles.

After editing:
- Explain session structure.
- Explain how frontend stores session.
- Explain how to test logout/login/profile unlock.
```

---

# Phase 9 — Data ownership enforcement

## Goal

Every chat, file, memory, code chat, and document belongs to the correct owner.

## Codex prompt

```text
Implement Phase 9 only: data ownership enforcement.

Requirements:
1. Chats, code chats, memory, settings, files, documents, and downloads must filter by owner.
2. Guest data:
   WHERE guest_id = current_guest_id AND device_id = current_device_id
3. Profile data:
   WHERE user_id = current_user_id AND profile_id = current_profile_id
4. Never query user data without ownership filtering.
5. Download route must verify file owner before serving.
6. Guest cannot access signed-in data.
7. Signed-in user cannot access another user's data.
8. Other device cannot access device-bound profile data.

After editing:
- Tell me how to test ownership.
- Tell me how to test download protection.
```

---

# Phase 10 — Secure upload/download

## Goal

Make file handling safe for deployment.

## Codex prompt

```text
Implement Phase 10 only: secure file upload and download.

Requirements:
1. Validate file extension and MIME type.
2. Allow only:
   - pdf
   - docx
   - png
   - jpg
   - jpeg
   - txt
3. Reject dangerous files:
   - exe
   - bat
   - cmd
   - sh
   - zip unless safely supported
4. Enforce max file size.
5. Store uploaded files in controlled directory/storage.
6. Prevent path traversal like ../../secret.env.
7. Download route must check owner before serving file.
8. Guest file uploads count toward guest limit.
9. Do not break DOCX to PDF conversion or image/PDF analysis.

After editing:
- Tell me how to test safe files.
- Tell me how to test rejected files.
```

---

# Phase 11 — API security for deployment

## Goal

Prepare backend for online deployment.

## Codex prompt

```text
Implement Phase 11 only: deployment API security.

Requirements:
1. Add structured errors.
2. Do not leak stack traces to frontend.
3. Log errors server-side only.
4. Configure production CORS using CORS_ORIGINS from env.
5. Add basic rate limiting for:
   - login
   - profile PIN attempts
   - guest chat
   - file uploads
   - AI calls
6. Validate inputs with Pydantic.
7. Add or improve /health endpoint.
8. Add request size protections if possible.
9. Do not expose API keys or database secrets.
10. Keep all features working.

After editing:
- Tell me production env variables required.
- Tell me how to test rate limit and CORS.
```

---

# Phase 12 — Frontend UX polish

## Goal

Make the product feel professional.

## Codex prompt

```text
Implement Phase 12 only: frontend UX polish for guest/account/profile system.

Add:
1. Guest badge.
2. Remaining limits display.
3. Upgrade/sign-in modal.
4. Onboarding page.
5. Profile device error UI.
6. Code Studio guest/full indicator.
7. Better friendly error messages.
8. Loading states for auth/profile/session.
9. Do not redesign entire UI.
10. Preserve existing theme and layout.

After editing:
- Tell me what components changed.
- Tell me how to test guest to login to profile flow.
```

---

# Phase 13 — Regression testing

## Goal

Verify everything works.

## Codex prompt

```text
Implement Phase 13 only: testing and verification.

Run through this checklist and fix only bugs found:

Guest:
- First visit opens app without login
- Guest chat works
- Guest Code Studio works
- Guest file upload works
- Guest limits decrease
- Limit reached modal appears
- Guest cannot access profiles

Account/profile:
- Login works
- Onboarding appears once
- Profile creation works
- Max 3 profiles enforced
- PIN login works
- Wrong PIN fails
- Same profile name/PIN can exist on different devices/accounts
- Other device cannot see profile

Security:
- /profiles does not expose all profiles
- User cannot access another user's chat
- User cannot download another user's file
- Guest cannot bypass limits by editing localStorage
- CORS is not wildcard in production
- .env is not committed

Existing features:
- Normal chat
- Code Studio
- Voice
- Memory
- Settings
- PDF reading
- DOCX to PDF
- Image upload
- Search
- Weather
- Calculator
- Download button
- Chat persistence
- Code chat persistence

After testing:
- Tell me what passed
- Tell me what failed
- Tell me what was fixed
```

---

# Phase 14 — Deployment preparation

## Goal

Prepare for Vercel + Render + Supabase deployment.

## Codex prompt

```text
Implement Phase 14 only: deployment preparation.

Deployment target:
- Frontend: Vercel
- Backend: Render
- Database: Supabase Postgres
- AI APIs: Groq + Gemini/Groq vision fallback

Tasks:
1. Verify frontend API base URL uses env variable.
2. Verify backend uses env variables only.
3. Add deployment instructions.
4. Add Render start command.
5. Add requirements.txt updates.
6. Add health check endpoint documentation.
7. Confirm .env files are ignored.
8. Confirm no secrets are hardcoded.
9. Confirm database uses Supabase DATABASE_URL.
10. Confirm generated/private files are ignored.

After editing:
- Give me exact Vercel setup steps.
- Give me exact Render setup steps.
- Give me exact Supabase env variables.
- Give me final test checklist.
```

---

# Git instructions after every successful phase

After each working phase, run:

```powershell
git status --short
git add .
git commit -m "Describe the completed phase"
```

Before commit, verify secrets are not staged:

```powershell
git diff --cached --name-only | Select-String -Pattern '(^|/)\.env$|backend/.env|frontend/.env'
```

If that command shows anything, stop.

---

# Emergency rollback commands

If a phase breaks the project:

```powershell
git status
git restore .
```

If you already committed broken changes:

```powershell
git log --oneline
git revert COMMIT_ID
```

Do not delete project files manually unless you know exactly what they are.
