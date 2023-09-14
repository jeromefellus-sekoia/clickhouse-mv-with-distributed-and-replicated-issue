#!/bin/bash
export USE_DISTRIBUTED=0
docker compose kill
docker compose down -v
docker compose up -d
docker compose up main