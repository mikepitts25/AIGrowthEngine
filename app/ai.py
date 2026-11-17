"""AI-powered content and outreach generation, with template fallbacks.

Works with any LLM provider configured in Settings (Anthropic, OpenAI,
Gemini, OpenRouter, Groq, local Ollama, or a custom OpenAI-compatible
endpoint) — see app/llm.py. With no provider configured the app still
works using templates.
"""
import json
import re

from . import llm

PLATFORM_SPECS = {
    "x": "X/Twitter post, max 280 characters, punchy hook first line, 1-2 hashtags max",
    "linkedin": "LinkedIn post, 100-200 words, professional but personal, line breaks between ideas, end with a question to drive comments",
    "reddit": "Reddit post (title + body), value-first and non-promotional in tone — Reddit hates ads. Share genuine insight; mention the product only if organic",
    "instagram": "Instagram caption, 50-125 words, engaging hook, emoji-friendly, 5-8 hashtags at the end",
}


def ai_available() -> bool:
    return llm.available()


def _profile_context(profile: dict) -> str:
    return (
        f"Business: {profile.get('business_name', '')}\n"
        f"Website: {profile.get('website', '')}\n"
        f"What it sells: {profile.get('description', '')}\n"
        f"Target audience: {profile.get('audience', '')}\n"
        f"Voice/tone: {profile.get('tone', '')}"
    )


# ---------------------------------------------------------------- outreach

def draft_outreach(profile: dict, lead: dict, channel: str) -> tuple[str, str]:
    """Return (content, generated_by). Personalizes to the lead's post."""
    text = llm.complete(
        system=(
            "You write authentic, helpful outreach for a small business. "
            "Rules: lead with genuine value specific to what the person posted; "
            "never open with a pitch; keep it short; sound human, not corporate; "
            "one soft mention of the product at most, and only where it truly helps. "
            "Respect community norms — on Reddit especially, be a helpful member first.\n\n"
            + _profile_context(profile)
        ),
        user=(
            f"Draft a {channel} reply/message to this person. "
            f"Return ONLY the message text, no preamble.\n\n"
            f"Where they posted: {lead.get('community', '')}\n"
            f"Their post title: {lead.get('title', '')}\n"
            f"Their post text: {lead.get('snippet', '') or '(no body text)'}"
        ),
        max_tokens=1024,
    )
    if text:
        return text, "ai"

    # Template fallback
    name = profile.get("business_name", "our guide")
    site = profile.get("website", "")
    content = (
        f"Hey! Saw your post about \"{lead.get('title', '')[:80]}\" — great question.\n\n"
        f"A few things that helped me/people I know get started: pick ONE AI tool and get genuinely "
        f"good at it before chasing the next shiny thing, start with a service you can sell this week "
        f"(writing, images, automation), and reinvest early income into better tooling.\n\n"
        f"I put together a full walkthrough of this in {name}"
        + (f" ({site})" if site else "")
        + " if you want the step-by-step version. Happy to answer questions here either way!"
    )
    return content, "template"


# ---------------------------------------------------------------- agency outreach

QUALIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "fit_score": {"type": "integer"},
        "rationale": {"type": "string"},
        "opener_angle": {"type": "string"},
    },
    "required": ["fit_score", "rationale", "opener_angle"],
    "additionalProperties": False,
}


def qualify_lead(agency_profile: dict, lead: dict) -> dict | None:
    """AI fit-scoring: 0-100 fit for the agency's service, a one-line
    rationale, and the sharpest opener angle. None if AI is unavailable
    or the call fails."""
    gaps = _lead_gaps(lead)
    text = llm.complete(
        system=(
            "You qualify sales leads for a small AI agency. Score how good a fit "
            "each business is for the service (0-100), where high fit = an owner-run "
            "service business at $1M-3M revenue with years of past customers (30-400 Google "
            "reviews is a good proxy) that runs Jobber or Housecall Pro - i.e. it has a customer "
            "list and open estimates we can work, and an office that can book the replies. Low "
            "fit: brand-new shops (no customer base), ServiceTitan-size operations with their own "
            "marketing team, supply houses, wholesalers, franchises with call "
            "centers, and non-service businesses. Be blunt.\n\n"
            + _agency_context(agency_profile)
        ),
        user=(
            "Qualify this lead.\n\n"
            f"Business: {lead.get('title', '')}\n"
            f"Trade: {lead.get('vertical', '')}\n"
            f"City: {lead.get('city') or lead.get('community', '')}\n"
            f"Phone: {lead.get('phone') or 'none listed'}\n"
            f"Website: {lead.get('website') or 'NONE'}\n"
            f"Email: {lead.get('email') or 'none found'}\n"
            f"Details: {lead.get('snippet', '')}\n"
            f"Signals: {'; '.join(gaps) or 'none'}"
        ),
        max_tokens=1024,
        json_schema=QUALIFY_SCHEMA,
    )
    if not text:
        return None
    data = llm.parse_json_response(text)
    if not data or "fit_score" not in data:
        return None
    try:
        data["fit_score"] = max(0, min(100, int(data["fit_score"])))
    except (TypeError, ValueError):
        return None
    return data


AGENCY_CHANNEL_SPECS = {
    "email": (
        "a cold email: subject line on the first line as 'Subject: …', then a 70-110 word body. "
        "Open with their dormant customers (people who haven't booked in a year), not with AI. "
        "Offer: a short seasonal note sent from THEIR own Jobber/Housecall Pro account, which "
        "they approve word for word, in English and Spanish, and they pay $75 per booked job, "
        "nothing up front, counted from their own job board. CTA: a 15-minute screenshare to "
        "count their dormant customers. Never invent statistics, response rates or client results"
    ),
    "sms": (
        "a first-touch SMS to the OWNER (a business, not a consumer), max 300 characters: who "
        "you are, the dormant-customer idea in one line, '$75 per booked job, nothing up front', "
        "and an easy yes/no question about counting them together. No links, never lead with 'AI'"
    ),
    "callprep": (
        "a cold-call prep sheet in plain text with these sections: LEAD SNAPSHOT (their details "
        "and signals), OPENING (word-for-word, ~10 seconds: 'how many customers do you think "
        "you've got who haven't booked in the last year?'), OFFER (seasonal note from their own "
        "account, they approve it, $75 per booked job, nothing up front, counted in their job "
        "board), SEASONAL ANGLE (the right campaign for this month and trade), LIKELY OBJECTIONS "
        "(4 with word-for-word answers: 'we already send emails' / 'I don't want to spam my "
        "customers' / 'what's the catch' / 'how do you know who booked because of you'), and "
        "CLOSE (two-option ask for a 15-minute Dormant-Customer Count screenshare)"
    ),
    "sequence": (
        "a 3-email sequence in plain text, labeled 'EMAIL 1 — Day 0', 'EMAIL 2 — Day 4', "
        "'EMAIL 3 — Day 10', each with its own Subject: line. Email 1: dormant customers + the "
        "pay-per-booked-job offer + 15-min count. Email 2: short, this season's campaign idea "
        "for their trade. Email 3: brief, warm break-up ('reply count if you ever want the "
        "number'). Never guilt-trip, never invent results or statistics"
    ),
}


def _agency_context(profile: dict) -> str:
    return (
        f"Agency: {profile.get('agency_name', '')}\n"
        f"Founders: {profile.get('founders', '')}\n"
        f"Service: {profile.get('service', '')}\n"
        f"Pricing: {profile.get('pricing', '')}\n"
        f"Voice/tone: {profile.get('tone', '')}"
    )


# How the trade reads as an adjective in prose ("plumbing companies").
TRADE_ADJECTIVES = {
    "hvac": "HVAC", "plumber": "plumbing", "roofer": "roofing",
    "electrician": "electrical", "landscaping": "landscaping", "cleaning": "cleaning",
}


def _lead_gaps(lead: dict) -> list[str]:
    try:
        reasons = json.loads(lead.get("meta") or "{}").get("score_reasons", [])
    except (json.JSONDecodeError, TypeError):
        return []
    # Internal qualification notes (e.g. "phone listed — cold-callable",
    # "pitch ...", "qualify size ...") aren't customer-facing gaps — don't
    # quote them in outreach.
    internal = ("cold-callable", "pitch", "qualify", "deprioritise", "check they",
                "target band", "email found", "add-on signal", "Booked-Job Desk lead")
    # Strip internal value tags like "(Morning Board value)" from what's left.
    return [re.sub(r"\s*\([^)]*value\)$", "", r) for r in reasons
            if not any(k in r for k in internal)]


_SEASONS = {
    "hvac": {11: "furnace safety checks before the first cold snap", 12: "maintenance-plan renewals before year end",
             1: "uneven heating and plan renewals", 2: "uneven heating and plan renewals",
             3: "AC tune-ups before the spring rush", 4: "AC tune-ups before the spring rush",
             5: "beat the first heatwave", 6: "beat the first heatwave", 7: "'running but not cooling?' repairs",
             8: "'running but not cooling?' repairs", 9: "furnace tune-ups before the cold", 10: "furnace tune-ups before the cold"},
}
_DEFAULT_SEASON = {11: "water heater flushes and pipe-freeze prep", 12: "water heater flushes and pipe-freeze prep",
                   1: "frozen-pipe follow-ups and panel checks", 2: "sump pump tests and panel checks",
                   3: "spring plumbing and outdoor-outlet checks", 4: "spring plumbing and outdoor-outlet checks",
                   5: "surge protection before storm season", 6: "surge protection before storm season",
                   7: "water heater age checks", 8: "generator and water heater checks",
                   9: "winterisation", 10: "winterisation and whole-home inspections"}


def _month_name() -> str:
    import datetime
    return datetime.date.today().strftime("%B")


def _seasonal_angle(vertical: str) -> str:
    import datetime
    m = datetime.date.today().month
    return _SEASONS.get(vertical, _DEFAULT_SEASON).get(m, _DEFAULT_SEASON[m])


def draft_agency_outreach(profile: dict, lead: dict, channel: str) -> tuple[str, str]:
    """Draft outreach to a local business for agency services.
    channel: email | sms | callprep. Returns (content, generated_by)."""
    spec = AGENCY_CHANNEL_SPECS.get(channel, AGENCY_CHANNEL_SPECS["email"])
    gaps = _lead_gaps(lead)
    business = lead.get("title", "the business")
    vertical = lead.get("vertical", "home service")
    trade = TRADE_ADJECTIVES.get(vertical, vertical or "home service")
    city = lead.get("city") or lead.get("community", "")

    text = llm.complete(
        system=(
            "You write B2B sales outreach for a two-person agency that runs the Booked-Job "
            "Desk for home service businesses (HVAC, plumbing, electrical, roofing): win-back "
            "campaigns to the shop's own dormant customers, follow-up on open estimates and review "
            "requests, sent from the shop's own Jobber/Housecall Pro, approved by the owner, paid "
            "per booked job. Rules: plain-spoken and specific, never hypey; never lead with 'AI'; "
            "the money is in customers they already have; 'booked' is counted in THEIR job board; "
            "never invent statistics, response rates or client results. Sound like a fellow "
            "small-business owner, not a marketer.\n\n"
            + _agency_context(profile)
        ),
        user=(
            f"Draft {spec}.\n"
            f"Return ONLY the outreach text, no preamble.\n\n"
            f"Business: {business}\n"
            f"Trade: {vertical}\n"
            f"City: {city}\n"
            f"Phone: {lead.get('phone') or 'unknown'}\n"
            f"Website: {lead.get('website') or 'NONE'}\n"
            f"Details: {lead.get('snippet', '')}\n"
            f"Signals we noticed: {'; '.join(gaps) or 'none'}\n"
            f"Current month: {_month_name()} (pick the seasonal campaign for this trade)"
        ),
        max_tokens=1500,
    )
    if text:
        return text, "ai"

    # Template fallbacks — modeled on the Colibri Code sales materials, Part A (Nov 2026).
    name = profile.get("agency_name", "our agency")
    founders = profile.get("founders", "")
    first = founders.split("(")[0].split("&")[0].strip() or "Mike"
    season = _seasonal_angle(vertical)
    offer = ("a short seasonal note from your own account, which you approve word for word, "
             "and you pay $75 per job it books, nothing up front, counted in your own job board")

    if channel == "sms":
        content = (
            f"Hi, {first} with {name}. Most {trade} shops in {city} have hundreds of past customers "
            f"who haven't booked in a year. We win them back for you: $75 per booked job, nothing "
            f"up front. Want to count yours together in 15 min?"
        )
    elif channel == "callprep":
        rating_line = ""
        try:
            meta = json.loads(lead.get("meta") or "{}")
            if meta.get("rating"):
                rating_line = f"Rating: {meta['rating']}★ ({meta.get('review_count', '?')} reviews)\n"
        except (json.JSONDecodeError, TypeError):
            pass
        content = (
            f"📞 CALL PREP — {business} ({vertical}, {city})\n"
            f"{'=' * 50}\n"
            f"Phone: {lead.get('phone') or 'find via Google Business Profile'}\n"
            f"Website: {lead.get('website') or 'NONE'}\n"
            f"{rating_line}"
            f"Signals: {'; '.join(gaps) or 'check reviews count (customer base) before dialing'}\n\n"
            f"OPENING (10s): \"Hey [first name], it's {first} with {name}. Quick one — how many "
            f"customers do you think you've got in Jobber who haven't booked anything in the "
            f"last year?\"\n\n"
            f"OFFER: \"That's usually the cheapest work a shop can get. We send them {offer}.\"\n\n"
            f"SEASONAL ANGLE: {season}\n\n"
            f"OBJECTIONS:\n"
            f"- \"We already send emails\" → \"When did the last one go to people who haven't "
            f"booked in a year? Most shops have the tool and no time. We're the time.\"\n"
            f"- \"Don't want to spam customers\" → \"One short note, in your voice, you approve "
            f"it first, unsubscribe on every email. If you don't like it, it doesn't go.\"\n"
            f"- \"What's the catch?\" → \"We only get paid on jobs in your own board within 30 "
            f"days. You check our count; disputed rows are yours.\"\n"
            f"- \"How do you know it was you?\" → \"We match new jobs against the list we sent, "
            f"and anyone already scheduled is excluded up front.\"\n\n"
            f"CLOSE: \"Could we count them together on a 15-minute screenshare — Tuesday or "
            f"Thursday?\""
        )
    elif channel == "sequence":
        content = (
            f"EMAIL 1 — Day 0\n"
            f"Subject: Your customers from last year\n\n"
            f"Hi there,\n\n"
            f"Most {trade} shops in {city} have hundreds of customers who haven't booked in a "
            f"year — the cheapest work there is, because they already know you. We send them "
            f"{offer}.\n\n"
            f"Worth 15 minutes to count yours?\n\n"
            f"{first}, {name}\n\n"
            f"{'—' * 30}\n\n"
            f"EMAIL 2 — Day 4\n"
            f"Subject: The campaign that works this time of year\n\n"
            f"Quick one — for {trade} shops right now it's: {season}. Happy to count your dormant "
            f"customers on a 15-min screenshare and show you the draft.\n\n"
            f"{first}, {name}\n\n"
            f"{'—' * 30}\n\n"
            f"EMAIL 3 — Day 10\n"
            f"Subject: Closing the loop\n\n"
            f"I'll leave it here. If you ever want to know how many past customers you're sitting "
            f"on, reply 'count' and I'll set it up.\n\n"
            f"{first}, {name}"
        )
    else:  # email
        content = (
            f"Subject: Your customers from last year\n\n"
            f"Hi there,\n\n"
            f"Most {trade} shops in {city} have hundreds of customers in Jobber or Housecall Pro "
            f"who haven't booked in a year — the cheapest work there is, because they already "
            f"know you.\n\n"
            f"We send them {offer}. English and Spanish.\n\n"
            f"Worth 15 minutes to count yours?\n\n"
            f"{first}\n{name}"
        )
    return content, "template"

# ---------------------------------------------------------------- content

POSTS_SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": list(PLATFORM_SPECS)},
                    "content": {"type": "string"},
                    "hashtags": {"type": "string"},
                },
                "required": ["platform", "content", "hashtags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["posts"],
    "additionalProperties": False,
}


def generate_posts(profile: dict, topic: str, platforms: list[str]) -> list[dict]:
    """Generate one post per platform. Returns [{platform, content, hashtags, generated_by}]."""
    specs = "\n".join(f"- {p}: {PLATFORM_SPECS.get(p, 'social post')}" for p in platforms)
    text = llm.complete(
        system=(
            "You are a social media strategist for a small business. Write posts that give "
            "real value first and promote softly. Avoid hype words (unlock, game-changer, "
            "revolutionize) and AI-slop phrasing.\n\n" + _profile_context(profile)
        ),
        user=f"Topic: {topic}\n\nWrite one post for each platform:\n{specs}",
        max_tokens=4096,
        json_schema=POSTS_SCHEMA,
    )
    if text:
        data = llm.parse_json_response(text)
        posts = (data or {}).get("posts", [])
        wanted = [p for p in posts
                  if isinstance(p, dict) and p.get("platform") in platforms and p.get("content")]
        if wanted:
            for p in wanted:
                p["generated_by"] = "ai"
                p.setdefault("hashtags", "")
            return wanted

    # Template fallback
    name = profile.get("business_name", "our product")
    site = profile.get("website", "")
    templates = {
        "x": f"Most people overcomplicate {topic}.\n\nStart small: one tool, one skill, one paying use case. Consistency beats complexity.\n\n#AI #SideHustle",
        "linkedin": (
            f"I've been diving into {topic} lately.\n\n"
            "The pattern I keep seeing: the people getting results aren't using secret tools — "
            "they picked one workflow and repeated it until it paid.\n\n"
            "Three steps that work:\n"
            "1. Pick a skill AI genuinely accelerates\n"
            "2. Package it as a simple service\n"
            "3. Deliver fast, collect proof, raise prices\n\n"
            f"What's been your experience with {topic}?"
        ),
        "reddit": (
            f"What actually works with {topic} (from someone who's tested a lot)\n\n"
            "Cutting through the hype: most 'AI money' advice fails because it skips the boring part — "
            "finding someone who'll pay before building anything. Start with a real problem, use AI to "
            "deliver faster, and iterate. Ask me anything, happy to share specifics."
        ),
        "instagram": (
            f"Real talk about {topic} 💡\n\n"
            "It's not magic — it's leverage. The people winning picked ONE thing and stuck with it.\n\n"
            f"Learn the exact playbook → {name}" + (f" (link in bio: {site})" if site else "") +
            "\n\n#AITools #SideHustle #PassiveIncome #MakeMoneyOnline #AIIncome"
        ),
    }
    return [
        {"platform": p, "content": templates.get(p, f"Thoughts on {topic}..."), "hashtags": "", "generated_by": "template"}
        for p in platforms
    ]


# ---------------------------------------------------------------- course leads

COURSE_QUALIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "fit_score": {"type": "integer"},
        "rationale": {"type": "string"},
        "opener_angle": {"type": "string"},
    },
    "required": ["fit_score", "rationale", "opener_angle"],
    "additionalProperties": False,
}


def qualify_course_lead(profile: dict, lead: dict) -> dict | None:
    """Score how good a fit a person is for the course (0-100), with a
    rationale and the best angle for a genuinely helpful reply."""
    text = llm.complete(
        system=(
            "You qualify inbound-style social leads for a digital course that teaches "
            "people to make money with AI. High fit = someone genuinely trying to start "
            "an AI side hustle or make money online, asking real questions, open to help. "
            "Low fit = people already selling courses, bots, rage-bait, or off-topic posts. "
            "Be blunt and practical.\n\n" + _profile_context(profile)
        ),
        user=(
            "Qualify this person as a potential course buyer.\n\n"
            f"Where they posted: {lead.get('community', '')}\n"
            f"Author: {lead.get('author', '')}\n"
            f"Post: {lead.get('title', '')}\n{lead.get('snippet', '')}"
        ),
        max_tokens=1024,
        json_schema=COURSE_QUALIFY_SCHEMA,
    )
    if not text:
        return None
    data = llm.parse_json_response(text)
    if not data or "fit_score" not in data:
        return None
    try:
        data["fit_score"] = max(0, min(100, int(data["fit_score"])))
    except (TypeError, ValueError):
        return None
    return data


# ---------------------------------------------------------------- content calendar

CALENDAR_SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "integer"},
                    "platform": {"type": "string", "enum": list(PLATFORM_SPECS)},
                    "topic": {"type": "string"},
                    "content": {"type": "string"},
                    "hashtags": {"type": "string"},
                },
                "required": ["day", "platform", "topic", "content", "hashtags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["posts"],
    "additionalProperties": False,
}


def generate_calendar(profile: dict, days: int = 7, platforms: list[str] | None = None) -> list[dict]:
    """A ready-to-schedule week of content — one post per day, rotating
    platforms, each on a distinct angle. Returns [{day, platform, topic,
    content, hashtags, generated_by}]."""
    platforms = platforms or ["x", "linkedin", "instagram"]
    text = llm.complete(
        system=(
            "You are a social media strategist for a small business. Plan a content "
            "calendar that builds trust and drives soft interest — value first, promotion "
            "light. Vary the angle each day (tip, myth-buster, mini case study, question, "
            "behind-the-scenes, quick win, invitation). No hype words or AI-slop phrasing.\n\n"
            + _profile_context(profile)
        ),
        user=(
            f"Plan {days} days of content, one post per day (day 1..{days}), rotating across "
            f"these platforms: {', '.join(platforms)}. Each post: a distinct topic/angle, the "
            f"finished post text, and hashtags where the platform uses them."
        ),
        max_tokens=4096,
        json_schema=CALENDAR_SCHEMA,
    )
    if text:
        data = llm.parse_json_response(text)
        posts = (data or {}).get("posts", [])
        wanted = [p for p in posts if isinstance(p, dict) and p.get("content") and p.get("platform") in platforms]
        if wanted:
            for p in wanted:
                p["generated_by"] = "ai"
                p.setdefault("hashtags", "")
                p.setdefault("topic", "")
            return wanted[:days]

    # Template fallback — a solid evergreen week.
    angles = [
        ("x", "The one-tool rule", "Most people fail at AI income because they chase every new tool.\n\nPick ONE. Get genuinely good. Sell it this week. Then expand.\n\n#AI #SideHustle"),
        ("linkedin", "How beginners earn their first $100 with AI",
         "The gap between 'learning AI' and 'earning with AI' is one thing: finding someone who'll pay before you build.\n\n"
         "Three steps that actually work:\n1. Pick a service AI speeds up (writing, images, automation)\n"
         "2. Offer it to 10 real people this week\n3. Deliver fast, collect proof, raise your price\n\nWhat's stopped you from starting?"),
        ("instagram", "Myth: you need to be technical",
         "Myth: you need to code to make money with AI 🙅\n\nReality: the people winning are just good at ONE workflow they repeat.\n\n#AITools #SideHustle #MakeMoneyOnline #PassiveIncome #AIIncome"),
        ("x", "Quick win", "A $0 AI side hustle you can start today:\n\nOffer to rewrite 5 local businesses' Google descriptions with AI. Charge $50 each once they see the before/after.\n\n#AI #SideHustle"),
        ("linkedin", "Mini case study",
         "A friend with zero tech background started offering AI-written product descriptions to Etsy sellers.\n\n"
         "$30 a store, 2 stores a day, done in an evening. It's not glamorous — it's repeatable.\n\nRepeatable beats clever. What could you repeat?"),
        ("instagram", "Behind the scenes",
         "The 'secret' to AI income isn't a secret 👀\n\nIt's picking a boring problem people already pay to solve, and using AI to solve it faster.\n\n#AIIncome #SideHustle #MakeMoneyOnline #AITools #Entrepreneur"),
        ("x", "Invitation", "I wrote out the exact beginner playbook for making your first income with AI — no fluff, no 'passive income' lies.\n\nHappy to share it, just ask.\n\n#AI #SideHustle"),
    ]
    name = profile.get("business_name", "")
    out = []
    for i in range(days):
        platform, topic, content = angles[i % len(angles)]
        out.append({"day": i + 1, "platform": platform, "topic": topic,
                    "content": content, "hashtags": "", "generated_by": "template"})
    return out


TOPICS_SCHEMA = {
    "type": "object",
    "properties": {"topics": {"type": "array", "items": {"type": "string"}}},
    "required": ["topics"],
    "additionalProperties": False,
}


def suggest_topics(profile: dict, n: int = 8) -> list[str]:
    """Fresh content-topic ideas tailored to the business."""
    text = llm.complete(
        system=(
            "You brainstorm social content topics for a small business. Each topic is a "
            "specific, scroll-stopping angle — not a generic category. Value-first.\n\n"
            + _profile_context(profile)
        ),
        user=f"Give {n} content topic ideas, each a short specific hook.",
        max_tokens=1024,
        json_schema=TOPICS_SCHEMA,
    )
    if text:
        data = llm.parse_json_response(text)
        topics = [t for t in (data or {}).get("topics", []) if isinstance(t, str) and t.strip()]
        if topics:
            return topics[:n]
    return [
        "3 realistic ways beginners earn their first $100 with AI",
        "The one AI tool I'd master first if I started over",
        "Why 'passive income with AI' is mostly a lie (and what actually works)",
        "A $0 AI side hustle you can start this weekend",
        "How to find someone who'll pay before you build anything",
        "AI freelancing: the services people actually pay for right now",
        "Turning one skill into a repeatable AI-powered service",
        "The boring AI money strategy nobody posts about",
    ][:n]
