#!/bin/bash
# Run the URA OSINT Platform backend
# First time: pip install -r requirements.txt
# Then: python run.py or bash run.sh

cd "$(dirname "$0")"
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
