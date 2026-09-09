import re
from datetime import datetime


# ===== KEYWORD LIBRARY =====
KEYWORDS = {
    "short_stay": [
        "short term", "short-term", "short time",
        "daily rental", "weekly rental", "monthly rental",
        "flexible stay", "flexible lease", "flexible term",
        "transit stay", "transit room",
        "homestay",
        "no minimum stay",
        "move in immediately", "immediate move in",
        "available now", "available immediate"
    ],
    "dormitory": [
        "bed space", "bedspace",
        "bunk bed", "double decker",
        "partition room",
        "sharing room", "shared room", "share room",
        "workers welcome", "worker house", "worker room",
        "dormitory", "dorm ",
        "maid's room", "maids room"
    ],
    "pricing": [
        "per night", "per day", "per week",
        "/night", "/day", "/week",
        "no deposit",
        "no agent fee", "no agent commission", "no agent fees",
        "cash only",
        "per pax", "per person"
    ],
    "evasion": [
        "pm for details", "dm me",
        "message for price", "contact for details",
        "second landlord",
        "contract can discuss",
        "no landlord", "no owner staying", "no owner",
        "can register address", "can register hdb",
        "welcome all nationalities"
    ]
}

CHINESE_KEYWORDS = {
    "short_stay_cn": [
        "\u77ed\u79df", "\u65e5\u79df", "\u5468\u79df", "\u6708\u79df",
        "\u6c11\u5bbf", "\u7075\u6d3b\u79df", "\u8fc7\u6e21\u623f", "\u4e34\u65f6\u4f4f\u5bbf",
        "\u62ce\u5305\u5165\u4f4f", "\u5373\u523b\u5165\u4f4f"
    ],
    "dormitory_cn": [
        "\u5e8a\u4f4d", "\u4e0a\u4e0b\u94fa", "\u9694\u95f4", "\u9694\u65ad\u623f",
        "\u5408\u79df", "\u642d\u623f", "\u5ba2\u5de5\u53ef\u79df", "\u5de5\u4eba\u53ef\u4ee5\u4f4f",
        "\u56db\u4eba\u95f4", "\u5973\u5e8a\u4f4d", "\u5973\u56db\u4eba\u95f4"
    ],
    "pricing_cn": [
        "\u6bcf\u665a", "\u6bcf\u5929", "\u6bcf\u5468",
        "\u514d\u62bc\u91d1", "\u65e0\u9700\u62bc\u91d1",
        "\u514d\u4e2d\u4ecb\u8d39", "\u53ea\u6536\u73b0\u91d1"
    ],
    "evasion_cn": [
        "\u79c1\u804a", "\u79c1\u6211", "\u4ef7\u683c\u79c1\u804a",
        "\u4e8c\u623f\u4e1c", "\u4e0d\u67e5\u623f", "\u53ef\u62a5\u5730\u5740",
        "\u5408\u540c\u53ef\u4ee5\u8c08"
    ]
}

STANDALONE_TRIGGERS = ["daily", "weekly", "flexible", "dormitory", "bedspace"]

PAX_PATTERN = re.compile(r'(\d+)\s*(?:pax|person|persons|people)', re.IGNORECASE)
ADDRESS_PATTERN = re.compile(
    r'blk\s*\d|block\s*\d|\d{6}|street\s+\d|lorong\s+\d|lor\s+\d|'
    r'avenue\s+\d|drive\s+\d|road\s+\d|crescent|jalan\s+\w|bukit\s+\w',
    re.IGNORECASE
)


def match_keywords(text):
    text_lower = text.lower()
    matched = []

    for category, keywords in KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower and keyword not in matched:
                matched.append(keyword)

    for category, keywords in CHINESE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text and keyword not in matched:
                matched.append(keyword)

    for word in STANDALONE_TRIGGERS:
        if re.search(r'\b' + word + r'\b', text_lower) and word not in matched:
            already = any(word in m for m in matched)
            if not already:
                matched.append(word)

    pax_match = PAX_PATTERN.search(text_lower)
    if pax_match:
        pax_count = int(pax_match.group(1))
        if pax_count >= 2:
            pax_label = str(pax_count) + " pax"
            if pax_label not in matched:
                matched.append(pax_label)

    if re.search(r'\bworker[s]?\b', text_lower):
        worker_terms = ["workers welcome", "worker house", "worker room"]
        if not any(w in matched for w in worker_terms):
            matched.append("workers")

    return matched


def classify_property_type(text, location):
    combined = (text + " " + location).lower()
    if any(t in combined for t in ["shophouse", "shop house"]):
        return "Shophouse"
    if any(t in combined for t in ["condo", "condominium", "apartment", " ec ", "the glades", "orchid park", "alexis", "princess cove", "fernvale vine"]):
        return "Condo / EC"
    if any(t in combined for t in ["hdb", "blk ", "blk.", "block "]):
        return "HDB"
    if any(t in combined for t in ["landed", "terrace", "semi-d", "bungalow"]):
        return "Landed"
    return "Unknown"


def extract_duration(text):
    text_lower = text.lower()
    if any(w in text_lower for w in ["per night", "per day", "/night", "/day"]):
        return "Daily"
    if re.search(r'\bdaily\b', text_lower) and "daily cleaning" not in text_lower:
        return "Daily"
    if any(w in text_lower for w in ["per week", "/week"]):
        return "Weekly"
    if re.search(r'\bweekly\b', text_lower) and "weekly cleaning" not in text_lower:
        return "Weekly"
    if re.search(r'1\s*[-\u2013]\s*2\s*month', text_lower):
        return "1-2 months"
    if re.search(r'1\s*to\s*1\.5\s*month', text_lower):
        return "1-2 months"
    if "\u65e5\u79df" in text:
        return "Daily"
    if "\u5468\u79df" in text:
        return "Weekly"
    if "\u77ed\u79df" in text or "\u6708\u79df" in text:
        return "Short-term (unspecified)"
    if any(w in text_lower for w in ["short term", "short-term", "short time"]):
        return "Short-term (unspecified)"
    return "Unknown"


def classify_issue(keywords_matched):
    all_short = KEYWORDS["short_stay"] + KEYWORDS["pricing"] + CHINESE_KEYWORDS["short_stay_cn"] + CHINESE_KEYWORDS["pricing_cn"] + ["daily", "weekly", "flexible"]
    all_dorm = KEYWORDS["dormitory"] + CHINESE_KEYWORDS["dormitory_cn"] + ["workers"]
    has_short = any(k in all_short for k in keywords_matched)
    has_dorm = any(k in all_dorm for k in keywords_matched)
    has_pax = any("pax" in k for k in keywords_matched)
    if has_pax:
        has_dorm = True
    if has_short and has_dorm:
        return "Short-term + Dormitory"
    if has_dorm:
        return "Unauthorised Dormitory"
    if has_short:
        return "Short-term Accommodation"
    return "Unclassified"


def calculate_completeness(listing):
    fields = ["raw_text", "raw_price_text", "poster_handle", "raw_location_text", "post_url"]
    filled = sum(1 for f in fields if listing.get(f) and str(listing.get(f, "")).strip())
    return round((filled / len(fields)) * 100)


def get_pax_count(text):
    match = PAX_PATTERN.search(text.lower())
    return int(match.group(1)) if match else 0


def has_identifiable_address(text, location):
    combined = text + " " + location
    return bool(ADDRESS_PATTERN.search(combined))


def score_priority(listing, property_type, duration, keywords_matched, suspected_issue):
    text = ((listing.get("raw_text", "") or "") + " " + (listing.get("raw_price_text", "") or "")).lower()
    location = listing.get("raw_location_text", "") or ""
    has_addr = has_identifiable_address(text, location)
    has_explicit = duration in ["Daily", "Weekly", "1-2 months"]
    has_evidence = bool((listing.get("post_url", "") or "").strip())
    prop_known = property_type != "Unknown"
    pax = get_pax_count(text)
    is_dorm = "dormitory" in text or "dorm " in text

    if (is_dorm or pax >= 6) and (has_addr or prop_known):
        return "High"
    if pax >= 6 and any("worker" in str(k).lower() for k in keywords_matched):
        return "High"
    if prop_known and has_explicit and (has_addr or has_evidence):
        return "High"
    if has_explicit and has_addr:
        return "High"
    if len(keywords_matched) >= 4:
        return "High"
    if property_type == "Shophouse" and any(k in keywords_matched for k in ["workers", "dormitory", "worker house"]):
        return "High"
    if pax >= 8:
        return "High"

    if has_explicit:
        return "Medium"
    if is_dorm:
        return "Medium"
    if pax >= 4:
        return "Medium"
    if any(k in keywords_matched for k in ["bed space", "bedspace", "bunk bed", "double decker"]):
        return "Medium"
    if len(keywords_matched) >= 2:
        return "Medium"
    if len(keywords_matched) == 1:
        return "Medium"

    return "Low"


def generate_notes(listing, keywords_matched, property_type, duration, suspected_issue):
    text = (listing.get("raw_text", "") or "").lower()
    pax = get_pax_count(text)

    if "dormitory" in text and property_type == "Shophouse":
        return "Shophouse converted to dormitory, matches CNA Serangoon Road pattern"
    if "dormitory" in text and pax >= 6:
        return "Unauthorised dormitory with " + str(pax) + " occupants"
    if pax >= 6 and "worker" in text:
        return "Worker housing with " + str(pax) + " occupants, potential unauthorised dormitory"
    if "dormitory" in text:
        return "Listed as dormitory in residential area"
    if duration == "Daily":
        return "Per-night or per-day pricing on residential property"
    if duration == "Weekly":
        return "Per-week pricing, well under legal minimum stay"
    if duration == "1-2 months":
        return "Duration explicitly under 3-month legal minimum"
    if pax >= 4 and any(k in keywords_matched for k in ["bunk bed", "double decker"]):
        return str(pax) + " occupants with bunk beds, overcrowding indicator"
    if any(k in keywords_matched for k in ["bed space", "bedspace", "\u5e8a\u4f4d", "\u5973\u5e8a\u4f4d"]):
        return "Per-bed pricing, potential overcrowding"
    if any(k in keywords_matched for k in ["\u77ed\u79df", "\u65e5\u79df"]):
        return "Chinese language short-term rental listing"
    if any(k in keywords_matched for k in ["\u56db\u4eba\u95f4", "\u5973\u56db\u4eba\u95f4"]):
        return "Chinese multi-person room listing"
    if "no owner" in " ".join(keywords_matched) and "no agent" in " ".join(str(k) for k in keywords_matched):
        return "Multiple evasion signals: no agent, no owner"
    if any(k in keywords_matched for k in ["short term", "short-term"]):
        return "Advertised as short term rental"
    return ""


def normalize_listing(raw):
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
            listing["source_post_id"] = match.group(1) if match else "import-" + str(int(datetime.now().timestamp()))
        else:
            listing["source_post_id"] = "import-" + str(int(datetime.now().timestamp())) + "-" + str(abs(hash(listing.get("raw_text", ""))))
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


def process_listing(raw):
    listing = normalize_listing(raw)
    text = ((listing.get("raw_text", "") or "") + " " + (listing.get("raw_price_text", "") or ""))
    keywords_matched = match_keywords(text)
    property_type = classify_property_type(listing.get("raw_text", "") or "", listing.get("raw_location_text", "") or "")
    duration = extract_duration(text)
    issue = classify_issue(keywords_matched)
    completeness = calculate_completeness(listing)
    priority = score_priority(listing, property_type, duration, keywords_matched, issue)
    notes = generate_notes(listing, keywords_matched, property_type, duration, issue)
    listing["property_type"] = property_type
    listing["suspected_issue"] = issue
    listing["advertised_duration"] = duration
    listing["priority"] = priority
    listing["completeness"] = completeness
    listing["keywords_matched"] = keywords_matched
    listing["notes"] = notes
    listing["review_status"] = "Pending"
    return listing
