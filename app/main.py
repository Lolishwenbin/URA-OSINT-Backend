from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional, List
import json
import csv
import io
from datetime import datetime

from app.database import init_db, insert_listing, get_all_listings, get_listing_by_id, update_review_status, get_stats, delete_all, delete_by_id
from app.ai_validator import process_listing
from app.scraper import search_carousell, scrape_carousell_agent
from app.models import RawListing, SearchRequest, ReviewUpdate

app = FastAPI(title="URA OSINT Platform", version="1.0.0")

# Allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database on startup
@app.on_event("startup")
def startup():
    init_db()


# ===== ROUTES =====

@app.get("/")
def root():
    return {"status": "running", "name": "URA OSINT Platform", "version": "1.0.0"}


@app.post("/import")
def import_listings(listings: List[dict]):
    """Import raw scraped listings. Auto-processes each one through the validation engine."""
    results = {"added": 0, "skipped": 0, "processed": []}

    for raw in listings:
        # Handle TinyFish nested formats
        if "listings" in raw:
            for item in raw["listings"]:
                processed = process_listing(item)
                if insert_listing(processed):
                    results["added"] += 1
                    results["processed"].append({
                        "text": processed.get("raw_text", "")[:80],
                        "priority": processed.get("priority"),
                        "issue": processed.get("suspected_issue"),
                        "keywords": len(processed.get("keywords_matched", []))
                    })
                else:
                    results["skipped"] += 1
        elif "results" in raw:
            for item in raw["results"]:
                processed = process_listing(item)
                if insert_listing(processed):
                    results["added"] += 1
                    results["processed"].append({
                        "text": processed.get("raw_text", "")[:80],
                        "priority": processed.get("priority"),
                        "issue": processed.get("suspected_issue"),
                        "keywords": len(processed.get("keywords_matched", []))
                    })
                else:
                    results["skipped"] += 1
        else:
            processed = process_listing(raw)
            if insert_listing(processed):
                results["added"] += 1
                results["processed"].append({
                    "text": processed.get("raw_text", "")[:80],
                    "priority": processed.get("priority"),
                    "issue": processed.get("suspected_issue"),
                    "keywords": len(processed.get("keywords_matched", []))
                })
            else:
                results["skipped"] += 1

    return results


@app.get("/listings")
def list_listings(
    priority: Optional[str] = None,
    suspected_issue: Optional[str] = None,
    property_type: Optional[str] = None,
    review_status: Optional[str] = None,
    search: Optional[str] = None,
):
    """Get all listings with optional filters."""
    filters = {}
    if priority:
        filters["priority"] = priority
    if suspected_issue:
        filters["suspected_issue"] = suspected_issue
    if property_type:
        filters["property_type"] = property_type
    if review_status:
        filters["review_status"] = review_status
    if search:
        filters["search"] = search

    return get_all_listings(filters)


@app.get("/listings/{listing_id}")
def get_listing(listing_id: int):
    """Get a single listing by ID."""
    listing = get_listing_by_id(listing_id)
    if not listing:
        return {"error": "Listing not found"}
    return listing


@app.put("/listings/{listing_id}/review")
def review_listing(listing_id: int, update: ReviewUpdate):
    """Update the review status of a listing."""
    update_review_status(listing_id, update.review_status, update.reviewed_by)
    return {"status": "updated", "listing_id": listing_id, "review_status": update.review_status}


@app.get("/stats")
def stats():
    """Get summary statistics."""
    return get_stats()


@app.get("/export/csv")
def export_csv(
    priority: Optional[str] = None,
    suspected_issue: Optional[str] = None,
    property_type: Optional[str] = None,
    review_status: Optional[str] = None,
):
    """Export filtered listings as CSV."""
    filters = {}
    if priority:
        filters["priority"] = priority
    if suspected_issue:
        filters["suspected_issue"] = suspected_issue
    if property_type:
        filters["property_type"] = property_type
    if review_status:
        filters["review_status"] = review_status

    listings = get_all_listings(filters)

    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "source", "source_post_id", "post_url", "scraped_at", "posted_at",
        "raw_text", "raw_price_text", "poster_handle", "language_detected",
        "raw_location_text", "property_type", "suspected_issue",
        "advertised_duration", "priority", "completeness",
        "keywords_matched", "notes", "review_status"
    ]
    writer.writerow(headers)

    for listing in listings:
        writer.writerow([
            listing.get(h, "") if h != "keywords_matched"
            else "; ".join(listing.get("keywords_matched", []))
            for h in headers
        ])

    output.seek(0)
    filename = f"ura-osint-export-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/export/json")
def export_json(
    priority: Optional[str] = None,
    suspected_issue: Optional[str] = None,
    property_type: Optional[str] = None,
    review_status: Optional[str] = None,
):
    """Export filtered listings as JSON."""
    filters = {}
    if priority:
        filters["priority"] = priority
    if suspected_issue:
        filters["suspected_issue"] = suspected_issue
    if property_type:
        filters["property_type"] = property_type
    if review_status:
        filters["review_status"] = review_status

    listings = get_all_listings(filters)
    return listings


@app.delete("/listings/{listing_id}")
def delete_single(listing_id: int):
    """Delete a single listing by ID."""
    if delete_by_id(listing_id):
        return {"status": "deleted", "listing_id": listing_id}
    return {"error": "Listing not found", "listing_id": listing_id}


@app.delete("/listings")
def clear_all():
    """Delete all listings. Use with caution."""
    delete_all()
    return {"status": "all listings deleted"}


@app.post("/search")
async def search(request: SearchRequest):
    """
    Search Carousell via TinyFish, auto-process results, and save to database.
    User just provides keywords, everything else happens automatically.
    """
    all_results = {
        "keywords_searched": request.keywords,
        "raw_scraped": 0,
        "added": 0,
        "skipped": 0,
        "failed": 0,
        "listings": [],
        "errors": [],
    }

    for keyword in request.keywords:
        try:
            raw_listings = await search_carousell(keyword, request.max_results)
            all_results["raw_scraped"] += len(raw_listings)

            for raw in raw_listings:
                try:
                    processed = process_listing(raw)
                    if insert_listing(processed):
                        all_results["added"] += 1
                        all_results["listings"].append({
                            "text": (processed.get("raw_text", "") or "")[:80],
                            "priority": processed.get("priority"),
                            "issue": processed.get("suspected_issue"),
                            "keyword_used": keyword,
                        })
                    else:
                        all_results["skipped"] += 1
                except Exception as e:
                    all_results["failed"] += 1
                    all_results["errors"].append(f"Processing failed: {str(e)[:80]}")
        except Exception as e:
            all_results["errors"].append(f"Search '{keyword}' failed: {str(e)[:100]}")

    return all_results


@app.post("/search/agent")
async def search_agent(goal: str, url: str = "https://www.carousell.sg"):
    """
    Use TinyFish Agent for more complex scraping (interactive, slower).
    Use when Search doesn't return enough results.
    """
    try:
        raw_listings = await scrape_carousell_agent(goal, url)
        results = {
            "raw_scraped": len(raw_listings),
            "added": 0,
            "skipped": 0,
            "failed": 0,
            "listings": [],
        }

        for raw in raw_listings:
            try:
                processed = process_listing(raw)
                if insert_listing(processed):
                    results["added"] += 1
                    results["listings"].append({
                        "text": (processed.get("raw_text", "") or "")[:80],
                        "priority": processed.get("priority"),
                        "issue": processed.get("suspected_issue"),
                    })
                else:
                    results["skipped"] += 1
            except Exception as e:
                results["failed"] += 1

        return results
    except Exception as e:
        return {"error": str(e)}


@app.get("/keywords")
def get_default_keywords():
    """
    Return the default keyword library that reviewers can pick from.
    """
    return {
        "short_stay": [
            "short term rental Singapore",
            "daily rental room",
            "weekly rental Singapore",
            "monthly rental room",
            "flexible lease room",
            "transit stay room",
        ],
        "dormitory": [
            "bed space rent",
            "bedspace room",
            "bunk bed room rent",
            "worker dormitory room",
            "sharing room bed",
        ],
        "pricing": [
            "no agent fee room rent",
            "no deposit room rent",
        ],
        "chinese": [
            "短租 房间",
            "床位 出租",
            "日租 房间",
            "民宿 住宿",
        ],
    }
