"""Create a private demo login on the server without logging its password."""
from pathlib import Path
import os
import secrets
import subprocess

root = Path('/opt/vedanta/deploy')
env = root / '.env'
config = env.read_text()
if 'REPLACE_WITH_BCRYPT_HASH' in config:
    password = secrets.token_urlsafe(24)
    result = subprocess.run(
        ['docker', 'run', '--rm', 'caddy:2.10-alpine', 'caddy',
         'hash-password', '--plaintext', password],
        check=True, capture_output=True, text=True,
    )
    hashed = result.stdout.strip()
    if not hashed.startswith('$2'):
        raise RuntimeError('Password hash generation failed')
    credentials = Path('/etc/vedanta/demo-login.txt')
    fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write('URL: https://vedant-a.duckdns.org\nUsername: vedanta\nPassword: ' + password + '\n')
    env.write_text(config.replace('REPLACE_WITH_BCRYPT_HASH', hashed))
    os.chmod(env, 0o600)
    print('Private demo login created in /etc/vedanta/demo-login.txt')
