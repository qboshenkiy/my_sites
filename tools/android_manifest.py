"""Create update metadata from the APKs produced by the same signed build."""
import hashlib
import json
import sys
from pathlib import Path

folder, code, name = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
apps = {}
for module, package in [('marathon', 'net.sbena.vano.marathon'), ('chrono-logos', 'net.sbena.vano.chronologos')]:
    file = folder / (module + '.apk')
    apps[package] = dict(versionCode=code, versionName=name, size=file.stat().st_size,
        sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
        url=f'https://github.com/qboshenkiy/my_sites/releases/download/android-{code}/{file.name}')
(folder / 'updates.json').write_text(json.dumps(dict(apps=apps), indent=2), encoding='utf-8')
