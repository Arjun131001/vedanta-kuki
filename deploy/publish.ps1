param(
    [Parameter(Mandatory=$true)][ValidatePattern('^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')][string]$PublicIp,
    [Parameter(Mandatory=$true)][string]$PrivateKey
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$keyPath = (Resolve-Path -LiteralPath $PrivateKey).Path
$archive = Join-Path $projectRoot 'tmp/vedanta-source.tar.gz'
New-Item -ItemType Directory -Force (Split-Path $archive -Parent) | Out-Null
# Explicit source allowlist excludes local data, credentials and unrelated files.
& tar -czf $archive -C $projectRoot --exclude=node_modules --exclude=dist --exclude=__pycache__ --exclude=.pytest_cache --exclude=.env --exclude=runtime.env --exclude=duckdns.env --exclude=backups --exclude=data backend/app backend/requirements.txt frontend deploy .dockerignore
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
Write-Host 'SSH will request confirmation for an unknown host. Verify its fingerprint using EC2 before accepting.'
& ssh -i $keyPath "ubuntu@$PublicIp" 'test -f /opt/vedanta/bootstrap-complete'
if ($LASTEXITCODE -ne 0) { throw 'Server bootstrap is incomplete or SSH access failed.' }
& scp -i $keyPath $archive "ubuntu@${PublicIp}:/opt/vedanta/source.tar.gz"
if ($LASTEXITCODE -ne 0) { throw 'Source upload failed.' }
& ssh -i $keyPath "ubuntu@$PublicIp" 'cd /opt/vedanta && tar -xzf source.tar.gz && find deploy -type f -exec sed -i "s/\r$//" {} +'
if ($LASTEXITCODE -ne 0) { throw 'Server extraction failed.' }
Write-Host 'Source uploaded. Follow deploy/EC2_SETUP.md to configure secrets and start containers.'
