"""AI-powered content and outreach generation, with template fallbacks.

Works with any LLM provider configured in Settings (Anthropic, OpenAI,
Gemini, OpenRouter, Groq, local Ollama, or a custom OpenAI-compatible
endpoint) — see app/llm.py. With no provider configured the app still
works using templates.
"""
import json

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

AGENCY_CHANNEL_SPECS = {
    "email": (
        "a cold email: subject line on the first line as 'Subject: …', then a 90-130 word body. "
        "Open with the missed-call pain specific to their trade, one concrete gap you noticed about "
        "their business, the AI receptionist value in one plain sentence, price range anchored to "
        "one missed job, and a low-friction CTA offering a 15-minute demo where the AI calls them first"
    ),
    "sms": (
        "a first-touch SMS, max 320 characters: who you are, the missed-call pain for their trade, "
        "the AI receptionist in a few words, and an easy yes/no question. No links, no pressure"
    ),
    "callprep": (
        "a cold-call prep sheet in plain text with these sections: LEAD SNAPSHOT (their details and "
        "the pain signals we spotted), OPENING HOOK (word-for-word, ~10 seconds, ask for 60 seconds), "
        "PAIN AGITATION (vivid trade-specific missed-call scenario ending in an open question), "
        "SOLUTION TEASER (AI answers 24/7, sounds human, books to calendar, texts the owner), "
        "LIKELY OBJECTIONS (3-4 with word-for-word responses: not interested / already have a "
        "receptionist / cost / don't trust AI), and CLOSE (two-option scheduling ask)"
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
    # Internal qualification notes (e.g. "phone listed — cold-callable")
    # aren't customer-facing gaps — don't quote them in outreach.
    return [r for r in reasons if "cold-callable" not in r]


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
            "You write sales outreach for a small AI agency selling AI phone receptionists "
            "to home service businesses (HVAC, plumbing, roofing…). The core pain: owners "
            "lose jobs because calls come in while they're on a ladder, under a house, or "
            "after hours — and the caller books a competitor. Rules: plain-spoken and "
            "specific, never hypey; lead with their pain, not our tech; anchor price to the "
            "cost of one missed job; the strongest proof is letting the AI call them so "
            "they can hear it. Sound like a fellow small-business owner, not a marketer.\n\n"
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
            f"Pain signals we detected: {'; '.join(gaps) or 'none detected'}"
        ),
        max_tokens=1500,
    )
    if text:
        return text, "ai"

    # Template fallbacks — modeled on the Colibri Code sales materials.
    name = profile.get("agency_name", "our agency")
    founders = profile.get("founders", "")
    pricing = profile.get("pricing", "$300–500/month")
    gap_line = f" (I noticed: {gaps[0]}.)" if gaps else ""

    if channel == "sms":
        content = (
            f"Hi, this is {founders.split('(')[0].strip() or 'Mike'} with {name} — we help {trade} "
            f"companies in {city} stop losing jobs to missed calls. Our AI phone agent answers 24/7, "
            f"sounds like a real person, and books the job onto your calendar. 15-min demo where the "
            f"AI calls YOU first — worth a look?"
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
            f"Website: {lead.get('website') or 'NONE — big gap, phone is their only funnel'}\n"
            f"{rating_line}"
            f"Pain signals: {'; '.join(gaps) or 'verify hours/booking before dialing'}\n\n"
            f"OPENING (10s): \"Hey [first name], this is [Mike/Paola] with {name}. I'll be real "
            f"quick — I work with {trade} companies in {city}, and I had a quick question. "
            f"Do you have 60 seconds?\"\n\n"
            f"AGITATE (20s): \"The #1 thing I hear from {trade} owners: they lose jobs because "
            f"calls come in while they're on a job or after hours, and by the time they call back, "
            f"that customer already booked someone else. Is that something you run into?\"\n\n"
            f"TEASER: AI phone agent — answers 24/7, sounds like a real person, books the "
            f"appointment onto your calendar, texts you the details. {pricing}.\n\n"
            f"OBJECTIONS:\n"
            f"- \"Not interested\" → \"Totally fair. Quick question though — how many calls a week "
            f"would you guess you miss while on a job?\"\n"
            f"- \"Have a receptionist\" → \"That's great. Does she work nights and weekends too? "
            f"Most clients keep her for daytime and use us for after-hours and overflow.\"\n"
            f"- \"How much?\" → \"{pricing}. Best to see the demo first so you know what "
            f"you're getting.\"\n"
            f"- \"Don't trust AI\" → \"I'll have it call you right now — you tell me if you can "
            f"tell it's AI. If it doesn't sound right, you'll never hear from me again.\"\n\n"
            f"CLOSE: \"Would Tuesday or Thursday work better for a 15-minute demo?\""
        )
    else:  # email
        content = (
            f"Subject: Quick question about missed calls at {business}\n\n"
            f"Hi there,\n\n"
            f"I work with {trade} companies in {city}, and the #1 thing I keep hearing from "
            f"owners is that they lose jobs because calls come in while they're on a job or after "
            f"hours — and by the time they call back, that customer has already booked someone "
            f"else.{gap_line}\n\n"
            f"We built an AI phone agent that answers your calls 24/7, sounds like a real person, "
            f"books the appointment straight onto your calendar, and texts you the details. "
            f"Pricing-wise, most of our clients land at {pricing}.\n\n"
            f"Worth a quick 15-minute demo? I'll even have the AI call you first so you can hear "
            f"it for yourself.\n\n"
            f"{founders}\n{name}"
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
