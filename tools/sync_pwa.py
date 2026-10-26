"""Synchronize tested PWA sources and the self-contained GitDeck resource bundle."""
from pathlib import Path
import json,base64,re
ROOT=Path(__file__).resolve().parents[1]
for target in ['assets','marathon/assets','sketch_game/assets','chrono_logos/public/assets']:
 for source,dest in [('pwa-assist.js','pwa.js'),('pwa-endpoints.php','pwa-endpoints.php'),('service-worker.js','service-worker.js')]:
  (ROOT/target/dest).write_bytes((ROOT/'native-common'/source).read_bytes())
for target in ['chrono_logos/public/pwa.js','deploy-panel/pwa.js']:(ROOT/target).write_bytes((ROOT/'native-common/pwa-assist.js').read_bytes())
panel=ROOT/'deploy-panel';bundle={}
(panel/'service-worker.js').write_bytes((ROOT/'native-common/service-worker.js').read_bytes())
for filename in ['pwa.js','manifest.webmanifest','service-worker.js','icon.svg','icon-192.png','icon-512.png']:
 file=panel/filename;binary=filename.endswith('.png')
 bundle[filename]={'base64':binary,'body':base64.b64encode(file.read_bytes()).decode() if binary else file.read_text(encoding='utf-8')}
block='<script id="pwa-resources" type="application/json">'+json.dumps(bundle,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')+'</script>'
p=panel/'index.html';html=p.read_text(encoding='utf-8')
html=re.sub(r'<script id="pwa-resources" type="application/json">.*?</script>','',html,flags=re.S)
html=html.replace('<script src="/pwa.js?v=2"','<script src="/pwa.js?v=3"')
html=html.replace('</body>',block+'</body>');p.write_text(html,encoding='utf-8')
print('PWA assets synchronized')
