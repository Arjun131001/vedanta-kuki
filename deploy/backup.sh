#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
mkdir -p backups
chmod 700 backups
backup_name="vedanta-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
docker compose stop worker api
trap 'docker compose start api worker' EXIT
docker compose run --rm --no-deps -T --user root --entrypoint tar api -C /data -czf - . > "backups/$backup_name"
chmod 600 "backups/$backup_name"
tar -tzf "backups/$backup_name" >/dev/null
printf 'Backup created: backups/%s\n' "$backup_name"
