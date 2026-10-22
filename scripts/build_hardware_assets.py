"""Rebuild hardware previews with KiCad 9 + numpy; source engineering files stay unchanged."""
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
from pathlib import Path
from hardware_source import board_data
from vrml_to_glb import convert
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'dist/hardware'

def main():
 p=argparse.ArgumentParser();p.add_argument('--kicad-cli',default='kicad-cli');p.add_argument('--models-dir',type=Path,help='Official KiCad 9 packages3D folder');p.add_argument('--manifest-only',action='store_true');a=p.parse_args()
 env=os.environ.copy()
 if a.models_dir:
  for key in ['KICAD9_3DMODEL_DIR','KICAD8_3DMODEL_DIR','KICAD6_3DMODEL_DIR','KISYS3DMOD']:env[key]=str(a.models_dir.resolve())
 def run(*args):subprocess.run([a.kicad_cli,*map(str,args)],env=env,check=True)
 for key,name in [('ch347','CH347_SPI'),('rp2040','LA_rp2040')]:
  d=BASE/key;pcb=d/'source'/f'{name}.kicad_pcb';sch=d/'source'/f'{name}.kicad_sch'
  if not a.manifest_only:
   (d/'geometry.json').write_text(json.dumps(board_data(pcb),ensure_ascii=False,indent=2)+'\n')
   run('sch','export','svg','--exclude-drawing-sheet','-o',d/'schematic',sch)
   for face,layers in [('front','F.Cu,F.Silkscreen,Edge.Cuts'),('back','B.Cu,B.Silkscreen,Edge.Cuts')]:run('pcb','export','svg','--mode-single','--layers',layers,'--fit-page-to-board','--exclude-drawing-sheet','-o',d/f'pcb-{face}.svg',pcb)
   with tempfile.TemporaryDirectory() as tmp:
    wrl=Path(tmp)/'board.wrl';run('pcb','export','vrml','--units','m','--user-origin','0x0mm','--force','-o',wrl,pcb);convert(wrl,d/'board.glb')
   for image,args in [('board-top.png',[]),('board-render.png',['--rotate','325,0,25','--perspective'])]:run('pcb','render','--width','1600','--height','900','--quality','high','--zoom','1.1','--background','transparent',*args,'-o',d/image,pcb)
   with zipfile.ZipFile(d/('CH347_Debug.zip' if key=='ch347' else 'LA_RP2040.zip'),'w',zipfile.ZIP_DEFLATED) as z:
    for src in sorted((d/'source').iterdir()):z.write(src,arcname=src.name)
 manifest=json.loads((BASE/'manifest.json').read_text())
 manifest['glb_pipeline']='KiCad 9.0.9 embedded VRML → scripts/vrml_to_glb.py; retains source silkscreen, component geometry and library material colors'
 manifest['images']['product-hero.png']='Unused AI concept illustration, retained only as an optional generated asset. All UI board images use the exact CAD renders with original silkscreen.'
 for key in ['ch347','rp2040']:
  d=BASE/key;manifest['boards'][key]['assets']={str(p.relative_to(d)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob('*')) if p.is_file() and 'source' not in p.parts}
 (BASE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
