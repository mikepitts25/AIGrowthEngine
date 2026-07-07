# 🚀 AIGrowthEngine

A self-hosted growth engine for small businesses. Automates the hard parts of
finding customers and growing your social media presence — built originally to
solve customer outreach for the [AImoney](https://github.com/mikepitts25/AImoney)
AI Income Blueprint project, but configurable for any business.

## What it does

AIGrowthEngine drives **two income streams from one dashboard**:
**course sales** (find people who want to make money with AI, grow your
audience) and an **AI agency** (find local businesses that need an AI
receptionist and pitch them). Ships pre-configured for the
[AImoney](https://github.com/mikepitts25/AImoney) project and Colibri Code.

| Feature | How it helps |
|---|---|
| 🔎 **Find Leads (course)** | Scans **Bluesky, Hacker News, and Reddit** for people asking about making money with AI. Bluesky and HN need no keys; Reddit uses OAuth when `REDDIT_CLIENT_ID`/`SECRET` are set. Scored 0–100 for buying intent. |
| 🏢 **Agency Clients** | Finds local home-service businesses (HVAC, plumbing, roofing…) via **OpenStreetMap, Google Places, and Yelp**, scored for "missed-call pain" — the prospects your AI-receptionist service is built for. |
| 🔬 **Lead enrichment** | Probes a business's website: pulls owner **email addresses**, detects online booking, flags dead sites — and re-scores pain automatically. |
| 🧠 **AI qualification** | One click scores any lead's fit 0–100 with a rationale and the sharpest opener angle. |
| ✨ **Outreach Studio** | Drafts personalized outreach — reply/DM for course leads; **email, SMS, call-prep sheet, or a full 3-email sequence** for agency leads. AI-powered with template fallback. You send it yourself. |
| ⚡ **Bulk draft** | Draft outreach for the top 10 uncontacted leads in one click. |
| 🖨 **Call sheet** | Printable daily dial list at `/callsheet` — phone, email, pain signals, opening script. |
| ✍️ **Content Studio** | One topic → platform-tailored posts; **💡 topic ideas** and a **🗓 content calendar** that auto-schedules a whole week. |
| ⏰ **Follow-up queue** | Next-action + due date per lead; the dashboard surfaces what's due today. |
| 🛸 **Autopilot** | Background scheduler re-runs discovery + enrichment for both course and agency leads every N hours — hands-free pipeline. |
| 📊 **Dashboard** | Funnel, weekly outreach velocity, today's call targets, follow-ups due, breakdowns by trade/source, autopilot status. |
| ⚙️ **Profiles** | Separate course profile and agency profile power everything; both pre-configured. |

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
