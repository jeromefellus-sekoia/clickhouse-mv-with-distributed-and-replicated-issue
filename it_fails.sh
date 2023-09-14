#!/bin/bash
export USE_DISTRIBUTED=1
docker compose kill
docker compose down -v
docker compose up -d
docker compose up main