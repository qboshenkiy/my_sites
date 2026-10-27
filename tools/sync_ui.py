"""Ship shared UI foundations inside each module's existing deployment boundary."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
common=ROOT/'native-common'
icons=json.loads((common/'ui-icons.json').read_text())
js=(common/'ui.js').read_text()
js=re.sub(r'/\* UI_ICONS_START \*/.*?/\* UI_ICONS_END \*/',lambda _: '/* UI_ICONS_START */'+json.dumps(icons,ensure_ascii=False,separators=(',',':'))+'/* UI_ICONS_END */',js,flags=re.S)
(common/'ui.js').write_text(js)
for folder in ['assets','marathon/assets','sketch_game/assets','chrono_logos/public/assets','milk_duty/web','deploy-panel']:
 for name in ['ui.js','ui.css']:(ROOT/folder/name).write_bytes((common/name).read_bytes())
(ROOT/'chrono_logos/public/assets/ui-icons.json').write_bytes((common/'ui-icons.json').read_bytes())
print('Shared UI assets synchronized')
