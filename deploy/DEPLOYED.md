# Current deployment

Verified 30 October 2026 (Asia/Calcutta).

- URL: https://vedant-a.duckdns.org (exact domain verified in signed-in DuckDNS account).
- AWS project: Try Catch Finally; account ending 4087.
- Region: Sydney, ap-southeast-2. The Free plan project blocks Mumbai; no plan upgrade was performed.
- Instance: i-06ea2841857be12b3, vedanta-demo, t3.micro, Ubuntu 24.04.
- Current public IPv4: 16.178.145.239. This can change after stop/start.
- API, worker and HTTPS gateway run under Docker Compose in /opt/vedanta/deploy.
- Persistent database and files: Docker volume vedanta_app_data on encrypted EBS.
- DuckDNS update timer enabled; token stored only in restricted configuration files and excluded from Git/images.
- Login username: vedanta. Password is in the private local tmp/vedanta-login.txt file and /etc/vedanta/demo-login.txt on EC2. Do not commit or share these files.
- No local documents or existing local database were migrated. OPENAI_API_KEY and OPENAI_MODEL were subsequently copied from the project-root .env into the restricted server runtime.env at the user's request. API and worker use that runtime configuration; no paid model request was used for deployment verification.

## Verification

Both images built on EC2. Caddy configuration validation passed. API is healthy; API and worker restarted successfully after a consistent backup. Public HTTPS uses a trusted certificate. Unauthenticated API access returns 401. Authenticated health, dashboard, JavaScript asset and document-library API checks pass.

Backend suite in an isolated Linux container: 169 passed, one failed:
`test_recovery_detects_single_line_and_split_line_duplicate_as_ambiguous` in test_facts.py. This application evidence-recovery behavior needs review; the deployment does not establish that all application tests pass. Test data was isolated from the live database, with networking disabled.

Initial consistent backup: /opt/vedanta/deploy/backups/vedanta-20261029T191754Z.tar.gz, with an off-server copy at tmp/vedanta-initial-backup.tar.gz in this workspace. Treat backups as private. Current backups are manual; run `sudo bash backup.sh` from the deployment directory and copy new archives off EC2 after important changes.

The instance was launched through the console, not the CloudFormation template. The launch form had Delete on termination enabled for the root volume: back up before terminating the instance. Restart policies and DNS timer are configured; a full OS reboot has not been tested.
