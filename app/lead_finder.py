"""Discover potential customers from public sources (Reddit, Hacker News).

Both sources are free public JSON APIs — no keys required. Results are
scored for buying intent so the hottest leads float to the top.
"""
import re
import time

import httpx

USER_AGENT = "AIGrowthEngine/1.0 (lead discovery; respectful, low volume)"

# Phrases that signal someone is actively looking for help / a solution.
INTENT_PHRASES = [
    r"how (do|can|should) i",
    r"looking for",
    r"any (recommendation|advice|tips|ideas)",
    r"recommend",
    r"help me",
    r"where (do|can) i start",
    r"is it (possible|worth)",
    r"struggling",
    r"want to (make|earn|start|learn|grow)",
    r"trying to (make|earn|start|learn|grow)",
    r"best way to",
    r"has anyone",
    r"advice",
    r"beginner",
    r"getting started",
    r"side hustle",
    r"extra (money|income|cash)",
]
_INTENT_RE = [re.compile(p, re.IGNORECASE) for p in INTENT_PHRASES]


def score_lead(title: str, snippet: str, created_utc: float, engagement: int) -> int:
    """Score 0-100 for buying intent."""
    text = f"{title} {snippet}"
    score = 0
    # Intent phrases: up to 60 points
    hits = sum(1 for rx in _INTENT_RE if rx.search(text))
    score += min(hits * 15, 60)
    # Question marks signal someone seeking answers
    if "?" in title:
        score += 10
    # Recency: up to 20 points (fresh in the last 7 days)
    age_days = max(0.0, (time.time() - created_utc) / 86400)
    if age_days <= 1:
        score += 20
    elif age_days <= 3:
        score += 12
    elif age_days <= 7:
        score += 6
    # Engagement: up to 10 points
    score += min(engagement // 5, 10)
    return min(score, 100)


def search_reddit(keyword: str, subreddits: list[str], limit: int = 25) -> list[dict]:
    """Search Reddit's public JSON API. No key needed, but rate-limited —
    keep request volume low and set a real User-Agent."""
    results = []
    headers = {"User-Agent": USER_AGENT}
    # Global search plus per-subreddit search on the first few communities
    urls = [("https://www.reddit.com/search.json", {"q": keyword, "sort": "new", "limit": str(limit), "t": "month"})]
    for sub in subreddits[:3]:
        urls.append((
            f"https://www.reddit.com/r/{sub}/search.json",
            {"q": keyword, "restrict_sr": "1", "sort": "new", "limit": "10", "t": "month"},
        ))

    with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as client:
        for url, params in urls:
            try:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    continue
                for child in resp.json().get("data", {}).get("children", []):
                    d = child.get("data", {})
                    permalink = d.get("permalink", "")
                    if not permalink:
                        continue
                    snippet = (d.get("selftext") or "")[:400]
                    results.append({
                        "source": "reddit",
                        "source_url": f"https://www.reddit.com{permalink}",
                        "title": d.get("title", "")[:300],
                        "snippet": snippet,
                        "author": d.get("author", ""),
                        "community": f"r/{d.get('subreddit', '')}",
                        "intent_score": score_lead(
                            d.get("title", ""), snippet,
                            d.get("created_utc", 0),
                            int(d.get("score", 0)) + int(d.get("num_comments", 0)),
                        ),
                    })
            except httpx.HTTPError:
                continue
    return results


def search_hackernews(keyword: str, limit: int = 25) -> list[dict]:
    """Search Hacker News via the free Algolia API."""
    results = []
    since = int(time.time()) - 30 * 86400
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": keyword,
                    "tags": "(story,ask_hn,comment)",
                    "numericFilters": f"created_at_i>{since}",
                    "hitsPerPage": str(limit),
                },
            )
            resp.raise_for_status()
            for hit in resp.json().get("hits", []):
                object_id = hit.get("objectID")
                if not object_id:
                    continue
                title = hit.get("title") or hit.get("story_title") or ""
                text = re.sub(r"<[^>]+>", " ", hit.get("comment_text") or hit.get("story_text") or "")[:400]
                if not title and not text:
                    continue
                results.append({
                    "source": "hackernews",
                    "source_url": f"https://news.ycombinator.com/item?id={object_id}",
                    "title": (title or text[:120])[:300],
                    "snippet": text,
                    "author": hit.get("author", ""),
                    "community": "Hacker News",
                    "intent_score": score_lead(
                        title, text,
                        hit.get("created_at_i", 0),
                        int(hit.get("points") or 0) + int(hit.get("num_comments") or 0),
                    ),
                })
    except httpx.HTTPError:
        pass
    return results


def discover(keywords: list[str], subreddits: list[str], sources: list[str]) -> list[dict]:
    """Run discovery across sources for each keyword; dedupe by URL."""
    seen: dict[str, dict] = {}
    for kw in keywords[:4]:  # cap request volume
        found = []
        if "reddit" in sources:
            found += search_reddit(kw, subreddits)
        if "hackernews" in sources:
            found += search_hackernews(kw)
        for lead in found:
            url = lead["source_url"]
            if url not in seen or lead["intent_score"] > seen[url]["intent_score"]:
                seen[url] = lead
    leads = sorted(seen.values(), key=lambda x: x["intent_score"], reverse=True)
    return leads
