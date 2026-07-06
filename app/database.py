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
    source TEXT NOT NULL DEFAULT 'manual',        -- reddit | hackernews | manual
    source_url TEXT UNIQUE,
    title TEXT NOT NULL,
    snippet TEXT DEFAULT '',
    author TEXT DEFAULT '',
    community TEXT DEFAULT '',                    -- subreddit / HN / etc.
    intent_score INTEGER DEFAULT 0,               -- 0-100
    status TEXT NOT NULL DEFAULT 'new',           -- new | contacted | responded | customer | archived
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    contacted_at TEXT
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


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with get_db() as db:
        db.executescript(SCHEMA)
        cur = db.execute("SELECT value FROM settings WHERE key = 'profile'")
        if cur.fetchone() is None:
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('profile', ?)",
                (json.dumps(DEFAULT_PROFILE),),
            )


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
