#!/usr/bin/env bash
set -euo pipefail
cd /opt/vedanta/deploy
umask 077
if [[ ! -f .env ]]; then
    cp .env.example .env
    sed -i 's/^DOMAIN=.*/DOMAIN=vedant-a.duckdns.org/' .env
fi
if [[ ! -f runtime.env ]]; then
    cp runtime.env.example runtime.env
fi
# A small encrypted-root-volume swap file supports builds on 1 GiB instances.
if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
fi
export COMPOSE_PARALLEL_LIMIT=1
docker compose build api
docker compose build web
python3 /opt/vedanta/deploy/initialize-login.py
docker compose run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose up -d --no-build
docker compose ps
