import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "listings.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def insert_listing(listing: dict) -> bool:
    """Insert a processed listing into the database. Returns False if duplicate."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO listings (
                source, source_post_id, post_url, scraped_at, posted_at,
                raw_text, raw_price_text, images, poster_handle,
                language_detected, raw_location_text, property_type,
                suspected_issue, advertised_duration, priority, completeness,
                keywords_matched, notes, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing.get("source", "carousell"),
            listing.get("source_post_id", ""),
            listing.get("post_url", ""),
            listing.get("scraped_at", datetime.now().isoformat()),
            listing.get("posted_at"),
            listing.get("raw_text", ""),
            listing.get("raw_price_text", ""),
            json.dumps(listing.get("images", [])),
            listing.get("poster_handle", ""),
            listing.get("language_detected", "en"),
            listing.get("raw_location_text", ""),
            listing.get("property_type", "Unknown"),
            listing.get("suspected_issue", "Unclassified"),
            listing.get("advertised_duration", "Unknown"),
            listing.get("priority", "Low"),
            listing.get("completeness", 0),
            json.dumps(listing.get("keywords_matched", [])),
            listing.get("notes", ""),
            listing.get("review_status", "Pending"),
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_all_listings(filters: dict = None) -> list:
    """Retrieve listings with optional filters."""
    conn = get_connection()
    query = "SELECT * FROM listings WHERE 1=1"
    params = []

    if filters:
        if filters.get("priority"):
            query += " AND priority = ?"
            params.append(filters["priority"])
        if filters.get("suspected_issue"):
            query += " AND suspected_issue LIKE ?"
            params.append(f"%{filters['suspected_issue']}%")
        if filters.get("property_type"):
            query += " AND property_type = ?"
            params.append(filters["property_type"])
        if filters.get("review_status"):
            query += " AND review_status = ?"
            params.append(filters["review_status"])
        if filters.get("search"):
            query += " AND (raw_text LIKE ? OR poster_handle LIKE ? OR raw_location_text LIKE ?)"
            s = f"%{filters['search']}%"
            params.extend([s, s, s])

    query += " ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for row in rows:
        item = dict(row)
        item["images"] = json.loads(item.get("images", "[]"))
        item["keywords_matched"] = json.loads(item.get("keywords_matched", "[]"))
        results.append(item)
    return results


def get_listing_by_id(listing_id: int) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    if row:
        item = dict(row)
        item["images"] = json.loads(item.get("images", "[]"))
        item["keywords_matched"] = json.loads(item.get("keywords_matched", "[]"))
        return item
    return None


def update_review_status(listing_id: int, status: str, reviewed_by: str = None):
    conn = get_connection()
    conn.execute("""
        UPDATE listings SET review_status = ?, reviewed_by = ?, reviewed_at = ?
        WHERE id = ?
    """, (status, reviewed_by, datetime.now().isoformat(), listing_id))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    high = conn.execute("SELECT COUNT(*) FROM listings WHERE priority = 'High'").fetchone()[0]
    medium = conn.execute("SELECT COUNT(*) FROM listings WHERE priority = 'Medium'").fetchone()[0]
    low = conn.execute("SELECT COUNT(*) FROM listings WHERE priority = 'Low'").fetchone()[0]
    short_term = conn.execute("SELECT COUNT(*) FROM listings WHERE suspected_issue LIKE '%Short-term%'").fetchone()[0]
    dormitory = conn.execute("SELECT COUNT(*) FROM listings WHERE suspected_issue LIKE '%Dormitory%'").fetchone()[0]
    reviewed = conn.execute("SELECT COUNT(*) FROM listings WHERE review_status != 'Pending'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM listings WHERE review_status = 'Pending'").fetchone()[0]
    conn.close()

    return {
        "total": total,
        "high": high,
        "medium": medium,
        "low": low,
        "short_term": short_term,
        "dormitory": dormitory,
        "reviewed": reviewed,
        "pending": pending,
    }


def delete_all():
    conn = get_connection()
    conn.execute("DELETE FROM listings")
    conn.commit()
    conn.close()


def delete_by_id(listing_id: int) -> bool:
    """Delete a single listing by ID. Returns True if deleted."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted
