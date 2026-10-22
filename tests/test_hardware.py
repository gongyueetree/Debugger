import hashlib,json,struct,sys,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from hardware_source import board_data

class HardwareSourceTest(unittest.TestCase):
 def test_sources_and_all_download_assets_match_manifest(self):
  base=ROOT/'dist/hardware';manifest=json.loads((base/'manifest.json').read_text())
  for key,board in manifest['boards'].items():
   for path,sha in board['source_files'].items():self.assertEqual(hashlib.sha256((base/key/'source'/path).read_bytes()).hexdigest(),sha)
   for path,sha in board['assets'].items():self.assertEqual(hashlib.sha256((base/key/path).read_bytes()).hexdigest(),sha)
 def test_geometry_matches_source_with_two_physical_sides(self):
  for key,name in [('ch347','CH347_SPI'),('rp2040','LA_rp2040')]:
   base=ROOT/'dist/hardware'/key;g=board_data(base/'source'/f'{name}.kicad_pcb');self.assertEqual(g,json.loads((base/'geometry.json').read_text()));pads=next(c['pads'] for c in g['connectors'] if c['ref']=='J2');self.assertEqual(len(pads),12)
   for pad in pads:self.assertIn('F.Cu' if int(pad['number'])%2 else 'B.Cu',pad['layers'])
   for i in range(1,12,2):
    a=next(p for p in pads if p['number']==str(i));b=next(p for p in pads if p['number']==str(i+1));self.assertEqual((a['x'],a['y']),(b['x'],b['y']))
 def test_zip_has_original_engineering_files_only(self):
  for key,archive in [('ch347','CH347_Debug.zip'),('rp2040','LA_RP2040.zip')]:
   base=ROOT/'dist/hardware'/key
   with zipfile.ZipFile(base/archive) as z:
    self.assertEqual(len(z.namelist()),3)
    for name in z.namelist():self.assertEqual(z.read(name),(base/'source'/Path(name).name).read_bytes())
 def test_glb_contains_geometry_and_material_colors(self):
  for key in ['ch347','rp2040']:
   raw=(ROOT/'dist/hardware'/key/'board.glb').read_bytes();magic,version,size=struct.unpack_from('<4sII',raw);self.assertEqual((magic,version,size),(b'glTF',2,len(raw)));n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);self.assertGreater(len(doc['materials']),10);self.assertIn('original silkscreen',doc['nodes'][0]['name']);self.assertGreater(sum(a['count'] for a in doc['accessors'] if a['type']=='SCALAR'),30000)
