#!/usr/bin/env bash
# build.sh — Render runs this before starting the app

set -o errexit  # exit on any error

pip install -r requirements.txt

# Create the uploads directory if it doesn't exist
mkdir -p uploads

# Initialize the database tables
python -c "
from app import app
from models import init_db
init_db(app)
print('Database tables created.')
"
