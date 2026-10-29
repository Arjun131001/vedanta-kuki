"""Install the official deployment runner; registration data arrives through stdin."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tarfile
import urllib.request

settings = json.load(sys.stdin)
root = Path('/opt/vedanta-runner')
if (root / '.runner').exists():
    raise SystemExit('A runner is already configured; inspect it before replacing it.')
url = settings['download_url']
if not url.startswith('https://github.com/actions/runner/releases/download/'):
    raise SystemExit('Unexpected runner download source')
subprocess.run(['id', 'vedanta-runner'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0 or subprocess.run(
    ['useradd', '--system', '--create-home', '--home-dir', str(root), '--shell', '/usr/sbin/nologin', 'vedanta-runner'], check=True)
root.mkdir(exist_ok=True)
archive = root / 'runner.tar.gz'
digest = hashlib.sha256()
with urllib.request.urlopen(url, timeout=120) as response, archive.open('wb') as output:
    while chunk := response.read(1024 * 1024):
        digest.update(chunk)
        output.write(chunk)
if digest.hexdigest() != settings['sha256_checksum']:
    raise SystemExit('Official runner checksum mismatch')
with tarfile.open(archive) as source:
    source.extractall(root, filter='data')
subprocess.run(['chown', '-R', 'vedanta-runner:vedanta-runner', str(root)], check=True)
subprocess.run(['bash', str(root / 'bin/installdependencies.sh')], check=True)
subprocess.run([
    'runuser', '-u', 'vedanta-runner', '--', str(root / 'config.sh'),
    '--unattended', '--url', 'https://github.com/Arjun131001/vedanta-kuki',
    '--token', settings['token'], '--name', 'vedanta-production',
    '--labels', 'vedanta-production', '--work', '_work',
], cwd=root, check=True)
subprocess.run(['install', '-o', 'root', '-g', 'root', '-m', '755', '/home/ubuntu/vedanta-ci-release', '/usr/local/sbin/vedanta-ci-release'], check=True)
sudoers = Path('/etc/sudoers.d/vedanta-runner')
sudoers.write_text('vedanta-runner ALL=(root) NOPASSWD: /usr/local/sbin/vedanta-ci-release *\n')
os.chmod(sudoers, 0o440)
subprocess.run(['visudo', '-cf', str(sudoers)], check=True)
subprocess.run(['bash', str(root / 'svc.sh'), 'install', 'vedanta-runner'], cwd=root, check=True)
subprocess.run(['bash', str(root / 'svc.sh'), 'start'], cwd=root, check=True)
print('Dedicated deployment runner installed and started.')
