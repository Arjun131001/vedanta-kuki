"""Read-only HTTPS checks; run as root on EC2 to use the private demo login."""
import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

credentials = dict(line.split(': ', 1) for line in Path('/etc/vedanta/demo-login.txt').read_text().splitlines())
base = credentials['URL']
authorization = 'Basic ' + base64.b64encode((credentials['Username'] + ':' + credentials['Password']).encode()).decode()

try:
    urllib.request.urlopen(base + '/api/health', timeout=20)
    raise AssertionError('Unauthenticated API request was allowed')
except urllib.error.HTTPError as error:
    assert error.code == 401, error.code
print('PASS: HTTPS API requires authentication')


def get(path):
    request = urllib.request.Request(base + path, headers={'Authorization': authorization})
    with urllib.request.urlopen(request, timeout=20) as response:
        assert response.status == 200
        return response.read()


assert json.loads(get('/api/health'))['status'] == 'ok'
print('PASS: authenticated API health')
html = get('/').decode()
asset = re.search(r'src="(/assets/[^\"]+\.js)"', html)
assert asset, 'Compiled frontend asset missing'
assert len(get(asset.group(1))) > 0
print('PASS: compiled dashboard and JavaScript asset')
assert isinstance(json.loads(get('/api/documents')), (dict, list))
print('PASS: document library API')
print('AI configured:', bool(json.loads(get('/api/facts/config'))['configured']))
