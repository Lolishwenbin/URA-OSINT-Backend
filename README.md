# URA OSINT Platform - Backend

Illegal accommodation listing detection platform for Carousell.
Built by Talons Laboratories.

## Setup

```
pip install -r requirements.txt
python run.py
```

Server runs at http://localhost:8000

## API Endpoints

- POST /import - Import raw scraped listings (auto-processes through validation engine)
- GET /listings - Get all listings with filters
- GET /listings/{id} - Get single listing
- PUT /listings/{id}/review - Update review status
- GET /stats - Summary statistics
- GET /export/csv - Export as CSV
- GET /export/json - Export as JSON
- DELETE /listings - Clear all data

## API Docs

Once running, visit http://localhost:8000/docs for interactive API documentation.
