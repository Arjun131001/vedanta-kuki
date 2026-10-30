#!/usr/bin/env bash
set -euo pipefail
cd /opt/vedanta/deploy
if [[ ! -f .env || ! -f runtime.env || ! -f /etc/vedanta/duckdns.env ]]; then
    echo 'Configure deploy/.env, deploy/runtime.env and /etc/vedanta/duckdns.env first.' >&2
    exit 1
fi
if grep -q REPLACE_WITH_BCRYPT_HASH .env; then
    echo 'Replace the demo password placeholder first.' >&2
    exit 1
fi
chmod 600 .env runtime.env /etc/vedanta/duckdns.env
cp duckdns-update.service duckdns-update.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start duckdns-update.service
systemctl enable --now duckdns-update.timer
docker compose config --quiet
docker compose build api web
docker compose run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose up -d --no-build
docker compose ps
echo 'Check HTTPS health, uploads, worker processing and AWS billing before sharing the address.'
