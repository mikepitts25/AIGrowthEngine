"""AIGrowthEngine — business growth automation.

Run with:  uvicorn app.main:app --reload
"""
import asyncio
import csv
import hashlib
import html as html_mod
import io
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, business_finder, enrich, lead_finder, llm
from .database import (
    SECRET_KEYS, get_agency_profile, get_autopilot, get_db, get_profile,
    init_db, save_agency_profile, save_autopilot, save_profile, save_secrets,
    secrets_status,
)


@asynccontextmanager
async def _lifespan(_app):
    task = asyncio.create_task(_autopilot_loop())
    yield
    task.cancel()


app = FastAPI(title="AIGrowthEngine", lifespan=_lifespan)

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
    next_action: str | None = None
    next_action_at: str | None = None   # ISO date, "" clears


class EnrichIn(BaseModel):
    ids: list[int] | None = None   # default: all un-enriched business leads
    limit: int = 25


class BatchDraftIn(BaseModel):
    channel: str = "email"
    kind: str = "business"
    status: str = "new"
    limit: int = 10


class AutopilotIn(BaseModel):
    enabled: bool
    interval_hours: int = 24
    sources: list[str] = ["osm", "google", "yelp"]
    enrich: bool = True


class SecretsIn(BaseModel):
    GOOGLE_PLACES_API_KEY: str = ""
    YELP_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""


class DraftIn(BaseModel):
    channel: str = "comment"  # person: comment | dm | email — business: email | sms | callprep


class GenerateIn(BaseModel):
    topic: str
    platforms: list[str] = ["x", "linkedin"]


class CalendarIn(BaseModel):
    days: int = 7
    platforms: list[str] = ["x", "linkedin", "instagram"]


class PostPatch(BaseModel):
    content: str | None = None
    status: str | None = None
    scheduled_for: str | None = None


# ------------------------------------------------------------- dashboard

@app.get("/api/dashboard")
def dashboard():
    today = datetime.now().strftime("%Y-%m-%d")
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
        outreach_7d = db.execute(
            "SELECT COUNT(*) n FROM outreach WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()["n"]
        contacted_7d = db.execute(
            "SELECT COUNT(*) n FROM leads WHERE contacted_at >= datetime('now', '-7 days')"
        ).fetchone()["n"]
        by_vertical = {
            r["vertical"]: r["n"] for r in db.execute(
                "SELECT vertical, COUNT(*) n FROM leads WHERE kind = 'business' AND vertical != '' "
                "GROUP BY vertical ORDER BY n DESC")
        }
        by_source = {
            r["source"]: r["n"] for r in db.execute(
                "SELECT source, COUNT(*) n FROM leads GROUP BY source ORDER BY n DESC")
        }
        followups_due = [
            dict(r) for r in db.execute(
                "SELECT * FROM leads WHERE next_action_at IS NOT NULL AND next_action_at <= ? "
                "AND status NOT IN ('archived', 'customer') ORDER BY next_action_at LIMIT 10",
                (today,),
            )
        ]
        call_targets = [
            dict(r) for r in db.execute(
                "SELECT * FROM leads WHERE kind = 'business' AND status = 'new' "
                "ORDER BY intent_score DESC, id LIMIT 5"
            )
        ]
        recent_leads = [
            dict(r) for r in db.execute(
                "SELECT * FROM leads WHERE status != 'archived' ORDER BY intent_score DESC, id DESC LIMIT 5"
            )
        ]
    return {
        "leads": lead_counts,
        "posts": post_counts,
        "outreach_drafts": outreach_count,
        "outreach_7d": outreach_7d,
        "contacted_7d": contacted_7d,
        "by_vertical": by_vertical,
        "by_source": by_source,
        "followups_due": followups_due,
        "call_targets": call_targets,
        "top_leads": recent_leads,
        "autopilot": get_autopilot(),
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
        "yelp_enabled": business_finder.yelp_enabled(),
        "bluesky_enabled": lead_finder.bluesky_enabled(),
        "reddit_oauth_enabled": lead_finder.reddit_oauth_enabled(),
        "secrets": secrets_status(),  # which keys are set; never the values
    }


@app.put("/api/settings")
def write_settings(profile: ProfileIn):
    save_profile(profile.model_dump())
    return {"ok": True}


@app.put("/api/settings/agency")
def write_agency_settings(profile: AgencyProfileIn):
    save_agency_profile(profile.model_dump())
    return {"ok": True}


@app.put("/api/settings/secrets")
def write_secrets(body: SecretsIn):
    save_secrets(body.model_dump())
    return {"ok": True, "secrets": secrets_status()}


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


def _available_sources(requested: list[str]) -> list[str]:
    """Drop sources whose API keys aren't configured. OSM is always available."""
    out = []
    for s in requested:
        if s == "google" and not business_finder.google_places_enabled():
            continue
        if s == "yelp" and not business_finder.yelp_enabled():
            continue
        out.append(s)
    return out


def _run_agency_discovery(sources: list[str], cities: list[str] | None = None,
                          verticals: list[str] | None = None, min_score: int = 20) -> dict:
    agency = get_agency_profile()
    cities = cities or agency.get("cities", [])
    verticals = verticals or agency.get("verticals", [])
    if not cities:
        raise HTTPException(400, "No target cities configured — add some in Settings first.")
    if not verticals:
        raise HTTPException(400, "No verticals configured — add some in Settings first.")
    sources = _available_sources(sources)
    if not sources:
        raise HTTPException(400, "No available sources (set GOOGLE_PLACES_API_KEY / YELP_API_KEY).")

    found = business_finder.discover(cities, verticals, sources)
    found = [f for f in found if f["intent_score"] >= min_score]

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


@app.post("/api/agency/discover")
def discover_businesses(body: AgencyDiscoverIn):
    return _run_agency_discovery(body.sources, body.cities, body.verticals, body.min_score)


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
    if body.next_action is not None:
        updates.append("next_action = ?")
        params.append(body.next_action)
    if body.next_action_at is not None:
        updates.append("next_action_at = ?")
        params.append(body.next_action_at or None)
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


# ------------------------------------------------------------- enrichment & qualification

@app.post("/api/leads/enrich")
def enrich_leads(body: EnrichIn):
    return enrich.enrich_business_leads(body.ids, body.limit)


@app.post("/api/leads/{lead_id}/qualify")
def qualify_lead(lead_id: int):
    if not ai.ai_available():
        raise HTTPException(400, "AI qualification needs an LLM provider — configure one in Settings.")
    with get_db() as db:
        row = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Lead not found")
        lead = dict(row)
    if lead.get("kind") == "business":
        result = ai.qualify_lead(get_agency_profile(), lead)
    else:
        result = ai.qualify_course_lead(get_profile(), lead)
    if result is None:
        raise HTTPException(502, "The LLM call failed — try Test connection in Settings.")
    meta = json.loads(lead.get("meta") or "{}")
    meta["ai_qualification"] = result
    with get_db() as db:
        db.execute("UPDATE leads SET meta = ? WHERE id = ?", (json.dumps(meta), lead_id))
    return result


@app.post("/api/leads/draft-batch")
def draft_batch(body: BatchDraftIn):
    """Draft outreach for the top uncontacted leads in one shot."""
    with get_db() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM leads WHERE kind = ? AND status = ? "
            "AND id NOT IN (SELECT lead_id FROM outreach) "
            "ORDER BY intent_score DESC LIMIT ?",
            (body.kind, body.status, min(body.limit, 25)),
        )]
    agency, profile = get_agency_profile(), get_profile()
    drafted = []
    with get_db() as db:
        for lead in rows:
            if lead["kind"] == "business":
                content, generated_by = ai.draft_agency_outreach(agency, lead, body.channel)
            else:
                content, generated_by = ai.draft_outreach(profile, lead, body.channel)
            db.execute(
                "INSERT INTO outreach (lead_id, channel, content, generated_by) VALUES (?, ?, ?, ?)",
                (lead["id"], body.channel, content, generated_by),
            )
            drafted.append({"lead_id": lead["id"], "title": lead["title"], "generated_by": generated_by})
    return {"drafted": len(drafted), "leads": drafted}


# ------------------------------------------------------------- call sheet

@app.get("/callsheet")
def callsheet(limit: int = 20):
    """Printable daily call sheet for the top uncontacted business prospects."""
    with get_db() as db:
        leads = [dict(r) for r in db.execute(
            "SELECT * FROM leads WHERE kind = 'business' AND status = 'new' "
            "ORDER BY intent_score DESC, id LIMIT ?", (min(limit, 50),),
        )]
    agency = get_agency_profile()
    e = html_mod.escape
    rows = []
    for i, l in enumerate(leads, 1):
        meta = json.loads(l.get("meta") or "{}")
        signals = "; ".join(meta.get("score_reasons", []))
        qual = meta.get("ai_qualification") or {}
        phone = l.get("phone") or ""
        dial = "".join(c for c in phone if c.isdigit() or c == "+")
        phone_cell = f'<a class="call" href="tel:{e(dial)}">{e(phone)}</a>' if dial else "—"
        rows.append(f"""
        <tr>
          <td class="n">{i}</td>
          <td data-label="Business"><b>{e(l['title'])}</b><br><span class="sub">{e(l.get('vertical') or '')} · {e(l.get('city') or '')}</span></td>
          <td class="phone" data-label="Phone / email">{phone_cell}<br><span class="sub">{e(l.get('email') or '')}</span></td>
          <td class="score" data-label="Score">{l['intent_score']}{f"<br><span class='sub'>AI fit {qual['fit_score']}</span>" if qual.get('fit_score') is not None else ''}</td>
          <td class="sig" data-label="Signals &amp; angle">{e(signals) or '—'}{f"<br><i>{e(qual.get('opener_angle', ''))}</i>" if qual.get('opener_angle') else ''}</td>
          <td class="notes"></td>
        </tr>""")
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Call Sheet — {datetime.now():%Y-%m-%d}</title>
<style>
  body {{ font: 13px/1.45 -apple-system, sans-serif; margin: 24px; color: #111; }}
  h1 {{ font-size: 20px; margin: 0 0 2px; }}
  .hint {{ color: #666; margin: 0 0 16px; font-size: 12px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #f0f0f0; font-size: 11px; text-transform: uppercase; }}
  .n {{ width: 24px; color: #999; }} .score {{ width: 52px; font-weight: 700; }}
  .phone {{ white-space: nowrap; }} .sub {{ color: #666; font-size: 11px; font-weight: 400; }}
  .sig {{ font-size: 12px; }} .notes {{ width: 130px; }}
  .script {{ background: #f8f8f8; border: 1px solid #ddd; padding: 10px 12px; margin: 14px 0; font-size: 12px; }}
  a.call {{ color: #0a58ca; text-decoration: none; font-weight: 600; }}

  /* Phone: the six-column grid cannot fit, so each prospect becomes a stacked
     card. Headers are dropped and each cell is labelled from data-label. */
  @media screen and (max-width: 700px) {{
    body {{ margin: 12px; }}
    thead {{ display: none; }}
    table, tbody, tr, td {{ display: block; width: 100%; }}
    tr {{ border: 1px solid #ccc; border-radius: 8px; margin: 0 0 10px; padding: 8px 10px; }}
    td {{ border: none; padding: 3px 0; }}
    /* Blank cells collapse, except the outcome box you write into on the call. */
    td:empty:not(.notes) {{ display: none; }}
    td[data-label]::before {{
      content: attr(data-label); display: block;
      font-size: 10px; text-transform: uppercase; color: #888; margin-top: 4px;
    }}
    .n {{ width: auto; color: #999; font-size: 11px; }}
    .score {{ width: auto; }}
    .notes {{ width: auto; min-height: 44px; border-bottom: 1px dashed #bbb; }}
    .notes::before {{ content: "Outcome"; display: block; font-size: 10px;
                      text-transform: uppercase; color: #888; }}
  }}
  @media print {{ .noprint {{ display: none; }} body {{ margin: 8px; }} }}
</style></head><body>
<h1>📞 {e(agency.get('agency_name', 'Agency'))} — Call Sheet, {datetime.now():%A %b %d}</h1>
<p class="hint">Top {len(leads)} uncontacted prospects by ICP fit score. <a class="noprint" href="javascript:print()">Print</a></p>
<div class="script"><b>Opening:</b> "Hey [first name], this is [Mike/Paola] with {e(agency.get('agency_name', ''))}. I'll be real quick — I work with [trade] companies in [city], and I had a quick question. Do you have 60 seconds?"
&nbsp;·&nbsp; <b>Price:</b> {e(agency.get('pricing', ''))} &nbsp;·&nbsp; <b>Close:</b> "Would Tuesday or Thursday work better?"</div>
<table><thead><tr><th></th><th>Business</th><th>Phone / Email</th><th>Score</th><th>Pain signals & angle</th><th>Outcome</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="6">No uncontacted business leads — run discovery first.</td></tr>'}</tbody></table>
</body></html>"""
    return HTMLResponse(doc)


# ------------------------------------------------------------- autopilot

def _run_autopilot() -> str:
    cfg = get_autopilot()
    parts = []
    # Agency clients (businesses)
    try:
        r = _run_agency_discovery(cfg.get("sources", ["osm"]))
        parts.append(f"agency: {r['added']} new of {r['found']} via {'+'.join(r['sources_used'])}")
    except HTTPException as exc:
        parts.append(f"agency skipped: {exc.detail}")
    # Course buyers (people asking about making money with AI)
    profile = get_profile()
    keywords = profile.get("keywords", [])
    if keywords:
        # Bluesky + HN are keyless and reliable; Reddit joins when OAuth is configured.
        person_sources = ["hackernews", "bluesky"]
        if lead_finder.reddit_oauth_enabled():
            person_sources.append("reddit")
        found = lead_finder.discover(keywords, profile.get("subreddits", []), person_sources)
        found = [f for f in found if f["intent_score"] >= 25]
        added = 0
        with get_db() as db:
            for lead in found:
                cur = db.execute(
                    "INSERT OR IGNORE INTO leads (source, source_url, title, snippet, author, community, intent_score) "
                    "VALUES (:source, :source_url, :title, :snippet, :author, :community, :intent_score)",
                    lead,
                )
                added += cur.rowcount
        parts.append(f"course: {added} new of {len(found)} found")
    if cfg.get("enrich", True):
        er = enrich.enrich_business_leads(limit=25)
        parts.append(f"enriched {er['enriched']} leads, {er['emails_found']} emails found")
    result = " | ".join(parts)
    cfg = get_autopilot()
    cfg["last_run"] = datetime.now(timezone.utc).isoformat()
    cfg["last_result"] = result
    save_autopilot(cfg)
    return result


async def _autopilot_loop():
    while True:
        try:
            cfg = get_autopilot()
            if cfg.get("enabled"):
                due = True
                if cfg.get("last_run"):
                    try:
                        last = datetime.fromisoformat(cfg["last_run"])
                        due = datetime.now(timezone.utc) - last >= timedelta(
                            hours=max(1, int(cfg.get("interval_hours", 24))))
                    except ValueError:
                        pass
                if due:
                    await asyncio.to_thread(_run_autopilot)
        except Exception:
            pass  # never let the loop die
        await asyncio.sleep(300)


@app.get("/api/autopilot")
def read_autopilot():
    return get_autopilot()


@app.put("/api/autopilot")
def write_autopilot(body: AutopilotIn):
    cfg = get_autopilot()
    cfg.update(body.model_dump())
    save_autopilot(cfg)
    return cfg


@app.post("/api/autopilot/run")
def run_autopilot_now():
    return {"result": _run_autopilot(), **get_autopilot()}


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


@app.post("/api/content/topics")
def content_topics():
    return {"topics": ai.suggest_topics(get_profile())}


@app.post("/api/content/calendar")
def content_calendar(body: CalendarIn):
    """Generate a scheduled week (or N days) of posts, each pre-scheduled
    one day apart starting tomorrow, saved as drafts."""
    days = max(1, min(body.days, 14))
    posts = ai.generate_calendar(get_profile(), days, body.platforms)
    saved = []
    with get_db() as db:
        for p in posts:
            offset = int(p.get("day", 1))
            scheduled = (datetime.now() + timedelta(days=offset)).strftime("%Y-%m-%dT10:00")
            cur = db.execute(
                "INSERT INTO posts (platform, topic, content, hashtags, generated_by, status, scheduled_for) "
                "VALUES (?, ?, ?, ?, ?, 'scheduled', ?)",
                (p["platform"], p.get("topic", ""), p["content"], p.get("hashtags", ""),
                 p["generated_by"], scheduled),
            )
            saved.append({"id": cur.lastrowid, "scheduled_for": scheduled, **p})
    return {"posts": saved, "count": len(saved)}


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

@app.middleware("http")
async def _static_cache_headers(request, call_next):
    """Make static caching explicit instead of leaving it to browser heuristics.

    A versioned URL is immutable and can be cached hard. An unversioned one
    comes from an older cached shell, so it must revalidate — otherwise a
    phone keeps replaying a stale bundle and the UI silently half-works.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if request.query_params.get("v")
            else "no-cache, must-revalidate"
        )
    return response


def _asset_version(filename: str) -> str:
    """Short content hash used to bust caches for a static asset."""
    try:
        with open(os.path.join(STATIC_DIR, filename), "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()[:8]
    except OSError:
        return "0"


@app.get("/")
def index():
    """Serve the shell with versioned asset URLs.

    StaticFiles sends no Cache-Control, so browsers fall back to heuristic
    caching and a phone can keep running an old app.js against new markup —
    the UI half-updates and controls silently stop working. Stamping the
    content hash onto the URL makes a changed asset a new URL, and marking
    the shell no-cache means that new URL is actually seen.
    """
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace("/static/app.js", f"/static/app.js?v={_asset_version('app.js')}")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
