"""AIGrowthEngine — business growth automation.

Run with:  uvicorn app.main:app --reload
"""
import csv
import io
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, business_finder, lead_finder, llm
from .database import (
    get_agency_profile, get_db, get_profile, init_db,
    save_agency_profile, save_profile,
)

app = FastAPI(title="AIGrowthEngine")

init_db()

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

LEAD_STATUSES = ["new", "contacted", "responded", "customer", "archived"]
POST_STATUSES = ["draft", "scheduled", "posted"]


# ------------------------------------------------------------- models

class ProfileIn(BaseModel):
    business_name: str = ""
    website: str = ""
    description: str = ""
    audience: str = ""
    tone: str = ""
    keywords: list[str] = []
    subreddits: list[str] = []


class DiscoverIn(BaseModel):
    sources: list[str] = ["reddit", "hackernews"]
    keywords: list[str] | None = None  # default: profile keywords
    min_score: int = 20


class AgencyProfileIn(BaseModel):
    agency_name: str = ""
    website: str = ""
    service: str = ""
    pricing: str = ""
    founders: str = ""
    tone: str = ""
    verticals: list[str] = []
    cities: list[str] = []


class AgencyDiscoverIn(BaseModel):
    sources: list[str] = ["osm", "google"]
    cities: list[str] | None = None      # default: agency profile cities
    verticals: list[str] | None = None   # default: agency profile verticals
    min_score: int = 20


class LlmConfigIn(BaseModel):
    provider: str = "anthropic"
    model: str = ""
    api_key: str = ""    # empty = keep the currently stored key
    base_url: str = ""


class LeadIn(BaseModel):
    title: str
    snippet: str = ""
    source_url: str | None = None
    author: str = ""
    community: str = ""
    notes: str = ""


class LeadPatch(BaseModel):
    status: str | None = None
    notes: str | None = None


class DraftIn(BaseModel):
    channel: str = "comment"  # person: comment | dm | email — business: email | sms | callprep


class GenerateIn(BaseModel):
    topic: str
    platforms: list[str] = ["x", "linkedin"]


class PostPatch(BaseModel):
    content: str | None = None
    status: str | None = None
    scheduled_for: str | None = None


# ------------------------------------------------------------- dashboard

@app.get("/api/dashboard")
def dashboard():
    with get_db() as db:
        lead_counts = {
            row["status"]: row["n"]
            for row in db.execute("SELECT status, COUNT(*) n FROM leads GROUP BY status")
        }
        post_counts = {
            row["status"]: row["n"]
            for row in db.execute("SELECT status, COUNT(*) n FROM posts GROUP BY status")
        }
        outreach_count = db.execute("SELECT COUNT(*) n FROM outreach").fetchone()["n"]
        recent_leads = [
            dict(r) for r in db.execute(
                "SELECT * FROM leads WHERE status != 'archived' ORDER BY intent_score DESC, id DESC LIMIT 5"
            )
        ]
    return {
        "leads": lead_counts,
        "posts": post_counts,
        "outreach_drafts": outreach_count,
        "top_leads": recent_leads,
        "ai_enabled": ai.ai_available(),
    }


# ------------------------------------------------------------- settings

@app.get("/api/settings")
def read_settings():
    return {
        "profile": get_profile(),
        "agency": get_agency_profile(),
        "ai_enabled": ai.ai_available(),
        "llm": llm.status(),  # api key never included — only api_key_set
        "google_places_enabled": business_finder.google_places_enabled(),
    }


@app.put("/api/settings")
def write_settings(profile: ProfileIn):
    save_profile(profile.model_dump())
    return {"ok": True}


@app.put("/api/settings/agency")
def write_agency_settings(profile: AgencyProfileIn):
    save_agency_profile(profile.model_dump())
    return {"ok": True}


@app.put("/api/settings/llm")
def write_llm_settings(body: LlmConfigIn):
    if body.provider not in llm.PROVIDERS:
        raise HTTPException(400, f"provider must be one of {list(llm.PROVIDERS)}")
    cfg = body.model_dump()
    if not cfg["api_key"]:
        # Empty key in the form means "keep what I already saved" —
        # unless the provider changed, in which case the old key is wrong anyway.
        old = llm.get_llm_config()
        if old["provider"] == cfg["provider"]:
            cfg["api_key"] = old.get("api_key", "")
    llm.save_llm_config(cfg)
    return {"ok": True, "llm": llm.status()}


@app.post("/api/llm/test")
def test_llm():
    ok, detail = llm.try_complete(
        system="You are a connection test. Reply with a single short sentence.",
        user="Say hello and name yourself in under 15 words.",
        max_tokens=1024,
    )
    return {"ok": ok, "detail": detail, **{k: llm.status()[k] for k in ("provider", "model")}}


# ------------------------------------------------------------- leads

@app.post("/api/leads/discover")
def discover_leads(body: DiscoverIn):
    profile = get_profile()
    keywords = body.keywords or profile.get("keywords", [])
    if not keywords:
        raise HTTPException(400, "No keywords configured — add some in Settings first.")
    found = lead_finder.discover(keywords, profile.get("subreddits", []), body.sources)
    found = [f for f in found if f["intent_score"] >= body.min_score]

    added = 0
    with get_db() as db:
        for lead in found:
            cur = db.execute(
                "INSERT OR IGNORE INTO leads (source, source_url, title, snippet, author, community, intent_score) "
                "VALUES (:source, :source_url, :title, :snippet, :author, :community, :intent_score)",
                lead,
            )
            added += cur.rowcount
    return {"found": len(found), "added": added}


@app.post("/api/agency/discover")
def discover_businesses(body: AgencyDiscoverIn):
    agency = get_agency_profile()
    cities = body.cities or agency.get("cities", [])
    verticals = body.verticals or agency.get("verticals", [])
    if not cities:
        raise HTTPException(400, "No target cities configured — add some in Settings first.")
    if not verticals:
        raise HTTPException(400, "No verticals configured — add some in Settings first.")
    sources = body.sources
    if "google" in sources and not business_finder.google_places_enabled():
        sources = [s for s in sources if s != "google"]
    if not sources:
        raise HTTPException(400, "No available sources (set GOOGLE_PLACES_API_KEY to enable Google).")

    found = business_finder.discover(cities, verticals, sources)
    found = [f for f in found if f["intent_score"] >= body.min_score]

    added = 0
    with get_db() as db:
        for biz in found:
            row = {**biz, "meta": json.dumps(biz["meta"])}
            cur = db.execute(
                "INSERT OR IGNORE INTO leads (source, source_url, title, snippet, author, community, "
                " intent_score, kind, phone, website, city, vertical, meta) "
                "VALUES (:source, :source_url, :title, :snippet, :author, :community, "
                " :intent_score, :kind, :phone, :website, :city, :vertical, :meta)",
                row,
            )
            added += cur.rowcount
    return {"found": len(found), "added": added, "sources_used": sources}


@app.get("/api/leads")
def list_leads(status: str | None = None, q: str | None = None, kind: str | None = None):
    sql = "SELECT * FROM leads WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if q:
        sql += " AND (title LIKE ? OR snippet LIKE ? OR community LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY intent_score DESC, id DESC"
    with get_db() as db:
        return [dict(r) for r in db.execute(sql, params)]


@app.post("/api/leads")
def create_lead(body: LeadIn):
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO leads (source, source_url, title, snippet, author, community, notes) "
            "VALUES ('manual', ?, ?, ?, ?, ?, ?)",
            (body.source_url, body.title, body.snippet, body.author, body.community, body.notes),
        )
        return {"id": cur.lastrowid}


@app.patch("/api/leads/{lead_id}")
def update_lead(lead_id: int, body: LeadPatch):
    updates, params = [], []
    if body.status is not None:
        if body.status not in LEAD_STATUSES:
            raise HTTPException(400, f"status must be one of {LEAD_STATUSES}")
        updates.append("status = ?")
        params.append(body.status)
        if body.status == "contacted":
            updates.append("contacted_at = datetime('now')")
    if body.notes is not None:
        updates.append("notes = ?")
        params.append(body.notes)
    if not updates:
        raise HTTPException(400, "Nothing to update")
    params.append(lead_id)
    with get_db() as db:
        cur = db.execute(f"UPDATE leads SET {', '.join(updates)} WHERE id = ?", params)
        if cur.rowcount == 0:
            raise HTTPException(404, "Lead not found")
    return {"ok": True}


@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int):
    with get_db() as db:
        db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    return {"ok": True}


@app.get("/api/leads/export.csv")
def export_leads():
    with get_db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM leads ORDER BY id")]
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


# ------------------------------------------------------------- outreach

@app.post("/api/leads/{lead_id}/draft")
def draft_for_lead(lead_id: int, body: DraftIn):
    with get_db() as db:
        row = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Lead not found")
        lead = dict(row)
    if lead.get("kind") == "business":
        content, generated_by = ai.draft_agency_outreach(get_agency_profile(), lead, body.channel)
    else:
        content, generated_by = ai.draft_outreach(get_profile(), lead, body.channel)
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO outreach (lead_id, channel, content, generated_by) VALUES (?, ?, ?, ?)",
            (lead_id, body.channel, content, generated_by),
        )
        draft_id = cur.lastrowid
    return {"id": draft_id, "content": content, "generated_by": generated_by}


@app.get("/api/leads/{lead_id}/outreach")
def outreach_for_lead(lead_id: int):
    with get_db() as db:
        return [
            dict(r) for r in db.execute(
                "SELECT * FROM outreach WHERE lead_id = ? ORDER BY id DESC", (lead_id,)
            )
        ]


# ------------------------------------------------------------- content

@app.post("/api/content/generate")
def generate_content(body: GenerateIn):
    if not body.topic.strip():
        raise HTTPException(400, "Topic is required")
    posts = ai.generate_posts(get_profile(), body.topic.strip(), body.platforms)
    saved = []
    with get_db() as db:
        for p in posts:
            cur = db.execute(
                "INSERT INTO posts (platform, topic, content, hashtags, generated_by) VALUES (?, ?, ?, ?, ?)",
                (p["platform"], body.topic.strip(), p["content"], p.get("hashtags", ""), p["generated_by"]),
            )
            saved.append({"id": cur.lastrowid, **p})
    return {"posts": saved}


@app.get("/api/posts")
def list_posts(status: str | None = None):
    sql = "SELECT * FROM posts"
    params: list = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY CASE WHEN scheduled_for IS NULL THEN 1 ELSE 0 END, scheduled_for, id DESC"
    with get_db() as db:
        return [dict(r) for r in db.execute(sql, params)]


@app.patch("/api/posts/{post_id}")
def update_post(post_id: int, body: PostPatch):
    updates, params = [], []
    if body.content is not None:
        updates.append("content = ?")
        params.append(body.content)
    if body.status is not None:
        if body.status not in POST_STATUSES:
            raise HTTPException(400, f"status must be one of {POST_STATUSES}")
        updates.append("status = ?")
        params.append(body.status)
    if body.scheduled_for is not None:
        updates.append("scheduled_for = ?")
        params.append(body.scheduled_for or None)
    if not updates:
        raise HTTPException(400, "Nothing to update")
    params.append(post_id)
    with get_db() as db:
        cur = db.execute(f"UPDATE posts SET {', '.join(updates)} WHERE id = ?", params)
        if cur.rowcount == 0:
            raise HTTPException(404, "Post not found")
    return {"ok": True}


@app.delete("/api/posts/{post_id}")
def delete_post(post_id: int):
    with get_db() as db:
        db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    return {"ok": True}


# ------------------------------------------------------------- frontend

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
