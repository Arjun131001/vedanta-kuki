param(
    [Parameter(Mandatory=$true)][long]$RunId,
    [Parameter(Mandatory=$true)][string]$PrivateKey,
    [ValidatePattern('^[A-Za-z0-9.-]+$')][string]$HostName = 'vedant-a.duckdns.org'
)
$ErrorActionPreference = 'Stop'
$repository = 'Arjun131001/vedanta-kuki'
$keyPath = (Resolve-Path -LiteralPath $PrivateKey).Path
Get-Command gh -ErrorAction Stop | Out-Null
$runJson = & gh api "repos/$repository/actions/runs/$RunId"
if ($LASTEXITCODE -ne 0) { throw 'Could not read the GitHub run. Run gh auth login first.' }
$run = $runJson | ConvertFrom-Json
if ($run.status -ne 'completed' -or $run.conclusion -ne 'success' -or $run.head_branch -ne 'main' -or $run.event -notin @('push','workflow_dispatch')) {
    throw 'Choose a successful main-branch push or manual run whose release approval has completed.'
}
if ($run.path -ne '.github/workflows/deploy-ec2.yml') { throw 'Unexpected workflow.' }
$sha = $run.head_sha
if ($sha -notmatch '^[a-f0-9]{40}$') { throw 'Invalid commit SHA.' }
$projectRoot = Split-Path $PSScriptRoot -Parent
$downloadPath = Join-Path $projectRoot "tmp/approved-release-$RunId-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $downloadPath | Out-Null
# This artifact exists only after the production environment approval job runs.
& gh run download $RunId --repo $repository --name "approved-vedanta-$sha" --dir $downloadPath
if ($LASTEXITCODE -ne 0) { throw 'The approved artifact is missing, expired, or approval is incomplete.' }
$archive = Join-Path $downloadPath 'release.tar.gz'
if (-not (Test-Path -LiteralPath $archive)) { throw 'Approved release archive is missing.' }
$sshOptions = @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=20','-i',$keyPath)
& scp @sshOptions $archive "ubuntu@${HostName}:/home/ubuntu/vedanta-$sha.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed. Verify your current IP is allowed by the EC2 SSH rule and the server host key is trusted.' }
& ssh @sshOptions "ubuntu@$HostName" "mkdir -p /home/ubuntu/vedanta-release-$sha && tar -xzf /home/ubuntu/vedanta-$sha.tar.gz -C /home/ubuntu/vedanta-release-$sha && sudo bash /home/ubuntu/vedanta-release-$sha/apply-release.sh $sha"
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed; inspect rollback output and the retained backup.' }
Write-Output "Deployed approved commit $sha to https://$HostName"
