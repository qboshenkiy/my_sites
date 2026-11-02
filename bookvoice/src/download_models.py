"""One-time model installation. Only this step needs network access."""
import subprocess,sys
from pathlib import Path
import os
root=Path(os.getenv('MODEL_DIR','/models'));root.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,'-m','piper.download_voices','--download-dir',str(root),'ru_RU-denis-medium','ru_RU-dmitri-medium'],check=True)
print('Голоса Денис и Дмитрий готовы. Дальнейшая озвучка работает локально.')
