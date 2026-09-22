import os
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Connection string from Neon (or fallback to local SQLite for dev)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///listings.db"
)

# Neon sometimes gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS listings (
                id SERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                source_post_id TEXT UNIQUE NOT NULL,
                post_url TEXT,
                scraped_at TEXT,
                posted_at TEXT,
                raw_text TEXT,
                raw_price_text TEXT,
                images TEXT,
                poster_handle TEXT,
                language_detected TEXT,
                raw_location_text TEXT,
                property_type TEXT DEFAULT 'Unknown',
                suspected_issue TEXT DEFAULT 'Unclassified',
                advertised_duration TEXT DEFAULT 'Unknown',
                priority TEXT DEFAULT 'Low',
                completeness INTEGER DEFAULT 0,
                keywords_matched TEXT,
                notes TEXT,
                review_status TEXT DEFAULT 'Pending',
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))


def insert_listing(listing: dict) -> bool:
    """Insert a processed listing. Returns False if duplicate."""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO listings (
                    source, source_post_id, post_url, scraped_at, posted_at,
                    raw_text, raw_price_text, images, poster_handle,
                    language_detected, raw_location_text, property_type,
                    suspected_issue, advertised_duration, priority, completeness,
                    keywords_matched, notes, review_status
                ) VALUES (
                    :source, :source_post_id, :post_url, :scraped_at, :posted_at,
                    :raw_text, :raw_price_text, :images, :poster_handle,
                    :language_detected, :raw_location_text, :property_type,
                    :suspected_issue, :advertised_duration, :priority, :completeness,
                    :keywords_matched, :notes, :review_status
                )
            """), {
                "source": listing.get("source", "carousell"),
                "source_post_id": listing.get("source_post_id", ""),
                "post_url": listing.get("post_url", ""),
                "scraped_at": listing.get("scraped_at", datetime.now().isoformat()),
                "posted_at": listing.get("posted_at"),
                "raw_text": listing.get("raw_text", ""),
                "raw_price_text": listing.get("raw_price_text", ""),
                "images": json.dumps(listing.get("images", [])),
                "poster_handle": listing.get("poster_handle", ""),
                "language_detected": listing.get("language_detected", "en"),
                "raw_location_text": listing.get("raw_location_text", ""),
                "property_type": listing.get("property_type", "Unknown"),
                "suspected_issue": listing.get("suspected_issue", "Unclassified"),
                "advertised_duration": listing.get("advertised_duration", "Unknown"),
                "priority": listing.get("priority", "Low"),
                "completeness": listing.get("completeness", 0),
                "keywords_matched": json.dumps(listing.get("keywords_matched", [])),
                "notes": listing.get("notes", ""),
                "review_status": listing.get("review_status", "Pending"),
            })
        return True
    except Exception as e:
        # Duplicate source_post_id or other insertion error
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return False
        raise


def get_all_listings(filters: dict = None) -> list:
    query = "SELECT * FROM listings WHERE 1=1"
    params = {}

    if filters:
        if filters.get("priority"):
            query += " AND priority = :priority"
            params["priority"] = filters["priority"]
        if filters.get("suspected_issue"):
            query += " AND suspected_issue ILIKE :suspected_issue"
            params["suspected_issue"] = f"%{filters['suspected_issue']}%"
        if filters.get("property_type"):
            query += " AND property_type = :property_type"
            params["property_type"] = filters["property_type"]
        if filters.get("review_status"):
            query += " AND review_status = :review_status"
            params["review_status"] = filters["review_status"]
        if filters.get("search"):
            query += " AND (raw_text ILIKE :s OR poster_handle ILIKE :s OR raw_location_text ILIKE :s)"
            params["s"] = f"%{filters['search']}%"

    query += " ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    results = []
    for row in rows:
        item = dict(row)
        item["images"] = json.loads(item.get("images") or "[]")
        item["keywords_matched"] = json.loads(item.get("keywords_matched") or "[]")
        results.append(item)
    return results


def get_listing_by_id(listing_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM listings WHERE id = :id"),
            {"id": listing_id}
        ).mappings().first()
    if row:
        item = dict(row)
        item["images"] = json.loads(item.get("images") or "[]")
        item["keywords_matched"] = json.loads(item.get("keywords_matched") or "[]")
        return item
    return None


def update_review_status(listing_id: int, status: str, reviewed_by: str = None):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE listings
            SET review_status = :status,
                reviewed_by = :reviewed_by,
                reviewed_at = :reviewed_at
            WHERE id = :id
        """), {
            "status": status,
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now().isoformat(),
            "id": listing_id,
        })


def get_stats() -> dict:
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM listings")).scalar()
        high = conn.execute(text("SELECT COUNT(*) FROM listings WHERE priority = 'High'")).scalar()
        medium = conn.execute(text("SELECT COUNT(*) FROM listings WHERE priority = 'Medium'")).scalar()
        low = conn.execute(text("SELECT COUNT(*) FROM listings WHERE priority = 'Low'")).scalar()
        short_term = conn.execute(text("SELECT COUNT(*) FROM listings WHERE suspected_issue ILIKE '%Short-term%'")).scalar()
        dormitory = conn.execute(text("SELECT COUNT(*) FROM listings WHERE suspected_issue ILIKE '%Dormitory%'")).scalar()
        reviewed = conn.execute(text("SELECT COUNT(*) FROM listings WHERE review_status != 'Pending'")).scalar()
        pending = conn.execute(text("SELECT COUNT(*) FROM listings WHERE review_status = 'Pending'")).scalar()

    return {
        "total": total or 0,
        "high": high or 0,
        "medium": medium or 0,
        "low": low or 0,
        "short_term": short_term or 0,
        "dormitory": dormitory or 0,
        "reviewed": reviewed or 0,
        "pending": pending or 0,
    }


def delete_all():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM listings"))


def delete_by_id(listing_id: int) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM listings WHERE id = :id"),
            {"id": listing_id}
        )
        return result.rowcount > 0
