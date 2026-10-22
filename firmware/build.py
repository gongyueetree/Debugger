"""Build all three firmware profiles from pinned upstream sources or source bundle.
Prerequisites: Python 3.10+, Git, CMake, Ninja, Arm GNU Toolchain (incl. newlib).
Online: python firmware/build.py --work /path/to/empty/build-area
Offline: extract firmware-sources.tar.gz; use --work /path/to/firmware-sources
"""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPOS={
 'pico-sdk':('https://github.com/raspberrypi/pico-sdk.git','98a542c1a62fb549ffb5d66a3e5892b06276b670'),
 'debugprobe':('https://github.com/raspberrypi/debugprobe.git','262f9625d75a2bad8d76cc228ee5e21ca3a64d3a'),
 'logic-analyzer':('https://github.com/dgatf/logic_analyzer_rp2040.git','1b93e38126ca159a57b13c624b816e8e6eee15e9')}
def run(*args,**kw):subprocess.run(list(map(str,args)),check=True,**kw)
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'dist/firmware');a=p.parse_args()
 work=a.work.resolve();work.mkdir(parents=True,exist_ok=True);a.output.mkdir(parents=True,exist_ok=True)
 bundled=(work/'SOURCE_BUNDLE.json').exists()
 for name,(url,sha) in REPOS.items():
  dest=work/name
  if not bundled:
   if not dest.exists():run('git','clone',url,dest)
   if subprocess.check_output(['git','rev-parse','HEAD'],cwd=dest,text=True).strip()!=sha:
    if subprocess.check_output(['git','status','--porcelain'],cwd=dest,text=True).strip():raise SystemExit(f'{dest}: local changes; use a clean work directory')
    run('git','checkout','--detach',sha,cwd=dest)
   if name=='pico-sdk':run('git','submodule','update','--init','lib/tinyusb',cwd=dest)
   if name=='debugprobe':run('git','submodule','update','--init','--recursive',cwd=dest)
   if name in ('debugprobe','logic-analyzer'):
    patch=HERE/'patches'/('debugprobe.patch' if name=='debugprobe' else 'sump8.patch')
    check=subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=dest,capture_output=True)
    if check.returncode:run('git','apply',patch,cwd=dest)
 env=os.environ.copy();env['PICO_SDK_PATH']=str(work/'pico-sdk')
 sources=[('dap',work/'debugprobe','debugprobe_on_pico'),('sump8',work/'logic-analyzer/src','logic_analyzer'),('adc12',HERE/'adc12','la_rp2040_adc12')]
 records=[]
 from bin2uf2 import convert
 for name,source,target in sources:
  build=work/(name+'-build')
  run('cmake','-S',source,'-B',build,'-G','Ninja','-DPICO_BOARD=pico','-DPICO_NO_PICOTOOL=1','-DCMAKE_POLICY_VERSION_MINIMUM=3.5','-DPICO_DEFAULT_BOOT_STAGE2=boot2_generic_03h','-DPICO_FLASH_SIZE_BYTES=8388608',env=env)
  run('cmake','--build',build,'-j','4',env=env)
  data=convert((build/(target+'.bin')).read_bytes());out=a.output/f'la-rp2040-{name}.uf2';out.write_bytes(data)
  records.append({'profile':name,'filename':out.name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
 (a.output/'build-results.json').write_text(json.dumps(records,indent=2)+'\n')
 print('Built three UF2 profiles. Hardware verification is still required.')
if __name__=='__main__':main()
