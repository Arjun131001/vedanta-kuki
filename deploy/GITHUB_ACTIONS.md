# GitHub Actions deployment

Repository: https://github.com/Arjun131001/vedanta-kuki

The workflow triggers on pushes to `main` or a manual run from `main`. Its `production` environment must require deployment approval. No website password, OpenAI key or DuckDNS token belongs in the repository or workflow inputs. Existing server secrets are preserved. SSH uses a private-key secret and optionally its password/passphrase.

## Configure the approval gate before enabling deployments

In repository Settings → Environments, create `production`, enable Required reviewers, and select Arjun131001. Restrict deployment branches to `main`. If this is the only reviewer, leave Prevent self-review unchecked so you can approve a run you triggered. Disable administrator bypass if you want every run to wait for approval. Required-reviewer availability depends on repository visibility and GitHub plan; do not assume that simply declaring `environment: production` creates an approval rule.

Add these **environment secrets**:

| Secret | Value |
| --- | --- |
| `EC2_SSH_PRIVATE_KEY` | Contents of the downloaded vedanta-sydney.pem file, entered securely |
| `EC2_SSH_KEY_PASSPHRASE` | Only if that SSH key is encrypted; otherwise leave unset |
| `EC2_KNOWN_HOSTS` | Contents of deploy/github-known-hosts; this is the verified server public host key |
| `AWS_DEPLOY_ROLE_ARN` | ARN of the restricted GitHub OIDC role described below |

The website password remains in `/opt/vedanta/deploy/.env`, and the OpenAI settings remain in `runtime.env`; GitHub does not need either. The workflow never prints them or builds them into images.

## AWS network access

The current EC2 firewall admits SSH only from the operator's IP. GitHub-hosted runners have different IPs. The workflow uses short-lived OIDC credentials to admit only the current runner's `/32` address, then removes that exact rule in an always-run cleanup step. It does not open SSH to the internet.

Create the GitHub OIDC provider in IAM with URL `https://token.actions.githubusercontent.com` and audience `sts.amazonaws.com` if it does not exist. Create a role using `github-oidc-trust.example.json` (restricted to this repository's `production` environment) and `github-oidc-policy.json` (restricted to this server's security group). Put its ARN in the environment secret above. Verify the current AWS plan permits these IAM operations; do not upgrade the plan automatically.

If a runner is forcibly killed or AWS cleanup fails, inspect inbound rules and remove the stale runner `/32` rule. The workflow fails if normal cleanup fails. The OIDC policy permits editing rules only in the named security group; it is not an AWS administrator role. Protect workflow changes and limit repository write access because approved deployment code can administer the EC2 host through SSH.

## What happens after approval

1. Build the Python image and run the backend suite in an isolated container without network access or production data. Run the frontend unit tests and production build.
2. Package both images and an explicit allowlist of deployment files. No project `.env`, private documents or runtime secrets are transferred.
3. Authenticate to AWS, temporarily admit the runner, verify the pinned SSH host key, and upload the bundle to EC2.
4. Load the images, take a consistent backup, and preserve the previous Compose configuration and image tag in a root-only release-history directory.
5. Change the release tag to the Git commit SHA, recreate containers, and check authenticated HTTPS health and dashboard assets.
6. On failure, restore the previous configuration/images. Incompatible database changes require restoring the pre-release backup manually. Do not deploy migrations that lack a compatible rollback plan.
7. Remove the runner's SSH rule and terminate its SSH agent.

The workflow serializes releases. Builds run on GitHub to reduce load on the small EC2 instance. Keep enough EC2 disk space for the upload, loaded images and backups; older images, uploaded bundles and backups are deliberately retained for recovery and need periodic retention management. A new SSH host key after instance replacement must be verified and updated in EC2_KNOWN_HOSTS.

## Current application baseline

The last deployment test run had 169 passing tests and one failure in `test_recovery_detects_single_line_and_split_line_duplicate_as_ambiguous`. This workflow intentionally blocks deployment if that failure remains. It does not skip the test or modify application evidence validation to force a green run.

## References

- GitHub deployment environment protections: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- GitHub OIDC with AWS: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
