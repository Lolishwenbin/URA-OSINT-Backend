"""
TinyFish scraper module.
Calls TinyFish Search and Agent APIs to scrape Carousell listings.
"""

import os
import httpx
import asyncio
import re
from datetime import datetime
from typing import List, Dict
from urllib.parse import quote

TINYFISH_API_KEY = os.getenv("TINYFISH_API_KEY", "")
SEARCH_URL = "https://api.search.tinyfish.ai"
AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run"


async def search_carousell(keywords: str, max_results: int = 10) -> List[Dict]:
    """
    Search Carousell via TinyFish Search API.
    Returns raw listings mapped to the common schema.
    """
    if not TINYFISH_API_KEY:
        raise Exception("TINYFISH_API_KEY not set")

    # Scope to carousell.sg by including it in the query
    query = f"site:carousell.sg {keywords}"

    headers = {"X-API-Key": TINYFISH_API_KEY}
    params = {
        "query": query,
        "location": "SG",
        "language": "en",
    }

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(SEARCH_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    return _map_search_results(data, max_results)


async def scrape_carousell_agent(goal: str, url: str = "https://www.carousell.sg") -> List[Dict]:
    """
    Use TinyFish Agent for interactive scraping. Uses credits.
    """
    if not TINYFISH_API_KEY:
        raise Exception("TINYFISH_API_KEY not set")

    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "url": url,
        "goal": goal,
        "browser_profile": "stealth",
        "proxy_config": {"enabled": True, "type": "tetra", "country_code": "US"},
        "agent_config": {"max_duration_seconds": 120, "max_steps": 40},
    }

    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
        response = await client.post(AGENT_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return _map_agent_results(data)


def _map_search_results(data: Dict, max_results: int) -> List[Dict]:
    """
    Convert TinyFish Search response to common schema.
    Response format: {"query": "...", "results": [{"position", "site_name", "title", "snippet", "url"}]}
    """
    listings = []
    now = datetime.now().isoformat()

    results = data.get("results", [])

    for item in results[:max_results * 3]:  # Get extra since we may filter
        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        # Accept both individual listings and category pages
        # Category pages still have useful data Claude can analyze
        if "carousell.sg" not in url:
            continue

        # Extract identifier from URL (either /p/xxx or /q-xxx)
        match = re.search(r"/p/([^/?]+)|/q-(\d+)", url)
        if match:
            source_post_id = match.group(1) or f"category-{match.group(2)}-{abs(hash(url))}"
        else:
            source_post_id = f"tf-{int(datetime.now().timestamp())}-{abs(hash(url))}"

        combined_text = title
        if snippet:
            combined_text += " " + snippet

        listing = {
            "source": "carousell",
            "source_post_id": source_post_id,
            "post_url": url,
            "scraped_at": now,
            "posted_at": None,
            "raw_text": combined_text,
            "raw_price_text": _extract_price(snippet),
            "images": [],
            "poster_handle": "",
            "language_detected": _detect_language(combined_text),
            "raw_location_text": _extract_location(snippet),
        }
        listings.append(listing)

        if len(listings) >= max_results:
            break

    return listings


def _map_agent_results(data: Dict) -> List[Dict]:
    """Convert TinyFish Agent response to common schema."""
    listings = []
    now = datetime.now().isoformat()

    result = data.get("result", data)

    if isinstance(result, str):
        return _parse_text_listings(result)

    raw_listings = result.get("listings", []) or result.get("items", []) or result.get("data", [])

    for item in raw_listings:
        url = item.get("listing_url", "") or item.get("url", "") or item.get("post_url", "")
        title = item.get("title", "") or item.get("name", "") or item.get("raw_text", "")

        match = re.search(r"/p/([^/?]+)", url)
        source_post_id = match.group(1) if match else f"tf-agent-{int(datetime.now().timestamp())}-{abs(hash(title))}"

        listings.append({
            "source": "carousell",
            "source_post_id": source_post_id,
            "post_url": url,
            "scraped_at": now,
            "posted_at": None,
            "raw_text": (title + " " + item.get("description", "")).strip(),
            "raw_price_text": item.get("price", "") or item.get("raw_price_text", ""),
            "images": item.get("images", []),
            "poster_handle": item.get("seller_username", "") or item.get("poster_handle", ""),
            "language_detected": _detect_language(title),
            "raw_location_text": item.get("location", "") or item.get("raw_location_text", ""),
        })

    return listings


def _extract_price(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"S?\$[\d,]+(?:\.\d+)?(?:/\w+)?", text)
    return match.group(0) if match else ""


def _extract_location(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"(?:Blk|Block)\s*\d+\w*(?:\s+\w+){0,4}", text, re.IGNORECASE)
    if match:
        return match.group(0)
    match = re.search(r"Singapore\s+\d{6}|\b\d{6}\b", text)
    if match:
        return match.group(0)
    return ""


def _detect_language(text: str) -> str:
    if not text:
        return "en"
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return "zh" if cn_chars > 5 else "en"


def _parse_text_listings(text: str) -> List[Dict]:
    listings = []
    now = datetime.now().isoformat()

    lines = re.split(r"\n(?=\d+\.|\-|\*)", text)

    for i, line in enumerate(lines):
        line = line.strip()
        if len(line) < 20:
            continue

        title_match = re.search(r"(?:^\d+\.\s*|\*\*)([^*\n]+)", line)
        price_match = re.search(r"S?\$[\d,]+(?:\.\d+)?(?:/\w+)?", line)
        url_match = re.search(r"https?://\S+", line)

        title = title_match.group(1).strip() if title_match else line[:100]
        price = price_match.group(0) if price_match else ""
        url = url_match.group(0) if url_match else ""

        source_post_id = f"tf-text-{int(datetime.now().timestamp())}-{i}"
        if url:
            m = re.search(r"/p/([^/?]+)", url)
            if m:
                source_post_id = m.group(1)

        listings.append({
            "source": "carousell",
            "source_post_id": source_post_id,
            "post_url": url,
            "scraped_at": now,
            "posted_at": None,
            "raw_text": title,
            "raw_price_text": price,
            "images": [],
            "poster_handle": "",
            "language_detected": _detect_language(title),
            "raw_location_text": _extract_location(line),
        })

    return listings


def search_carousell_sync(keywords: str, max_results: int = 10) -> List[Dict]:
    return asyncio.run(search_carousell(keywords, max_results))


def scrape_carousell_agent_sync(goal: str, url: str = "https://www.carousell.sg") -> List[Dict]:
    return asyncio.run(scrape_carousell_agent(goal, url))
