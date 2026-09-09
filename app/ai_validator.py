"""
AI-powered validation engine using Anthropic Claude API.
This replaces the rule-based validator with actual language understanding.
"""

import os
import json
import re
from datetime import datetime
from anthropic import Anthropic

# API key from environment variable
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-5"

client = Anthropic(api_key=API_KEY) if API_KEY else None


SYSTEM_PROMPT = """You are an OSINT analyst for Singapore's URA (Urban Redevelopment Authority) helping detect illegal accommodation listings.

Singapore rental law:
- Private property (condo, landed): minimum rental period is 3 months
- HDB flats: minimum rental period is 6 months
- Any per-night, per-day, per-week, or under-minimum rental is ILLEGAL
- Overcrowding: more than 6 unrelated persons in a residential unit is a violation
- Bunk beds, partition rooms, per-bed pricing in residential units suggests unauthorised dormitory

Your job: analyze a rental listing and extract structured data. Focus on facts stated in the listing. Do NOT guess - if information is missing, mark it as Unknown.

Return ONLY valid JSON in this exact format (no other text before or after):

{
  "property_type": "HDB" or "Condo / EC" or "Landed" or "Shophouse" or "Unknown",
  "suspected_issue": "Short-term Accommodation" or "Unauthorised Dormitory" or "Short-term + Dormitory" or "Unclassified",
  "advertised_duration": "Daily" or "Weekly" or "1-2 months" or "Short-term (unspecified)" or "Unknown",
  "priority": "High" or "Medium" or "Low",
  "keywords_matched": [list of key indicators found in listing text],
  "notes": "one-sentence explanation of why this listing was flagged and what verification is needed",
  "reasoning": "brief internal reasoning, one sentence"
}

Priority definitions (STRICT):
- High: Property identifiable (address/postal code visible) AND illegal duration explicitly stated AND evidence preserved. OR dormitory with 6+ occupants at identifiable location. OR shophouse used as worker housing.
- Medium: Explicit short-stay offer but property/address unclear. OR bed space/dormitory indicators without confirmed address. OR under-market pricing with multiple weak signals.
- Low: Only vague wording. No duration stated. Property and location unknown.

Understand both English and Chinese listings. Chinese terms to recognize:
- 短租 (short rent), 日租 (daily rent), 周租 (weekly rent), 月租 (monthly rent)
- 民宿 (homestay), 灵活租 (flexible rent), 过渡房 (transit room)
- 床位 (bed space), 上下铺 (bunk bed), 隔间 (partition room), 合租 (shared rental)
- 四人间 (4-person room), 女床位 (female bed space)
- 二房东 (second landlord), 私聊 (PM me), 不查房 (no inspections), 可报地址 (can register address)

Return ONLY the JSON. No markdown, no code blocks, no explanation."""


def normalize_listing(raw):
    """Map alternative TinyFish field names to the common schema."""
    listing = dict(raw)

    if listing.get("title") and not listing.get("raw_text"):
        listing["raw_text"] = listing["title"]
    if listing.get("price") and not listing.get("raw_price_text"):
        listing["raw_price_text"] = listing["price"]
    if listing.get("seller_username") and not listing.get("poster_handle"):
        listing["poster_handle"] = listing["seller_username"]
    if listing.get("location") and not listing.get("raw_location_text"):
        listing["raw_location_text"] = listing["location"]
    if listing.get("listing_url") and not listing.get("post_url"):
        listing["post_url"] = listing["listing_url"]
    if listing.get("description_snippet"):
        listing["raw_text"] = ((listing.get("raw_text", "") or "") + " " + listing["description_snippet"]).strip()

    if not listing.get("source_post_id"):
        if listing.get("post_url"):
            match = re.search(r'/p/([^/]+)', listing["post_url"])
            listing["source_post_id"] = match.group(1) if match else f"import-{int(datetime.now().timestamp())}"
        else:
            listing["source_post_id"] = f"import-{int(datetime.now().timestamp())}-{abs(hash(listing.get('raw_text', '')))}"

    if not listing.get("source"):
        listing["source"] = "carousell"
    if not listing.get("scraped_at"):
        listing["scraped_at"] = datetime.now().isoformat()
    if listing.get("images") is None:
        listing["images"] = []
    if not listing.get("language_detected"):
        text = listing.get("raw_text", "") or ""
        cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        listing["language_detected"] = "zh" if cn_chars > 5 else "en"
    if not listing.get("posted_at"):
        listing["posted_at"] = None

    return listing


def calculate_completeness(listing):
    fields = ["raw_text", "raw_price_text", "poster_handle", "raw_location_text", "post_url"]
    filled = sum(1 for f in fields if listing.get(f) and str(listing.get(f, "")).strip())
    return round((filled / len(fields)) * 100)


def analyze_with_claude(listing):
    """Send listing to Claude for analysis. Returns extracted fields."""
    if not client:
        raise Exception("ANTHROPIC_API_KEY not set. Set it as an environment variable.")

    user_message = f"""Analyze this Carousell rental listing:

Title/Text: {listing.get('raw_text', '')}
Price: {listing.get('raw_price_text', 'not stated')}
Location: {listing.get('raw_location_text', 'not stated')}
Seller: {listing.get('poster_handle', 'unknown')}
URL: {listing.get('post_url', 'not available')}

Return the JSON analysis."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    response_text = response.content[0].text.strip()

    # Handle case where model wraps in code blocks
    if response_text.startswith("```"):
        response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)

    try:
        result = json.loads(response_text)
        return result
    except json.JSONDecodeError as e:
        # Fallback: extract JSON from response
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise Exception(f"Could not parse Claude response as JSON: {response_text[:200]}")


def process_listing(raw):
    """Main function: normalize the listing and send to Claude for analysis."""
    listing = normalize_listing(raw)

    # Skip AI analysis if listing has no meaningful text
    if not listing.get("raw_text", "").strip():
        listing["property_type"] = "Unknown"
        listing["suspected_issue"] = "Unclassified"
        listing["advertised_duration"] = "Unknown"
        listing["priority"] = "Low"
        listing["completeness"] = calculate_completeness(listing)
        listing["keywords_matched"] = []
        listing["notes"] = "No text content to analyze"
        listing["review_status"] = "Pending"
        return listing

    try:
        analysis = analyze_with_claude(listing)

        listing["property_type"] = analysis.get("property_type", "Unknown")
        listing["suspected_issue"] = analysis.get("suspected_issue", "Unclassified")
        listing["advertised_duration"] = analysis.get("advertised_duration", "Unknown")
        listing["priority"] = analysis.get("priority", "Low")
        listing["keywords_matched"] = analysis.get("keywords_matched", [])
        listing["notes"] = analysis.get("notes", "")
        listing["completeness"] = calculate_completeness(listing)
        listing["review_status"] = "Pending"

    except Exception as e:
        # If AI fails, mark for manual review
        listing["property_type"] = "Unknown"
        listing["suspected_issue"] = "Unclassified"
        listing["advertised_duration"] = "Unknown"
        listing["priority"] = "Low"
        listing["completeness"] = calculate_completeness(listing)
        listing["keywords_matched"] = []
        listing["notes"] = f"AI analysis failed: {str(e)[:100]}"
        listing["review_status"] = "Pending"

    return listing
