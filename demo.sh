#!/bin/bash
echo "Starting Multi-Environment DB Sync..."
docker-compose up -d
sleep 15
python src/db_sync.py
