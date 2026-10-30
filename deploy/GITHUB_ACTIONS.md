# GitHub approval and local EC2 deployment

Repository: https://github.com/Arjun131001/vedanta-kuki

GitHub builds and tests the application on hosted Ubuntu runners. For main-branch releases, the production environment requires approval by Arjun131001, limits releases to main, and disables administrator bypass. After approval, GitHub publishes an approved-vedanta-COMMIT artifact retained for three days. No EC2 deployment happens inside GitHub Actions.

The final deployment runs from your computer using the existing SSH key and IP-restricted firewall. No persistent runner is installed on EC2. No SSH private key, website password, OpenAI key or DuckDNS token is stored in GitHub. The AWS Free plan explicitly denied OIDC-provider operations, and installation of a self-hosted deployment runner was declined.

## Deploy an approved release

Install the official GitHub CLI and sign in with gh auth login. Merge the reviewed PR, wait for the main-branch build, then approve the production environment job in GitHub Actions. Copy the successful workflow run ID and run from the project folder:

```powershell
.\deploy\deploy-approved.ps1 -RunId YOUR_RUN_ID -PrivateKey "$env:USERPROFILE\Downloads\vedanta-sydney.pem"
```

The script checks the workflow identity, main branch, event and successful conclusion, and requires the approved artifact. It downloads the exact commit-tagged images and deployment files, verifies SSH host identity, and uploads to EC2. Your current public IP must be allowed by the existing SSH firewall rule. Do not open SSH to all addresses.

The server loads the prebuilt images, takes a consistent backup, preserves its runtime secrets, and updates containers. Authenticated HTTPS checks verify the result. Failures restore the previous configuration/images; incompatible database changes require a manual restore from the retained pre-release backup. Old images, bundles and backups need periodic retention management on the small EC2 disk.

Pull requests and the preparation branch only build/test. They cannot produce an approved main-branch release. GitHub authentication provides the approval gate; no plaintext deployment password appears in workflow inputs or logs. The website password remains on EC2.

The initial PR build passed its full current tests and image builds. The revised runnerless workflow must also pass CI before merging. Required reviewer availability depends on GitHub plan and repository visibility; review protections before making the repository private.
