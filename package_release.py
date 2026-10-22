"""Create a reproducible, credential-free source ZIP; never includes dependencies."""
import argparse, hashlib, zipfile
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args();out=Path(args.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
files=[root/x for x in ['README.md','requirements.txt','start.sh','start-windows.bat','package_release.py','.gitignore']]
for folder in ['bridge','tests','docs','dist','firmware']:
 files += [p for p in (root/folder).rglob('*') if p.is_file() and (p.suffix in ['.py','.md','.html','.css','.js','.json','.uf2','.gz','.c','.txt','.patch'] or p.name=='LICENSE') and '__pycache__' not in p.parts]
for folder in ['agent','lib']:
 files += [p for p in (root/'agent-runtime'/folder).rglob('*') if p.is_file()]
files += [root/'agent-runtime'/x for x in ['package.json','package-lock.json','tsconfig.json','ask.mjs','AGENTS.md']]
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(set(files)):
  info=zipfile.ZipInfo('CH347_Debug_Studio/'+p.relative_to(root).as_posix(),date_time=(2026,10,22,0,0,0));info.external_attr=(0o755 if p.name=='start.sh' else 0o644)<<16;info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,p.read_bytes())
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 assert not any('node_modules' in n or '/.env' in n or '/.git/' in n for n in z.namelist())
print(f'{out}: {out.stat().st_size} bytes; SHA256 {hashlib.sha256(out.read_bytes()).hexdigest()}')
