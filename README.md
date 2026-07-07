# 🚀 AIGrowthEngine

A self-hosted growth engine for small businesses. Automates the hard parts of
finding customers and growing your social media presence — built originally to
solve customer outreach for the [AImoney](https://github.com/mikepitts25/AImoney)
AI Income Blueprint project, but configurable for any business.

## What it does

| Feature | How it helps |
|---|---|
| 🔎 **Lead Finder** | Scans Reddit and Hacker News (free public APIs, no keys needed) for people actively asking about topics your business solves. Every result is scored 0–100 for buying intent. |
| 👥 **Leads CRM** | A simple pipeline: `new → contacted → responded → customer`. Notes, filtering, and CSV export included. |
| ✨ **Outreach Studio** | One click drafts a personalized, value-first reply or DM for any lead — AI-powered when a provider is configured, with solid templates as fallback. You review and send it yourself, keeping outreach authentic and within platform rules. |
| ✍️ **Content Studio** | Turn one topic into platform-tailored posts for X/Twitter, LinkedIn, Reddit, and Instagram. Edit, copy, schedule reminders, and track draft → posted. |
| ⚙️ **Business profile** | One profile (what you sell, who it's for, your tone, keywords) powers everything. Ships pre-configured for the AI Income Blueprint. |

## Quick start

```bash
python3 -m pip install -r requirements.txt   # use `py -m pip` on Windows
python3 -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000 — that's it. Data is stored in a local SQLite
database (`data/growth.db`).

### Enable AI generation (optional but recommended)

Any LLM works. Open **Settings → 🤖 AI Provider**, pick a provider, set a
model and API key, and hit **Test connection**:

| Provider | Notes |
|---|---|
| Anthropic (Claude) | Default. Also picks up `ANTHROPIC_API_KEY` from the environment — get one at platform.claude.com |
| OpenAI / Google Gemini / OpenRouter / Groq | Paste an API key (env vars `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY` also work) |
| Ollama | Free, local, no key — install from ollama.com, `ollama pull llama3.2`, done |
| Custom | Any OpenAI-compatible endpoint (LM Studio, Together, DeepSeek, vLLM…) — set the base URL |

With a provider configured, outreach drafts and social posts are AI-generated
and personalized to each lead and your business profile. Without one, the app
falls back to built-in templates and everything still works. Keys are stored
in the local SQLite database (`data/`, gitignored) — never in the repo.

## Typical workflow

1. **Settings** — confirm your business profile and keywords (pre-seeded for AImoney).
2. **Find Leads** — run discovery; high-intent posts land in your pipeline sorted by score.
3. **Leads** — click *✨ Draft outreach* on a hot lead, tweak the draft, post/send it yourself, mark it *contacted*.
4. **Content Studio** — generate a batch of posts from one topic, copy each to its platform, mark *posted*.
5. **Dashboard** — watch leads move down the funnel to *customer*.

## Design notes

- **No auto-posting / auto-DMing by design.** The app drafts; you send. This keeps outreach genuine, avoids spam-bot bans, and respects community rules (especially Reddit's).
- **No API keys required for discovery** — Reddit's public JSON endpoints and the Hacker News Algolia API are used respectfully at low volume.
- Backend: FastAPI + SQLite. Frontend: vanilla JS + Tailwind (CDN) — no build step, same philosophy as the AImoney site.

## API

All functionality is also available as a JSON API (see `app/main.py`):
`/api/dashboard`, `/api/leads/discover`, `/api/leads`, `/api/leads/{id}/draft`,
`/api/content/generate`, `/api/posts`, `/api/settings`, `/api/leads/export.csv`.
