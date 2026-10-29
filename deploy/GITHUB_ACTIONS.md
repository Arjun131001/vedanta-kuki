# Approval-gated GitHub deployment

Repository: https://github.com/Arjun131001/vedanta-kuki

Builds and tests run on GitHub-hosted Ubuntu. Deployment from main waits for Arjun131001 approval in the production environment, with administrator bypass disabled and main as the only permitted deployment branch. Self-review is allowed so the sole owner can approve their own run. Pull requests and the preparation branch never run on EC2.

AWS Free plan denied OIDC-provider operations through a service control policy. A dedicated deployment runner on the existing EC2 instance instead downloads the approved artifact over outbound HTTPS. No account upgrade, AWS access key, GitHub SSH secret or additional inbound port is needed. The website password, OpenAI key and DuckDNS token remain on EC2.

The runner uses a separate locked Linux user, vedanta-runner, under /opt/vedanta-runner. It is not in the Docker group and cannot directly read production secrets. Its one sudo entry allows the root-owned /usr/local/sbin/vedanta-ci-release helper, which validates the SHA and staging path before applying the approved release. Approved release code has administrator deployment capability. Protect repository write access and workflow changes; never route untrusted pull-request code or unrelated jobs to this production runner. Labels are routing, not an authorization boundary.

The release contains commit-tagged backend/frontend images and an explicit allowlist of deployment files. It excludes credentials and private documents. Before changing containers, it takes a consistent backup and records the previous configuration. It checks authenticated HTTPS afterward and restores previous configuration/images if verification fails. Incompatible database changes require restoring the pre-release backup manually.

Releases are serialized. Images, bundles and backups are retained for recovery, so monitor EC2 disk and manage retention. The runner uses memory on the existing instance; GitHub-hosted build minutes and artifact usage follow the repository plan. Artifacts expire after three days.

Approval uses GitHub authentication; no password is entered into workflow inputs or logs. The earlier backend suite had 169 passes and one evidence-recovery failure. The complete current suite gates deployment; tests are not skipped to force a release.

Required reviewers are available on GitHub Free for public repositories; check protections before changing visibility. Declaring environment: production in YAML alone does not create a required-reviewer rule.

Reference: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
