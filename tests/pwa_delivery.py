import tempfile,subprocess,shutil,socket,time,urllib.request,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
for base in ['', 'marathon','sketch_game','chrono_logos/public']:
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);source=ROOT/base
  # Exactly the old Docker contract: index.php and assets; no new root files.
  shutil.copy2(source/'index.php',root/'index.php');(root/'assets').mkdir()
  for name in ['pwa-endpoints.php','manifest.webmanifest','service-worker.js','pwa.js','pwa-icon-192.png','pwa-icon-512.png']:
   shutil.copy2(source/'assets'/name,root/'assets'/name)
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  server=subprocess.Popen([PHP,'-S',f'127.0.0.1:{port}','-t',str(root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   url=f'http://127.0.0.1:{port}'
   for _ in range(40):
    try:r=urllib.request.urlopen(url+'/index.php?pwa=manifest',timeout=1);break
    except OSError:time.sleep(.1)
   assert r.status==200 and 'application/manifest+json' in r.headers['Content-Type']
   manifest=json.load(r);assert manifest['scope']=='/'
   for icon in manifest['icons']:
    assert urllib.request.urlopen(url+icon['src']).status==200
   worker=urllib.request.urlopen(url+'/index.php?pwa=worker')
   assert worker.status==200 and 'javascript' in worker.headers['Content-Type'] and worker.headers['Service-Worker-Allowed']=='/'
   assert b"addEventListener('fetch'" in worker.read()
   print('PASS deployment layout and PWA resources:',base or 'pulse')
   if not base and os.environ.get('PWA_BROWSER_TEST')=='1':
    (root/'pwa-test.html').write_text('<!doctype html><meta charset="utf-8"><link rel="manifest" href="/index.php?pwa=manifest"><h1>Installability check</h1><script src="/assets/pwa.js" defer></script>',encoding='utf-8')
    subprocess.run(['node',str(ROOT/'tests/pwa_installability.cjs')],env=dict(os.environ,PWA_TEST_URL=url),check=True)

  finally:server.terminate();server.wait(timeout=5)
