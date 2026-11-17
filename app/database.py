"""SQLite storage for AIGrowthEngine."""
import json
import os
import sqlite3
from contextlib import contextmanager

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "growth.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT 'manual',        -- reddit | hackernews | osm | google | manual
    source_url TEXT UNIQUE,
    title TEXT NOT NULL,
    snippet TEXT DEFAULT '',
    author TEXT DEFAULT '',
    community TEXT DEFAULT '',                    -- subreddit / HN / etc.
    intent_score INTEGER DEFAULT 0,               -- 0-100
    status TEXT NOT NULL DEFAULT 'new',           -- new | contacted | responded | customer | archived
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    contacted_at TEXT,
    kind TEXT NOT NULL DEFAULT 'person',          -- person (course leads) | business (agency clients)
    phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    city TEXT DEFAULT '',
    vertical TEXT DEFAULT '',                     -- hvac | plumber | roofer | ...
    meta TEXT DEFAULT '{}'                        -- JSON: rating, review_count, hours, score_reasons…
);

CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel TEXT NOT NULL DEFAULT 'comment',      -- comment | dm | email
    content TEXT NOT NULL,
    generated_by TEXT DEFAULT 'template',         -- ai | template
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,                       -- x | linkedin | reddit | instagram
    topic TEXT DEFAULT '',
    content TEXT NOT NULL,
    hashtags TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',         -- draft | scheduled | posted
    scheduled_for TEXT,
    generated_by TEXT DEFAULT 'template',
    created_at TEXT DEFAULT (datetime('now'))
);
"""

DEFAULT_PROFILE = {
    "business_name": "AI Income Blueprint (AIMoney)",
    "website": "https://mikepitts25.github.io/AImoney/",
    "description": (
        "A 27-chapter digital guide teaching people how to generate income "
        "using AI tools — from side hustles to full online businesses. "
        "Sold directly via Stripe."
    ),
    "audience": (
        "People looking to make extra money online, side-hustlers, beginners "
        "curious about AI tools, freelancers wanting to boost income"
    ),
    "tone": "friendly, helpful, non-hypey — lead with value, never hard-sell",
    "keywords": [
        "make money with AI",
        "AI side hustle",
        "passive income with AI",
        "earn money ChatGPT",
        "AI income ideas",
        "how to make money online with AI",
    ],
    "subreddits": [
        "sidehustle",
        "passive_income",
        "WorkOnline",
        "Entrepreneur",
        "ArtificialInteligence",
    ],
}

# Agency mode: Colibri Code runs the Booked-Job Desk for home service businesses.
# Seeded from the sales materials in the AImoney course repo — edit in Settings.
DEFAULT_AGENCY_PROFILE = {
    "agency_name": "Colibri Code LLC",
    "website": "",
    "service": (
        "The Booked-Job Desk for home-service contractors: we turn the customers and "
        "estimates a shop already has into booked jobs. Seasonal win-back campaigns to "
        "customers who haven't booked in 12+ months, a weekly follow-up on open estimates, "
        "and review requests after every job - drafted with AI, reviewed by a bilingual person "
        "(English/Spanish), approved by the owner, and sent from the shop's OWN Jobber or "
        "Housecall Pro account. Results are counted in the shop's own job board. Add-ons on "
        "request: after-hours front office (we run their AI receptionist) and speed-to-lead."
    ),
    "pricing": (
        "Free Dormant-Customer Count (15-min screenshare). Reactivation Pilot: $0 up front, "
        "$75 per booked job (counted in their job board within 30 days). Booked-Job Desk: "
        "$400/month + $40 per booked job, capped at $1,500, month-to-month, no setup fee."
    ),
    "founders": "Mike (build + sales) & Paola (client ops, campaign review, Spanish)",
    "tone": (
        "confident, plain-spoken, owner-to-owner. Lead with THEIR dormant customers and open "
        "estimates - their own numbers - never with 'AI'. Stress that they approve every "
        "message, it sends from their own account, and they only pay per job booked in their "
        "own job board. Never invent statistics, response rates or client results."
    ),
    "verticals": ["hvac", "plumber", "roofer", "electrician"],
    # Working window 17:00-23:00 CET = 08:00-14:00 PT, and Mountain/Pacific is where
    # Spanish-speaking demand concentrates - timezone and language edge select the
    # same prospect list.
    "cities": [
        "Phoenix, AZ", "Tucson, AZ", "Las Vegas, NV", "Denver, CO",
        "Albuquerque, NM", "Sacramento, CA", "San Antonio, TX", "Houston, TX",
    ],
}


# Fingerprint of the Aug-2026 default "service" text. A stored profile that
# still carries it was never edited by the user, so init_db upgrades its
# service/pricing/tone/founders to the current defaults.
_AUG_2026_SERVICE = (
        "A staffed AI front desk for home-service contractors. Two halves: (1) the "
        "agent answers every call and is configured to give Google's 'Ask for Me' "
        "AI caller a structured quote - price band, next availability, warranty, "
        "permits, haul-away - inside 90 seconds, so the homeowner's AI books them "
        "instead of dialling the next shop; (2) a bilingual human reads, corrects "
        "and escalates every overnight conversation before the owner wakes up. "
        "Books into their real calendar (Jobber/Housecall Pro), handles follow-up, "
        "and we own the A2P registration and AI-disclosure compliance."
)
# Fingerprint of the Oct-2026 default (Overnight Front Office), upgraded the same way.
_OCT_2026_SERVICE = (
        "The Overnight Front Office for home-service contractors. Every call, text and "
        "AI-caller inquiry from 5pm to 7am is answered - by the shop's existing AI "
        "receptionist (Jobber, Housecall Pro, Zoom, Quo), which we configure and run, or by "
        "ours - and a bilingual human reads, corrects, tags and escalates every overnight "
        "conversation, then sends the owner a sorted Morning Board (book today / call back / "
        "quote sent / spam) before 7am Pacific. Spanish-speaking customers get a call back "
        "from a person. Google discontinued Business Profile call history in 2026, so the "
        "board is the owner's record. Includes calendar write-back, follow-up texts, review "
        "requests, Business Profile facts kept current for Google's AI caller, and the A2P "
        "and AI-disclosure compliance."
)
_PROFILE_UPGRADE_FIELDS = ("service", "pricing", "tone", "founders")

# Columns added after the first release — applied to existing databases on boot.
_LEAD_MIGRATIONS = {
    "kind": "TEXT NOT NULL DEFAULT 'person'",
    "phone": "TEXT DEFAULT ''",
    "website": "TEXT DEFAULT ''",
    "city": "TEXT DEFAULT ''",
    "vertical": "TEXT DEFAULT ''",
    "meta": "TEXT DEFAULT '{}'",
    "email": "TEXT DEFAULT ''",
    "next_action": "TEXT DEFAULT ''",       # e.g. "follow-up email #2"
    "next_action_at": "TEXT",               # ISO date the action is due
}

DEFAULT_AUTOPILOT = {
    "enabled": False,
    "interval_hours": 24,
    "sources": ["osm", "google", "yelp"],   # unavailable sources are skipped
    "enrich": True,                          # auto-enrich new business leads
    "last_run": None,
    "last_result": "",
}


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_db() as db:
        db.executescript(SCHEMA)
        existing = {r["name"] for r in db.execute("PRAGMA table_info(leads)")}
        for col, decl in _LEAD_MIGRATIONS.items():
            if col not in existing:
                db.execute(f"ALTER TABLE leads ADD COLUMN {col} {decl}")
        cur = db.execute("SELECT value FROM settings WHERE key = 'profile'")
        if cur.fetchone() is None:
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('profile', ?)",
                (json.dumps(DEFAULT_PROFILE),),
            )
        row = db.execute("SELECT value FROM settings WHERE key = 'agency_profile'").fetchone()
        if row is None:
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('agency_profile', ?)",
                (json.dumps(DEFAULT_AGENCY_PROFILE),),
            )
        else:
            stored = json.loads(row["value"])
            if stored.get("service") in (_AUG_2026_SERVICE, _OCT_2026_SERVICE):
                stored.update({k: DEFAULT_AGENCY_PROFILE[k] for k in _PROFILE_UPGRADE_FIELDS})
                db.execute("UPDATE settings SET value = ? WHERE key = 'agency_profile'",
                           (json.dumps(stored),))


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_profile() -> dict:
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = 'profile'").fetchone()
        return json.loads(row["value"]) if row else dict(DEFAULT_PROFILE)


def save_profile(profile: dict):
    with get_db() as db:
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('profile', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(profile),),
        )


# API keys for optional data sources. Stored here (settings key 'secrets')
# so they're configurable in the UI; an environment variable of the same
# name still works and takes precedence for anyone who prefers it.
SECRET_KEYS = ["GOOGLE_PLACES_API_KEY", "YELP_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]


def _stored_secrets() -> dict:
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = 'secrets'").fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return {}


def get_secret(name: str) -> str:
    """Env var wins; otherwise the value saved in Settings."""
    return os.environ.get(name) or _stored_secrets().get(name, "")


def save_secrets(values: dict):
    """Merge in provided keys; blank string means 'keep existing'."""
    stored = _stored_secrets()
    for k in SECRET_KEYS:
        v = values.get(k)
        if v:  # non-empty → set; empty/None → leave what's there
            stored[k] = v.strip()
    with get_db() as db:
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('secrets', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(stored),),
        )


def secrets_status() -> dict:
    """Which keys are set, and whether from env (locked) or the DB — never the values."""
    stored = _stored_secrets()
    out = {}
    for k in SECRET_KEYS:
        from_env = bool(os.environ.get(k))
        out[k] = {"set": from_env or bool(stored.get(k)), "from_env": from_env}
    return out


def get_autopilot() -> dict:
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = 'autopilot'").fetchone()
    cfg = dict(DEFAULT_AUTOPILOT)
    if row:
        try:
            cfg.update(json.loads(row["value"]))
        except json.JSONDecodeError:
            pass
    return cfg


def save_autopilot(cfg: dict):
    with get_db() as db:
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('autopilot', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(cfg),),
        )


def get_agency_profile() -> dict:
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key = 'agency_profile'").fetchone()
        return json.loads(row["value"]) if row else dict(DEFAULT_AGENCY_PROFILE)


def save_agency_profile(profile: dict):
    with get_db() as db:
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('agency_profile', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(profile),),
        )
