#!/usr/bin/env bash
# Invoked over SSH by GitHub Actions; production secrets remain on EC2.
set -euo pipefail
release_id=${1:?A Git commit SHA is required}
[[ "$release_id" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid release ID' >&2; exit 1; }
bundle_dir=$(cd -- "$(dirname -- "$0")" && pwd)
deployment=/opt/vedanta/deploy
cd "$deployment"
exec 9>/var/lock/vedanta-release.lock
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
test -f .env && test -f runtime.env
docker load -i "$bundle_dir/images.tar.gz"

rollback_dir="/opt/vedanta/release-history/$release_id-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$rollback_dir"
cp .env compose.yaml verify-live.py backup.sh "$rollback_dir/"
bash backup.sh

rollback() {
    status=$?
    if [[ $status -ne 0 ]]; then
        echo 'Release verification failed; restoring the previous configuration.' >&2
        cp "$rollback_dir/.env" "$rollback_dir/compose.yaml" "$rollback_dir/verify-live.py" "$rollback_dir/backup.sh" "$deployment/"
        docker compose up -d --no-build --wait --wait-timeout 120 || true
        echo "Database backup retained in $deployment/backups. Code rollback cannot reverse incompatible database changes." >&2
    fi
    exit "$status"
}
trap rollback EXIT
install -m 644 "$bundle_dir/compose.yaml" "$bundle_dir/verify-live.py" "$bundle_dir/backup.sh" "$deployment/"
if grep -q '^RELEASE_TAG=' .env; then
    sed -i "s/^RELEASE_TAG=.*/RELEASE_TAG=$release_id/" .env
else
    printf '\nRELEASE_TAG=%s\n' "$release_id" >> .env
fi
docker compose config --quiet
docker compose run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose stop worker
docker compose up -d --no-build --wait --wait-timeout 120
# Caddy may briefly resolve the previous API container address during replacement.
verified=false
for attempt in 1 2 3 4 5 6; do
    if python3 verify-live.py; then verified=true; break; fi
    sleep 5
done
$verified || exit 1
echo "Deployed commit $release_id"
