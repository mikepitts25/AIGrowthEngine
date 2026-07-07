"""Lead enrichment: probe a business's website to sharpen the pitch.

Automates the cold-call prep checklist: does this business have online
booking? A working website at all? An email address we can reach? Each
answer adjusts the missed-call pain score and lands in the lead's meta
so drafts and call sheets can use it.
"""
import json
import re

import httpx

from .database import get_db

USER_AGENT = "Mozilla/5.0 (compatible; AIGrowthEngine/1.0; local business research)"

# Presence of any of these = they already take bookings online (less pain).
BOOKING_SIGNALS = [
    "calendly", "housecallpro", "housecall pro", "servicetitan", "jobber",
    "acuityscheduling", "squareup.com/appointments", "setmore", "youcanbook",
    "book online", "book now", "schedule online", "schedule service",
    "request appointment", "book an appointment", "online booking",
]
CHAT_SIGNALS = ["intercom", "drift.com", "tawk.to", "livechat", "tidio", "crisp.chat", "podium"]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_JUNK_EMAIL_RE = re.compile(
    r"(\.png|\.jpg|\.jpeg|\.gif|\.webp|\.svg|\.css|\.js)$|"
    r"^(noreply|no-reply|donotreply)@|@(example|sentry|wixpress|schema)\.",
    re.IGNORECASE,
)


def _extract_emails(html: str) -> list[str]:
    seen, out = set(), []
    for m in _EMAIL_RE.findall(html):
        e = m.lower().strip(".")
        if e not in seen and not _JUNK_EMAIL_RE.search(e):
            seen.add(e)
            out.append(e)
    return out[:3]


def probe_website(url: str) -> dict:
    """Fetch the site (+ /contact if easy) and report what we learn."""
    result = {
        "reachable": False, "has_booking": False, "has_chat": False,
        "emails": [], "checked_url": url,
    }
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    pages = []
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=12,
                          follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code < 400:
                result["reachable"] = True
                pages.append(resp.text[:400_000])
                # a contact page is where emails usually hide
                base = str(resp.url).rstrip("/")
                for path in ("/contact", "/contact-us"):
                    try:
                        c = client.get(base + path)
                        if c.status_code < 400:
                            pages.append(c.text[:200_000])
                            break
                    except httpx.HTTPError:
                        pass
    except httpx.HTTPError:
        return result

    html = "\n".join(pages).lower()
    result["has_booking"] = any(s in html for s in BOOKING_SIGNALS)
    result["has_chat"] = any(s in html for s in CHAT_SIGNALS)
    result["emails"] = _extract_emails("\n".join(pages))
    return result


def enrich_lead(lead: dict) -> dict | None:
    """Run enrichment for one business lead. Returns the updates applied
    (score delta, email, new signals) or None if there's nothing to probe."""
    try:
        meta = json.loads(lead.get("meta") or "{}")
    except json.JSONDecodeError:
        meta = {}
    reasons: list[str] = meta.get("score_reasons", [])
    score = int(lead.get("intent_score") or 0)
    email = lead.get("email") or ""

    website = (lead.get("website") or "").strip()
    if website:
        probe = probe_website(website)
        meta["enrichment"] = probe
        if not probe["reachable"]:
            score += 20
            reasons.append("website unreachable — the phone is their entire funnel")
        elif not probe["has_booking"]:
            score += 15
            reasons.append("website has NO online booking — callers who can't get through book a competitor")
        else:
            reasons.append("has online booking — pitch after-hours phone coverage instead")
        if probe["emails"] and not email:
            email = probe["emails"][0]
            reasons.append(f"email found on site: {email}")
    elif lead.get("kind") == "business":
        meta["enrichment"] = {"reachable": False, "checked_url": "", "note": "no website listed"}
    else:
        return None  # nothing to probe for person leads

    meta["score_reasons"] = reasons
    updates = {"intent_score": min(score, 100), "email": email, "meta": json.dumps(meta)}
    with get_db() as db:
        db.execute(
            "UPDATE leads SET intent_score = ?, email = ?, meta = ? WHERE id = ?",
            (updates["intent_score"], updates["email"], updates["meta"], lead["id"]),
        )
    return updates


def enrich_business_leads(lead_ids: list[int] | None = None, limit: int = 25) -> dict:
    """Enrich business leads that haven't been enriched yet (or specific ids).
    Returns summary counts."""
    sql = "SELECT * FROM leads WHERE kind = 'business'"
    params: list = []
    if lead_ids:
        sql += f" AND id IN ({','.join('?' * len(lead_ids))})"
        params += lead_ids
    else:
        sql += " AND meta NOT LIKE '%\"enrichment\"%' AND status != 'archived'"
    sql += " ORDER BY intent_score DESC LIMIT ?"
    params.append(limit)
    with get_db() as db:
        leads = [dict(r) for r in db.execute(sql, params)]

    enriched = emails_found = 0
    for lead in leads:
        updates = enrich_lead(lead)
        if updates is not None:
            enriched += 1
            if updates["email"] and not lead.get("email"):
                emails_found += 1
    return {"checked": len(leads), "enriched": enriched, "emails_found": emails_found}
