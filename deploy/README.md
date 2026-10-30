# Vedanta AWS deployment

Start with [EC2 provisioning and deployment](EC2_SETUP.md). The CloudFormation template installs Docker on Ubuntu and the PowerShell publisher uploads only application source.

Target: `https://vedant-a.duckdns.org`, Sydney (`ap-southeast-2`). DuckDNS registration is confirmed; the address still needs to point to EC2. These files implement the existing React/FastAPI/SQLite application using Docker Compose. Docker restart policies replace the originally proposed individual systemd app services; the DNS updater uses systemd.

## Prerequisites

Confirm active AWS credits and the EC2 launch estimate before provisioning. Use one Ubuntu 24.04 x86 EC2 instance, an eligible small instance type with enough memory for the workload, and an encrypted 10–15 GiB gp3 root volume. One GiB RAM needs representative load testing; building the frontend on another machine avoids build memory pressure. Allow 80/443 publicly and SSH only from your current IP. Do not open 8000. Require IMDSv2. Avoid a load balancer, NAT gateway and Route 53 for this deployment.

The registered DuckDNS subdomain is `vedant-a`. DOMAIN and DUCKDNS_SUBDOMAIN below use that exact name. AWS credentials and DuckDNS tokens should not be pasted into chat.

Install Docker Engine and the Compose plugin using the official Ubuntu instructions: https://docs.docker.com/engine/install/ubuntu/. Enable Docker at boot (`sudo systemctl enable --now docker`). The following Docker commands assume your operator can access Docker; use sudo if needed. Docker access gives administrative control of the machine.

## Prepare a release

Copy application source to `/opt/vedanta`, excluding local `.env`, `.venv`, `backend/data`, `node_modules` and logs. Include current intended application changes, not merely the last Git commit if it is stale. Never copy private local data implicitly.

```bash
cd /opt/vedanta/deploy
cp .env.example .env
cp runtime.env.example runtime.env
chmod 600 .env runtime.env
docker run --rm -it caddy:2.10-alpine caddy hash-password
```

Enter a strong password interactively, then edit `.env` and replace the placeholder with its bcrypt hash, keeping the single quotes around it. Login username is `vedanta`. Set RELEASE_TAG to a unique release name, such as `20261029-1`. Optionally set the OpenAI key in `runtime.env` securely on the server; model calls have separate provider costs.

```bash
docker compose config --quiet
docker compose build api web
docker compose run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

This build compiles the frontend and does not include secrets in image layers. On a memory-constrained server, build both images on a compatible x86 Linux Docker machine instead, save/load them with `docker image save` and `docker image load`, and use the same RELEASE_TAG on both machines. Existing named volumes persist across rebuilds. The API is accessible only inside the Docker network. Only Caddy publishes host ports.

## Configure DNS updates

```bash
sudo install -d -m 700 /etc/vedanta
sudoedit /etc/vedanta/duckdns.env
```

Enter these values in that file (substitute the actual token; no quotes needed):

```dotenv
DUCKDNS_SUBDOMAIN=vedant-a
DUCKDNS_TOKEN=your-token
```

```bash
sudo chmod 600 /etc/vedanta/duckdns.env
sudo cp duckdns-update.service duckdns-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start duckdns-update.service
sudo systemctl enable --now duckdns-update.timer
```

The updater sets the A record to the outbound public IPv4. Do not configure a stale AAAA record. Check DNS points to this instance before starting Caddy; it needs reachable 80/443 for certificate issuance.

## Start and verify

```bash
docker compose up -d --no-build
docker compose ps
curl --silent --output /dev/null --write-out '%{http_code}\n' https://vedant-a.duckdns.org/api/health
curl --fail --user vedanta https://vedant-a.duckdns.org/api/health
```

The first HTTPS request should return 401. The second prompts for the password and should return healthy JSON. Visit the site, log in, upload a sample PDF and XLSX, wait for worker completion and inspect evidence. Test optional Q&A only if the key and billing are configured. Verify full functionality after reboot and DNS recovery after stop/start. Check memory, disk and AWS billing after representative use. The API has one process and the worker one container; do not scale either across machines with this SQLite design.

Authentication gates all app/API routes, including docs. The HTTP endpoint redirects to HTTPS. The proxy accepts up to 273 MB per request; backend limits remain ten files and 25 MiB per file. The password gate is shared demo access, not individual accounts or data isolation.

## Data migration and backups

An empty deployment starts with a new database. To migrate local data, stop the local API and worker, archive the full local DATA_DIR, transfer securely and restore using the procedure below before starting the cloud services. This preserves related uploads, SQLite state and saved evidence together.

```bash
bash backup.sh
```

This briefly stops API/worker, archives the named data volume, checks archive readability, then restarts services even if backup fails. Copy the backup securely off the EC2 server and protect it: the archive itself is not encrypted. Never use `docker compose down -v` on a deployment whose data you need.

Restore first into a separate test directory and check SQLite integrity using Python's sqlite3 module and `PRAGMA integrity_check`. For an actual restore, ensure a recent backup exists and stop services. The target volume must be empty; preserve the old volume before switching, rather than merging unrelated database files. To use a fresh volume, change app_data's top-level volume declaration to a new explicit `name`, then:

```bash
docker compose stop worker api
docker compose run --rm --no-deps -T --user root --entrypoint tar api -C /data -xzf - < backups/CHOSEN-BACKUP.tar.gz
docker compose run --rm --no-deps --user root --entrypoint chown api -R 10001:10001 /data
docker compose up -d --no-build
```

The archive must be one created by this procedure or a trusted archive of the local DATA_DIR. Verify uploads and evidence after restoring. A same-host backup is not sufficient protection against instance loss.

## Updates and rollback

Run backend and frontend tests before deployment. Record the old RELEASE_TAG and keep those images. Back up, set a new RELEASE_TAG, build api/web, validate Caddy, and run `docker compose up -d --no-build`. For rollback, restore the old RELEASE_TAG and run that command again. Restore the matching pre-release database backup too if a release changed database compatibility. Retain Caddy volumes so certificates survive application updates. Base-image tags receive updates; record image digests if exact build reproducibility is required.

Monitor `docker compose logs --tail 100`, disk usage, failed jobs, and credit expiry. Docker logs are capped at three 10 MB files per service. Health checks expose API failure, but Docker restart policies do not automatically restart a running unhealthy process; investigate health failures. Set a demo end date and billing alerts. Stopping EC2 leaves storage billable; terminate and remove unneeded volumes/snapshots when finished.
