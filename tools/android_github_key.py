"""Store the existing Android signing key as an encrypted GitHub Actions secret.

Run locally once, never on the web server. Requires PyNaCl and GitHub credentials
already configured in Git Credential Manager. No credentials are printed.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
from nacl.public import PublicKey, SealedBox

credential = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
    text=True, capture_output=True, check=True,
    env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never'))
values = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
token = values.get('password', '')
if not token:
    raise SystemExit('GitHub authentication is required')
root = 'https://api.github.com/repos/qboshenkiy/my_sites/actions/secrets/'
def request(path, data=None):
    req = urllib.request.Request(root + path,
        data=json.dumps(data).encode() if data else None, method='PUT' if data else 'GET',
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json', 'User-Agent': 'my-sites-android-setup'})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        raise SystemExit(f'GitHub rejected signing-key setup (HTTP {error.code}); configure ANDROID_KEYSTORE_B64 in repository Actions secrets') from None

key = request('public-key')
keystore = Path.home() / '.android/debug.keystore'
if not keystore.is_file():
    raise SystemExit('Existing signing key not found. Do not generate a replacement key.')
encrypted = SealedBox(PublicKey(base64.b64decode(key['key']))).encrypt(base64.b64encode(keystore.read_bytes()))
request('ANDROID_KEYSTORE_B64', {'key_id': key['key_id'], 'encrypted_value': base64.b64encode(encrypted).decode()})
print('Permanent signing key configured as an encrypted repository secret. No key was added to Git.')
