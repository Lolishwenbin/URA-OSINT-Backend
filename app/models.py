from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RawListing(BaseModel):
    """Schema for raw scraped data from TinyFish. Matches Cloe's agreed format."""
    source: str = "carousell"
    source_post_id: str = ""
    post_url: str = ""
    scraped_at: str = ""
    posted_at: Optional[str] = None
    raw_text: str = ""
    raw_price_text: str = ""
    images: List[str] = []
    poster_handle: str = ""
    language_detected: str = "en"
    raw_location_text: str = ""

    # Alternative field names from TinyFish
    title: Optional[str] = None
    price: Optional[str] = None
    seller_username: Optional[str] = None
    location: Optional[str] = None
    listing_url: Optional[str] = None
    description_snippet: Optional[str] = None


class ProcessedListing(BaseModel):
    """Schema after validation engine has processed the listing."""
    # Original fields
    source: str = "carousell"
    source_post_id: str = ""
    post_url: str = ""
    scraped_at: str = ""
    posted_at: Optional[str] = None
    raw_text: str = ""
    raw_price_text: str = ""
    images: List[str] = []
    poster_handle: str = ""
    language_detected: str = "en"
    raw_location_text: str = ""

    # Fields added by validation engine
    property_type: str = "Unknown"
    suspected_issue: str = "Unclassified"
    advertised_duration: str = "Unknown"
    priority: str = "Low"
    completeness: int = 0
    keywords_matched: List[str] = []
    notes: str = ""
    review_status: str = "Pending"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None


class SearchRequest(BaseModel):
    """Request body for the /search endpoint."""
    keywords: List[str]
    platform: str = "carousell"
    max_results: int = 10


class ReviewUpdate(BaseModel):
    """Request body for updating review status."""
    review_status: str
    reviewed_by: Optional[str] = None
