# 🚀 AIGrowthEngine

A self-hosted growth engine for small businesses. Automates the hard parts of
finding customers and growing your social media presence — built originally to
solve customer outreach for the [AImoney](https://github.com/mikepitts25/AImoney)
AI Income Blueprint project, but configurable for any business.

## What it does

AIGrowthEngine drives **two income streams from one dashboard**:
**course sales** (find people who want to make money with AI, grow your
audience) and an **AI agency** (find contractors who fit the $1M-3M ICP and pitch
the staffed front desk — Google Ask-for-Me readiness plus a bilingual overnight desk). Ships pre-configured for the
[AImoney](https://github.com/mikepitts25/AImoney) project and Colibri Code.

| Feature | How it helps |
|---|---|
| 🔎 **Find Leads (course)** | Scans **Bluesky, Hacker News, and Reddit** for people asking about making money with AI. Bluesky and HN need no keys; Reddit uses OAuth when `REDDIT_CLIENT_ID`/`SECRET` are set. Scored 0–100 for buying intent. |
| 🏢 **Agency Clients** | Finds local home-service businesses (HVAC, plumbing, roofing…) via **OpenStreetMap, Google Places, and Yelp**, scored for **ICP fit** — ≈$1M-3M revenue (30-400 reviews), has a website, gaps in evening/weekend cover. Deliberately deprioritises the tiny no-website shops: they buy a $29 self-serve tool. |
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


## Positioning note — August 2026

The agency side of this tool was repositioned on 10 Aug 2026 after a market
re-check. Three things changed and the defaults now reflect them:

1. **Do not pitch "never miss a call."** That is the headline on Goodcall
   ($79/mo), Rosie ($49/mo) and Allo (from $18/mo), and Zoom shipped a standalone
   AI receptionist at $29.99/mo on 9 Jul 2026. Leading with it anchors you at
   their price. Lead instead with **Google "Ask for Me"** — Google's AI now calls
   local businesses for quotes, home repair included — and with the **bilingual
   overnight desk**, which a self-serve tool cannot supply at all.
2. **Price against a hire, never against an AI tool.** Only ~10% of SMBs spend
   $250+/mo on anything labelled AI (Bluevine, 15 Jul 2026). The same contractor
   pays $3,300-4,600/mo fully loaded for an in-house CSR. The default profile
   carries those comparison figures so generated outreach uses them.
3. **The ICP narrowed** to ~$1M-3M operators who are *not* on a bundled FSM AI
   tier, in Mountain/Pacific and Spanish-heavy metros. Scoring was inverted
   accordingly: a website is now a positive signal, and the review band moved to
   30-400. Sub-30-review shops score low on purpose.

Full reasoning lives in the AImoney repo's `agency-plan.html` under
**Command Center → What You Actually Sell** and **Market Reality Check**.
