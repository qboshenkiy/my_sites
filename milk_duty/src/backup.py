"""Consistent SQLite backup without stopping the bot; keep destination outside the public web root."""
import argparse
import os
from pathlib import Path
import sqlite3
parser=argparse.ArgumentParser()
parser.add_argument('destination')
parser.add_argument('--source',default=str(Path(os.getenv('DATA_DIR','data'))/'duty.sqlite'))
args=parser.parse_args()
os.umask(0o077)
source=Path(args.source).resolve();destination=Path(args.destination).resolve()
if source==destination or not source.is_file():raise SystemExit('Укажите существующую базу и другой путь для резервной копии.')
with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as src, sqlite3.connect(destination) as dst:src.backup(dst)
print('Резервная копия создана.')
