# AWS deployment plan for Verdant

Prepared: 29 October 2026. Scope: deployment planning only; no AWS resources or domain names have been created.

## Recommendation

Host the existing application on one Linux EC2 instance, using a free DuckDNS subdomain such as `kuki-verdant-demo.duckdns.org` (example only; availability must be checked). Use Caddy to serve the compiled React frontend, proxy the Python API, and obtain and renew HTTPS certificates. Run the API and persistent worker as separate systemd services on the same machine.

This is suitable for a small, password-protected assessment demo. The free address is a subdomain provided by DuckDNS, not ownership of a registered `.com` domain. AWS hosting is free only while applicable credits or allowances cover usage.

## Architecture

```text
Browser -> https://<chosen-name>.duckdns.org
        -> EC2 security group: HTTP 80 / HTTPS 443
        -> Caddy: HTTPS and shared demo password
           -> /api/* -> FastAPI at 127.0.0.1:8000 (preserve /api prefix)
           -> all other paths -> frontend/dist, with SPA fallback

FastAPI + Python worker -> same DATA_DIR on encrypted EBS
                        -> SQLite database, uploads, extracted evidence and saved results
Python worker -> OpenAI API when the user explicitly requests model features
EC2 -> DuckDNS HTTPS updater, scheduled every five minutes and at boot
```

The current API and worker use local SQLite and filesystem paths. Keep both on this single host. Static-only hosting does not run the backend or worker. A Lambda or multi-host deployment would require redesigning persistence and job processing.

## 1. Confirm AWS eligibility and budget

Before launching, inspect AWS Billing: account plan, credit balance, credit expiry, allowed EC2 instance types and regional service access. This plan cannot establish those account-specific details from the repository.

AWS changed Free Tier on 15 July 2025. New accounts can receive $100 sign-up credit and earn up to another $100; the Free plan ends after six months or credit exhaustion, whichever comes first. Older accounts used 12-month EC2 allowances. As of this plan's date, the original 12-month EC2 allowance for an account created before that change would already have elapsed. Do not assume that an existing account is still eligible merely because it was opened as a free tier account.

Use one region; prefer Mumbai if available and its launch estimate fits the credit budget. Select an eligible x86 micro instance for light demo use; a 2 GiB eligible instance is preferable if available within the budget. A 1 GiB micro instance is a starting point to validate, not a capacity guarantee. Build the frontend locally to reduce memory pressure; load-test representative PDF/XLSX files before choosing a larger machine. Check burstable CPU credit billing settings and avoid unexpected surplus charges.

Start with a single encrypted 10-15 GiB gp3 volume, subject to the account's allowances and actual data size. Do not provision a load balancer, NAT gateway, RDS, Route 53 hosted zone, or Kubernetes for this demo.

Create billing alerts at $1, $5 and $10, and credit-expiry reminders. Alerts are notifications, not spending caps. Check the launch cost estimate and billing after the first day.

## 2. Reserve the free address

1. Sign in to DuckDNS and register an available subdomain.
2. Launch EC2 with an automatically assigned public IPv4 address and update the DuckDNS A record to it.
3. Configure a boot job and five-minute systemd timer to update the address through DuckDNS's HTTPS API. Keep the token in a restricted file and out of source control and logs.
4. Confirm public DNS resolves correctly. Publish an AAAA record only if IPv6 is configured and reachable.
5. Allow Caddy to issue the certificate after DNS and ports 80/443 are working.

An automatically assigned EC2 public IPv4 can change after stop/start; the updater handles this, with a short DNS recovery interval. Public IPv4 is generally billed even without an Elastic IP. There is no need to allocate an Elastic IP for this design.

## 3. Prepare the application for the server

Implementation artifacts to add in a later deployment step:

- `deploy/Caddyfile`: hostname, HTTPS, hashed shared-password authentication on every app/API route, API proxy, static serving, SPA fallback and request limits.
- `deploy/verdant-api.service`: unprivileged service, backend working directory, environment file, restart policy, one Uvicorn process bound to loopback.
- `deploy/verdant-worker.service`: same user/environment/DATA_DIR; independent restart policy; `python -m app.worker`.
- `deploy/duckdns-update.service` and timer: address maintenance without logging tokens.
- `deploy/backup` procedure: consistent SQLite and file backup plus restore instructions.
- A repeatable release script and documented rollback procedure.

Use Python 3.11+ and the pinned `backend/requirements.txt`. Build the frontend with Node 20+ and `pnpm install --frozen-lockfile`, then `pnpm run build`. Copy the build output; do not run the Vite development server in production.

Suggested server layout:

```text
/opt/verdant/releases/<release-id>/   source, Python environment, frontend/dist
/opt/verdant/current                 link to active release
/var/lib/verdant/                    persistent DATA_DIR
/etc/verdant/runtime.env             restricted service environment
```

Set these variables through the systemd environment file:

```dotenv
DATA_DIR=/var/lib/verdant
MAX_UPLOAD_MB=25
FRONTEND_ORIGIN=https://<chosen-name>.duckdns.org
OPENAI_MODEL=<chosen-supported-model>
# OPENAI_API_KEY is optional; install securely on the server if model features are needed.
```

Leave frontend `VITE_API_URL` unset so requests use the same origin. The existing root `.env` loader reads only OpenAI settings; it does not load DATA_DIR or FRONTEND_ORIGIN, so services must explicitly receive these environment variables.

Preserve the API's 25 MiB per-file and ten-file batch limits. Permit approximately 260 MiB at the proxy for multipart overhead, validate actual batch sizes, and add disk-space checks. Authentication must cover `/api`, upload/retry actions, fact extraction and Q&A. Keep API documentation private too. Shared-password access suits this single-user demo; individual accounts and per-user data isolation require further application work.

## 4. Provision and release

1. Use an IAM identity with MFA and minimal deployment permissions. Do not deploy with root-account access keys.
2. Launch the selected Linux EC2 instance with encrypted EBS and IMDSv2 required. Permit inbound 80/443; restrict SSH 22 to the operator's current IP. Keep port 8000 private. Permit outbound HTTPS for packages, DNS updates, certificates and optional OpenAI calls.
3. Install Python, Caddy and required OS packages. Create an unprivileged app user and the persistent directories.
4. Run the backend tests and frontend build locally; upload a versioned release excluding `.env`, `.venv`, `node_modules`, local logs and private data.
5. Create the server virtual environment, install pinned dependencies, install the restricted runtime environment, and start API and worker services.
6. Install password protection, point DuckDNS at the server, validate the Caddy configuration and start HTTPS serving. Persist Caddy certificate state across releases.
7. If existing documents/results are required, stop the local API and worker before copying the entire DATA_DIR, or use a consistent backup procedure. Do not copy an active SQLite database file alone and omit its WAL. Transfer over SSH and verify file permissions and health after restoration.
8. Reboot once and verify automatic recovery of Caddy, API, worker and DNS updater.

## 5. Go-live acceptance checks

- HTTPS works with a trusted certificate; HTTP redirects to HTTPS.
- An unauthenticated request cannot view documents, upload files, inspect API docs or trigger paid model operations.
- The dashboard and direct navigation load; `/api/health` works through authenticated HTTPS.
- A representative PDF and XLSX upload successfully and finish extraction through the worker; citations open the correct evidence.
- A duplicate upload reuses the stored document; oversized files are rejected clearly.
- Optional fact extraction and Q&A work with a small controlled request and remain unavailable without a configured key.
- Restarting the worker recovers queued jobs; restarting the instance retains uploads, conversations and results.
- After stop/start and an IP change, DuckDNS updates and the site becomes reachable again.
- A backup restores into a separate test directory successfully; disk and memory remain acceptable during representative processing.

Run `python -m pytest` from `backend` and `pnpm run build` from `frontend`; also run the existing frontend `.test.mjs` tests with Node's test runner. These are planned release checks, not checks performed as part of this planning task.

## 6. Operations, backup and rollback

For this small demo, stop both API and worker briefly during a scheduled backup, archive the entire DATA_DIR, then restart them. Keep encrypted copies off the instance (for example on the operator's computer), verify restoration, and define retention. Optional private S3 backup adds storage/request charges and IAM configuration; EBS snapshots also consume billable storage. An EBS volume on the same instance is persistence, not a backup.

Rotate and cap service logs; monitor disk space, failed jobs, service restarts and billing. Use a single API process and a single worker initially. Keep SQLite on local EBS, not a shared network filesystem. Keep secrets outside releases and never put an OpenAI key in frontend build variables.

Deploy to a new release directory, stop services for a short maintenance window, back up data, switch the active link, restart, and run smoke checks. Retain the previous release. Roll back the code link if needed; if a later release changes database compatibility, restore its pre-release backup during maintenance as well.

## Cost boundaries and shutdown

| Item | Budget treatment |
| --- | --- |
| DuckDNS subdomain | Free service; chosen name is subject to availability |
| HTTPS certificate | Automatic public ACME certificate through Caddy; no certificate purchase |
| EC2 | Regional instance charges offset only by applicable allowances/credits |
| EBS | Volume storage and optional snapshots; validate account coverage |
| One public IPv4 | Published list rate $0.005/hour, about $3.65 for 730 hours, before credits/allowances |
| Internet transfer and logs | Usage-dependent; keep traffic and retained logs small |
| OpenAI API | Separate billing from AWS; budget independently if enabled |

A verified total requires the chosen region, instance type, remaining credits and expected traffic. This plan does not promise permanent zero-cost AWS hosting. The DNS address can remain free after AWS credits expire, while compute and storage can become billable.

For a temporary assessment, define an end date. Back up the data, terminate the instance, remove unneeded EBS volumes and snapshots, release any allocated Elastic IPs, and clear stale DuckDNS records. Stopping EC2 alone does not remove storage charges.

## Inputs needed when implementing

Confirm the AWS plan/remaining credits and allowed instance types in the console, choose an available DuckDNS name, decide whether to migrate existing local data, and decide whether to enable paid model features. Enter credentials only through the relevant provider or secure server configuration.

## Sources checked

- AWS Free Tier announcement: https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/
- AWS Free Tier FAQ: https://aws.amazon.com/free/free-tier-faqs/
- EC2 Free Tier eligibility: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html
- Public IPv4 pricing: https://aws.amazon.com/vpc/pricing/
- DuckDNS FAQ: https://www.duckdns.org/faqs.jsp
- DuckDNS update API: https://www.duckdns.org/spec.jsp
- Caddy automatic HTTPS: https://caddyserver.com/docs/automatic-https
