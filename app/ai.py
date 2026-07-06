"""Claude-powered content and outreach generation, with template fallbacks.

Set ANTHROPIC_API_KEY (or log in with `ant auth login`) to enable AI
generation. Without credentials the app still works using templates.
"""
import json
import os

try:
    import anthropic
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False

MODEL = "claude-opus-4-8"

PLATFORM_SPECS = {
    "x": "X/Twitter post, max 280 characters, punchy hook first line, 1-2 hashtags max",
    "linkedin": "LinkedIn post, 100-200 words, professional but personal, line breaks between ideas, end with a question to drive comments",
    "reddit": "Reddit post (title + body), value-first and non-promotional in tone — Reddit hates ads. Share genuine insight; mention the product only if organic",
    "instagram": "Instagram caption, 50-125 words, engaging hook, emoji-friendly, 5-8 hashtags at the end",
}


def _client():
    if not _HAS_SDK:
        return None
    # The SDK resolves ANTHROPIC_API_KEY / auth profiles itself; only skip
    # when we can tell there are no credentials at all.
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN") \
            and not os.path.exists(os.path.expanduser("~/.config/anthropic")):
        return None
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


def ai_available() -> bool:
    return _client() is not None


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
    client = _client()
    if client is not None:
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=(
                    "You write authentic, helpful outreach for a small business. "
                    "Rules: lead with genuine value specific to what the person posted; "
                    "never open with a pitch; keep it short; sound human, not corporate; "
                    "one soft mention of the product at most, and only where it truly helps. "
                    "Respect community norms — on Reddit especially, be a helpful member first.\n\n"
                    + _profile_context(profile)
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Draft a {channel} reply/message to this person. "
                        f"Return ONLY the message text, no preamble.\n\n"
                        f"Where they posted: {lead.get('community', '')}\n"
                        f"Their post title: {lead.get('title', '')}\n"
                        f"Their post text: {lead.get('snippet', '') or '(no body text)'}"
                    ),
                }],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "").strip()
            if text:
                return text, "ai"
        except Exception:
            pass  # fall through to template

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


# ---------------------------------------------------------------- content

def generate_posts(profile: dict, topic: str, platforms: list[str]) -> list[dict]:
    """Generate one post per platform. Returns [{platform, content, hashtags, generated_by}]."""
    client = _client()
    if client is not None:
        try:
            specs = "\n".join(f"- {p}: {PLATFORM_SPECS.get(p, 'social post')}" for p in platforms)
            resp = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=(
                    "You are a social media strategist for a small business. Write posts that give "
                    "real value first and promote softly. Avoid hype words (unlock, game-changer, "
                    "revolutionize) and AI-slop phrasing.\n\n" + _profile_context(profile)
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Topic: {topic}\n\nWrite one post for each platform:\n{specs}"
                    ),
                }],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": {
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
                        },
                    },
                },
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
            posts = json.loads(text).get("posts", [])
            wanted = [p for p in posts if p.get("platform") in platforms]
            if wanted:
                for p in wanted:
                    p["generated_by"] = "ai"
                return wanted
        except Exception:
            pass  # fall through to templates

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
