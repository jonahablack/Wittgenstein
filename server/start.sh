#!/bin/bash
# Production startup script for Render

# Download NLTK data
python -c "import nltk; nltk.download('punkt')"

# Start the application with Gunicorn
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 300 app:app
