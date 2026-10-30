"""Install only explicitly supplied OpenAI settings from stdin; never log keys."""
import json
import os
import re
import sys
from pathlib import Path

payload = json.load(sys.stdin)
key = payload.get('OPENAI_API_KEY', '').strip()
model = payload.get('OPENAI_MODEL', '').strip()
if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
    raise SystemExit('OpenAI key is empty or has unsupported characters')
if model and not re.fullmatch(r'[A-Za-z0-9_./:-]+', model):
    raise SystemExit('Model setting has unsupported characters')
target = Path('/opt/vedanta/deploy/runtime.env')
lines = target.read_text().splitlines() if target.exists() else []
values = {'OPENAI_API_KEY': key}
if model:
    values['OPENAI_MODEL'] = model
lines = [line for line in lines if line.split('=', 1)[0].strip() not in values]
lines.extend(name + "='" + value + "'" for name, value in values.items())
temporary = target.with_suffix('.env.new')
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as handle:
    handle.write('\n'.join(lines) + '\n')
os.chmod(temporary, 0o600)
os.replace(temporary, target)
print('OpenAI runtime settings installed; key not displayed.')
