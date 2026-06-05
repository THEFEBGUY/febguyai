# FEBGUYAI_PROFESSIONAL_AI_UPGRADE_PLAN.md

## Purpose

This file is for Codex. Read this document completely before editing anything.

The goal is to upgrade FebGuyAI from a normal chatbot-style app into a professional, natural, emotionally aware AI assistant while preserving the existing working website.

This is not a full rewrite. This is a safe intelligence-layer and UI/UX upgrade.

---

## Core Rule For Codex

Do not rewrite the whole app.

Do not remove existing features.

Do not restructure the project unless absolutely necessary.

Before starting any phase, inspect the current files and report:

1. Exact files you will edit.
2. Exact functions/components you will touch.
3. Existing flows that could be affected.
4. How you will avoid breaking those flows.
5. Whether database changes are required.
6. Testing steps after implementation.

Wait for approval before editing.

---

## Current Known Files

Main files expected to be edited:

- `main.py`
- `App.jsx`
- `index.css`
- `.env` or `.env.example` only if model config variables need to be added

Avoid editing other files unless the current architecture clearly requires it.

---

## Existing Features That Must Not Break

These features must keep working after every phase:

- Normal chat
- Streaming chat
- Voice mode
- File upload
- PDF/DOCX/TXT/image processing
- RAG/document context
- Search
- Calculator/tool responses
- Chat history
- Auth/account/guest/profile flow
- Guest limits
- Memory
- Code Studio
- Generated file downloads
- Citations/document hits
- Settings panel
- Mobile responsive UI

If any phase risks breaking these, stop and explain before editing.

---

# High-Level Upgrade Vision

FebGuyAI should feel like a 2026 professional AI website:

- More intelligent
- Less repetitive
- More natural
- More emotionally aware
- Better at understanding intent
- Better at choosing the right model
- Better UI controls for response style
- Better “thinking” and generation experience
- More premium-looking interaction design

Target experience:

> User asks casually, FebGuyAI replies casually.
> User asks serious work, FebGuyAI becomes structured and deep.
> User sounds frustrated, FebGuyAI becomes calm and helpful.
> User asks coding, FebGuyAI behaves like a senior engineer.
> User asks creative work, FebGuyAI becomes expressive and human.

---

# Recommended Model Strategy

## Main recommended deployment setup

Use Groq or compatible OpenAI-style provider.

Recommended `.env` model variables:

```env
FAST_MODEL=llama-3.1-8b-instant
SMART_MODEL=llama-3.3-70b-versatile
DEEP_MODEL=llama-3.3-70b-versatile
CODE_MODEL=qwen/qwen3-32b
VOICE_CHAT_MODEL=llama-3.1-8b-instant
CHAT_MODEL=llama-3.3-70b-versatile
RESPONSE_REFINER_MODEL=llama-3.1-8b-instant
ENABLE_RESPONSE_REFINER=true
```

## Model roles

### FAST_MODEL
Use for:
- greetings
- thanks
- simple questions
- quick summaries
- low-cost guest messages
- title generation
- response refinement if needed

### SMART_MODEL
Use for:
- normal chat
- study help
- explanation
- file Q&A
- natural emotional responses
- general FebGuyAI assistant replies

### DEEP_MODEL
Use for:
- complex reasoning
- research-style answers
- architecture planning
- debugging strategy
- long-form answers
- high-quality “pro” responses

### CODE_MODEL
Use for:
- Code Studio
- debugging
- code generation
- refactoring
- project explanations
- backend/frontend implementation guidance

### VISION_MODEL
Keep existing vision model logic unless there is a clear bug.

---

# Response Modes To Add

Add a frontend-selected `response_mode` field.

Supported modes:

```text
balanced
deep
creative
teacher
coding
human
```

## Meaning of each mode

### balanced
Default. Natural, helpful, not too long.

### deep
More strategic, detailed, step-by-step. Good for projects and serious work.

### creative
More expressive, emotionally engaging, good for writing, naming, content, branding.

### teacher
Simple explanation, examples, beginner-friendly, patient.

### coding
Senior-engineer style. Precise, practical, code-aware, avoids vague advice.

### human
Warm, conversational, less formal, suitable for casual chat.

---

# Backend Upgrade Plan

## Phase 0 — Safety Inspection Only

Do not edit code.

Codex must inspect:

- `main.py`
- `App.jsx`
- `index.css`

Find these areas:

In `main.py`:
- model config variables near existing model constants
- request schemas/forms for chat and chat-stream
- prompt builder function
- intent/route classifier functions
- streaming response function
- `call_text_model`
- `stream_text_model`
- `groq_chat_completion`
- `stream_groq_chat_completion`
- voice chat endpoint
- Code Studio endpoint if model routing touches code

In `App.jsx`:
- message state
- settings state
- `sendMessage`
- streaming request builder
- composer form
- settings panel
- voice modal/settings area
- Code Studio mode logic

In `index.css`:
- `.input-dock`
- `.top-bar`
- `.workspace-status`
- settings panel styles
- mobile responsive sections
- any existing button/chip styles that can be reused

Deliverable for Phase 0:
- List exact functions/components to edit.
- Confirm whether DB migration is needed.
- Confirm smallest safe implementation plan.
- Wait for approval.

---

## Phase 1 — Model Tier Configuration

Goal:
Add professional model tiers without changing app behavior yet.

### Backend tasks

In `main.py`, add safe env variables near existing model constants:

```python
FAST_MODEL = os.getenv("FAST_MODEL", "llama-3.1-8b-instant")
SMART_MODEL = os.getenv("SMART_MODEL", os.getenv("CHAT_MODEL", "llama-3.3-70b-versatile"))
DEEP_MODEL = os.getenv("DEEP_MODEL", SMART_MODEL)
RESPONSE_REFINER_MODEL = os.getenv("RESPONSE_REFINER_MODEL", FAST_MODEL)
ENABLE_RESPONSE_REFINER = os.getenv("ENABLE_RESPONSE_REFINER", "false").lower() == "true"
```

Keep existing variables working:
- `DEFAULT_MODEL`
- `CODE_MODEL`
- `VISION_MODEL`
- `VOICE_CHAT_MODEL`

Do not remove existing config.

### Add model selection helper

Add a helper like:

```python
def select_chat_model(
    response_mode: str,
    intent: str,
    answer_mode: str,
    has_file_context: bool = False,
    has_search_context: bool = False,
    has_images: bool = False,
    is_voice: bool = False,
) -> str:
    ...
```

Rules:
- If images exist, use existing vision model logic.
- If coding mode or code intent, use `CODE_MODEL`.
- If response_mode is `deep`, use `DEEP_MODEL`.
- If response_mode is `coding`, use `CODE_MODEL`.
- If voice and short/casual, use `VOICE_CHAT_MODEL` or `FAST_MODEL`.
- Otherwise use `SMART_MODEL`.

### Safety
- If model variable is empty, fallback to `DEFAULT_MODEL`.
- Do not hard-fail the request because a new env var is missing.

### Test
- Existing chat still works.
- Existing streaming still works.
- Existing voice still works.
- Existing Code Studio still works.

---

## Phase 2 — Response Mode API Field

Goal:
Allow frontend to send response mode safely.

### Backend tasks

Add `response_mode` support to:

- `/chat`
- `/chat-stream`
- voice endpoint if applicable
- request models if used

For form endpoints, add:

```python
response_mode: str = Form("balanced")
```

For JSON request models, add:

```python
response_mode: str = "balanced"
```

Add normalizer:

```python
VALID_RESPONSE_MODES = {"balanced", "deep", "creative", "teacher", "coding", "human"}

def normalize_response_mode(value: str | None) -> str:
    clean = str(value or "balanced").strip().lower()
    return clean if clean in VALID_RESPONSE_MODES else "balanced"
```

Use normalized value only.

### Important
Do not confuse existing `answer_mode` with new `response_mode`.

- `answer_mode` = internal route/classification
- `response_mode` = user-selected style/intelligence mode

Both can exist together.

### Test
- Sending no response_mode should behave like before.
- Sending invalid response_mode should fallback to balanced.
- Streaming still returns metadata normally.

---

## Phase 3 — Emotional Tone Detector

Goal:
Make FebGuyAI react more naturally.

### Backend tasks

Add a lightweight deterministic function first. Do not call extra LLM for this in Phase 3.

Example:

```python
def detect_emotional_tone(message: str) -> dict[str, str]:
    ...
```

Return:

```python
{
  "tone": "neutral | frustrated | excited | confused | urgent | casual | sad | confident",
  "instruction": "short style instruction for prompt"
}
```

Suggested detection:
- frustrated: "not working", "error", "broken", "why", "again", "bro", "stuck"
- urgent: "fast", "quick", "now", "urgent", "deadline"
- confused: "i don't understand", "what mean", "how", "explain"
- excited: "great", "nice", "awesome", "let's go"
- casual: "bro", "yo", "bhai", "hey", "sup"
- sad/stressed: "tired", "worried", "scared", "failed"

### Prompt injection
Pass emotional tone into prompt builder.

The prompt should include:
- detected tone
- how to respond
- avoid overdoing emotion
- do not fake feelings
- be warm and practical

Example instruction:

```text
Emotional tone detected: frustrated.
Respond calmly, directly, and practically. Acknowledge the difficulty briefly, then solve the problem.
```

### Safety
- Do not make medical/mental-health assumptions.
- Do not claim the AI has real emotions.
- The AI can sound warm, but should not pretend to be human.

---

## Phase 4 — Professional Prompt Builder Upgrade

Goal:
Reduce repetitive/basic answers.

### Backend tasks

Improve prompt builder with a structured “FebGuy Intelligence Contract”.

Include:

1. User intent
2. Response mode
3. Emotional tone
4. Relevant memory
5. Conversation context
6. File/search/tool context
7. Output style rules
8. Anti-repetition rules
9. Depth rules
10. Safety/factuality rules

### Add response mode style instructions

Example:

```python
RESPONSE_MODE_INSTRUCTIONS = {
    "balanced": "...",
    "deep": "...",
    "creative": "...",
    "teacher": "...",
    "coding": "...",
    "human": "...",
}
```

### Anti-repetition rules

Add rules like:

- Do not start every answer with “Sure”.
- Do not repeat the same sentence structure.
- Do not overuse “Here’s”.
- Do not always end with “Let me know”.
- Do not force “Next steps” for casual chat.
- Avoid generic motivational lines.
- Be specific to the user’s project.

### Naturalness rules

- Use casual language when the user is casual.
- Use professional structure when the task is serious.
- Give direct answers first.
- For simple questions, answer simply.
- For project/coding tasks, be precise and actionable.
- Show confidence when the evidence is clear.
- Mention uncertainty honestly when needed.

### Test
Try prompts:
- “yo bro”
- “why my pdf upload not working”
- “make FebGuyAI more professional”
- “explain this code”
- “write a college project conclusion”
- “what should I tell Codex now”

Compare output quality before and after.

---

## Phase 5 — Optional Response Critic / Refiner Pass

Goal:
Make responses feel more polished without changing tool logic.

### Backend tasks

Add optional function:

```python
def refine_response_if_enabled(
    original_response: str,
    user_message: str,
    response_mode: str,
    emotional_tone: dict,
    intent: str,
) -> str:
    ...
```

Use only when:
- `ENABLE_RESPONSE_REFINER=true`
- response is not a direct tool result
- response is not an error
- response is not too long
- not streaming OR apply after full stream only if architecture supports it safely

### Important streaming note

Do not break streaming.

If current streaming sends chunks directly to frontend, do not force a refiner into streaming in the first implementation.

Safe options:

Option A:
- Use refiner only for non-stream `/chat` and voice.

Option B:
- For streaming, skip refiner initially.

Option C:
- Later implement “draft first, refine, then stream refined text” but this changes UX latency and should be separate.

Recommended:
- Phase 5: refiner for non-stream/voice only.
- Phase 8 or later: streaming refiner upgrade if needed.

### Refiner prompt should say

- Improve naturalness.
- Remove robotic phrasing.
- Remove repetition.
- Preserve facts, code, citations, links, file references.
- Do not add unsupported claims.
- Do not change meaning.
- Keep same language as user unless task requires otherwise.

### Safety
If refiner fails, return original response.

Never let refiner delete citations/tool output metadata.

---

## Phase 6 — Frontend Response Mode UI

Goal:
Give user simple premium controls without cluttering the app.

### Frontend tasks in `App.jsx`

Add state:

```jsx
const [responseMode, setResponseMode] = useState("balanced");
```

Persist optionally:
- localStorage
- or existing settings if easy and safe

Add UI near composer or top bar:

Options:
- Balanced
- Deep
- Creative
- Teacher
- Coding
- Human

Recommended UI:
A small pill/dropdown above or inside composer, not a large panel.

Example labels:
- Balanced
- Deep
- Creative
- Teacher
- Code
- Human

When sending chat:
- include `response_mode` in FormData for `/chat-stream`
- include `response_mode` in JSON payload if non-stream endpoint exists
- include in voice request if supported

### Important
Do not show coding mode in normal chat if Code Studio already handles coding separately, unless useful.

Better:
- Normal workspace: balanced/deep/creative/teacher/human
- Code Studio: coding/deep/balanced

### Test
- Mode changes without refreshing.
- Chat request includes selected response_mode.
- Voice still works.
- File upload still works.
- Code Studio still works.

---

## Phase 7 — UI/UX Premium Polish

Goal:
Make FebGuyAI feel like a high-end 2026 AI site.

### Frontend UI improvements

Add:

1. Model/status pill
   - “Smart”
   - “Deep”
   - “Fast”
   - “Code”
   - Do not expose raw model names unless in settings/dev mode.

2. Better thinking states
   Instead of only:
   - “Thinking...”

   Use:
   - Understanding request
   - Checking context
   - Selecting model
   - Writing response

3. Regenerate style actions
   Under AI response:
   - Make deeper
   - Make simpler
   - More professional
   - More human
   - Code only

These can send a follow-up instruction using existing chat flow. Do not create complex new backend endpoints in this phase unless necessary.

4. Better empty screen starter cards
   Suggested cards:
   - Build with FebGuy
   - Study smarter
   - Analyze files
   - Code Studio
   - Voice assistant
   - Research with sources

5. Better response readability
   - Slightly wider message area
   - Improved code block spacing
   - Better table overflow
   - Better mobile composer layout

### CSS tasks in `index.css`

Add styles for:

- `.response-mode-bar`
- `.response-mode-chip`
- `.response-mode-chip.active`
- `.thinking-steps`
- `.thinking-step`
- `.ai-quality-actions`
- `.model-status-pill`

Reuse existing colors and glass style.

Do not redesign the entire CSS.

---

## Phase 8 — Testing And Hardening

Goal:
Confirm nothing broke.

### Backend tests

Manually test:

1. Guest chat
2. Account/profile chat
3. Streaming chat
4. Chat with file upload
5. Chat with image upload
6. Search query
7. Calculator/direct tool response
8. Voice query
9. Code Studio prompt
10. Code file upload
11. Chat history persistence
12. Memory panel/settings
13. Generated file download
14. Guest limits

### Frontend tests

Check:

1. Desktop layout
2. Mobile layout
3. Response mode selector
4. Composer send button
5. Voice button
6. Attach button
7. Stop generation
8. Regenerate/action buttons
9. Settings panel
10. Code Studio workspace switch

### Quality tests

Ask FebGuyAI:

```text
yo bro
```

Expected:
- Casual, short, natural.

```text
my ai responses feel repetitive and basic
```

Expected:
- Specific diagnosis, practical plan.

```text
explain this like teacher
```

Expected:
- Simple, beginner-friendly.

```text
debug this react code
```

Expected:
- Senior coding help.

```text
make this more emotional
```

Expected:
- Creative/human tone without sounding fake.

---

# Deployment Safety For 10–20 Users

## Cost control

Add or confirm:

- guest limits
- per-minute rate limits
- max message length
- upload size limit
- context clipping
- do not send full chat history every time
- use FAST_MODEL for simple requests
- use SMART_MODEL only when needed
- use DEEP_MODEL only when selected or required

## Recommended production defaults

```env
ENABLE_RESPONSE_REFINER=false
CHAT_MODEL=llama-3.3-70b-versatile
SMART_MODEL=llama-3.3-70b-versatile
DEEP_MODEL=llama-3.3-70b-versatile
FAST_MODEL=llama-3.1-8b-instant
CODE_MODEL=qwen/qwen3-32b
VOICE_CHAT_MODEL=llama-3.1-8b-instant
```

Keep response refiner disabled at first deployment if cost/latency matters.

Enable later after testing:

```env
ENABLE_RESPONSE_REFINER=true
```

---

# What Not To Do

Do not:

- rewrite the whole backend
- replace all prompts at once without testing
- remove existing `SYSTEM_PROMPT`
- remove current search/RAG/tool logic
- remove current voice logic
- change database schema unless absolutely necessary
- make response_mode required
- break old clients that do not send response_mode
- expose API keys to frontend
- hardcode secret keys
- send entire database memory into prompt
- use Deep model for every tiny greeting
- use response refiner on direct tool errors
- use response refiner on file download responses
- change auth/session ownership logic
- remove guest usage limits
- remove upload validation
- remove request size limits

---

# Approval Gates

Codex must stop after each phase and report:

1. What changed.
2. Files edited.
3. Functions/components edited.
4. Tests performed.
5. Any risk found.
6. Whether it is safe to continue.

Do not continue to the next phase without approval.

---

# Suggested Commands To Give Codex

## Start Phase 0

```text
Read FEBGUYAI_PROFESSIONAL_AI_UPGRADE_PLAN.md completely.

Start Phase 0 only.

Inspect main.py, App.jsx, and index.css.

Do not edit anything.

List exact files/functions/components you will modify for Phase 1 to Phase 2.

Tell me whether DB migration is needed.

Wait for my approval before editing.
```

## Start Phase 1

```text
Start Phase 1 only.

Add model tier config and safe model selection helper.

Do not change frontend yet.

Keep existing chat, streaming, voice, files, search, RAG, auth, history, and Code Studio working.

After changes, summarize files/functions edited and tests I should run.
```

## Start Phase 2

```text
Start Phase 2 only.

Add response_mode support to backend request handling with safe fallback to balanced.

Do not change UI yet.

Do not break existing requests that do not send response_mode.

After changes, summarize exactly what changed.
```

## Start Phase 3

```text
Start Phase 3 only.

Add deterministic emotional tone detector and pass it into prompt building.

Do not call an extra LLM for tone detection.

Keep behavior safe and non-creepy.

After changes, summarize tests.
```

## Start Phase 4

```text
Start Phase 4 only.

Upgrade the prompt builder with response mode instructions, emotional tone instructions, and anti-repetition rules.

Do not remove existing tool/search/RAG/file context behavior.

After changes, show example before/after style expectations.
```

## Start Phase 5

```text
Start Phase 5 only.

Add optional response refiner controlled by ENABLE_RESPONSE_REFINER.

Do not break streaming.

If streaming refiner is risky, skip it and apply refiner only to non-stream/voice responses.

Fallback to original response if refiner fails.
```

## Start Phase 6

```text
Start Phase 6 only.

Add frontend response mode UI in App.jsx and required styles in index.css.

Send response_mode with chat requests.

Keep composer, voice, attach, stop generation, file upload, and Code Studio working.
```

## Start Phase 7

```text
Start Phase 7 only.

Add premium UI polish: model/status pill, better thinking states, response action chips, and improved starter cards.

Do not redesign the entire app.

Keep responsive layout working.
```

## Start Phase 8

```text
Start Phase 8 only.

Run a final safety review.

Check backend/frontend flows and give me a deployment checklist for 10–20 users.

Do not add new features in this phase unless fixing a bug from earlier phases.
```

---

# Final Goal

After all phases, FebGuyAI should feel:

- smarter
- warmer
- more human
- more professional
- less repetitive
- better at coding
- better at study/project help
- better at emotional tone
- visually more premium
- still stable and safe for deployment

The upgrade must improve the brain without destroying the body.
