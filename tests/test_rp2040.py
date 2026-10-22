import base64, csv, io, json, os, struct, tempfile, threading, time, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from bridge.core import Studio, UserError
from bridge.rp2040 import (profile, validate_capture, sump_commands, capture,
    adc_capture, exports, adc_exports, measurements, read_exact, discover)

class BinaryPort:
 def __init__(self, data, chunk=3):self.data=bytearray(data);self.writes=[];self.chunk=chunk;self.closed=False
 def __enter__(self):return self
 def __exit__(self,*args):self.closed=True
 def reset_input_buffer(self):pass
 def read(self,n):
  n=min(n,self.chunk);out=bytes(self.data[:n]);del self.data[:n];return out
 def write(self,data):self.writes.append(data);return len(data)

class ProtocolTest(unittest.TestCase):
 def test_sump_binary_order_and_no_crlf_translation(self):
  original=bytes([0,10,13,255,3,8,128,17]);port=BinaryPort(b'1ALS'+original[::-1],chunk=1)
  p=validate_capture({'samples':8});p['port']='emulator'
  self.assertEqual(capture(p,opener=lambda path:port),original)
  self.assertEqual(port.writes,[b'\0'*5,b'\x02',b'\x80\x63\0\0\0',b'\x81\x01\0\x01\0',b'\x82\x38\0\0\0',b'\x01',b'\0'*5]);self.assertTrue(port.closed)
 def test_sump_trigger_frames(self):
  p=validate_capture({'trigger':'rising','trigger_channel':7});frames=sump_commands(p)
  self.assertEqual(struct.unpack('<I',frames[-4][1:])[0],3)
  self.assertEqual(struct.unpack('<I',frames[-3][1:])[0],2)
  self.assertEqual(struct.unpack('<I',frames[-2][1:])[0],0x0c700000)
 def test_wrong_handshake_never_starts_capture(self):
  port=BinaryPort(b'FAIL');p=validate_capture({});p['port']='emulator'
  with self.assertRaisesRegex(UserError,'握手'):capture(p,opener=lambda _:port)
  self.assertNotIn(b'\x01',port.writes)
 def test_timeout_and_cancel_reject_partial_capture(self):
  port=BinaryPort(b'ab')
  with self.assertRaisesRegex(UserError,'超时'):read_exact(port,4,time.monotonic()+.01,lambda:False)
  with self.assertRaisesRegex(UserError,'取消'):read_exact(port,4,time.monotonic()+5,lambda:True)
 def test_adc_handshake_header_samples_and_units(self):
  raw=struct.pack('<4H',0,1024,2048,4095)
  port=BinaryPort(struct.pack('<4sIII',b'ADCI',500000,32768,1)+struct.pack('<4sIII',b'ADC1',100000,4,0)+raw)
  p=validate_capture({'samples':4,'vref':3.3},analog=True);p['port']='emulator'
  result,stats=adc_capture(p,opener=lambda _:port)
  self.assertEqual(result,raw);self.assertAlmostEqual(stats['max_v'],4095/4096*3.3);self.assertEqual(stats['clipped'],2)
  self.assertEqual(port.writes[1],struct.pack('<4sBBHII',b'ADC1',1,0,0,4,100000))
  rows=list(csv.DictReader(io.StringIO(dict(adc_exports(raw,p))['adc0.csv'].decode())))
  self.assertEqual(rows[1]['time_s'],'0.000010000');self.assertEqual(rows[1]['voltage_v'],'0.825000000')
 def test_adc_error_bit_not_silently_masked(self):
  port=BinaryPort(struct.pack('<4sIII',b'ADCI',500000,32768,1)+struct.pack('<4sIII',b'ADC1',100000,4,0)+struct.pack('<4H',1,2,3,0x8000))
  p=validate_capture({'samples':4},True);p['port']='emulator'
  with self.assertRaisesRegex(UserError,'FIFO'):adc_capture(p,opener=lambda _:port)
 def test_adc_wrong_sample_count_rejected_before_allocation(self):
  port=BinaryPort(struct.pack('<4sIII',b'ADCI',500000,32768,1)+struct.pack('<4sIII',b'ADC1',100000,0xffffffff,0))
  p=validate_capture({'samples':4},True);p['port']='emulator'
  with self.assertRaisesRegex(UserError,'采集头'):adc_capture(p,opener=lambda _:port)
 def test_limits_and_unsupported_rates(self):
  for p,a in [({'samples':100004},False),({'samples':5},False),({'rate':1500000},False),({'channel':3},True),({'vref':'nan'},True),({'rate':1000000},True),({'samples':32769},True),({'timeout':2,'samples':32768,'rate':10000},True)]:
   with self.assertRaises(UserError):validate_capture(p,a)
 def test_exports_preserve_chronology_and_channel_names(self):
  data=bytes([0,1,3,0x80]);files=dict(exports(data,1000000))
  with zipfile.ZipFile(io.BytesIO(files['logic.sr'])) as z:
   self.assertEqual(z.read('logic-1-1'),data);self.assertEqual(z.read('version'),b'2')
   self.assertIn(b'probe8=D7_GP27',z.read('metadata'))
  self.assertIn(b'#1000\n1a',files['logic.vcd']);self.assertIn(b'#3000',files['logic.vcd'])
  rows=list(csv.DictReader(io.StringIO(files['logic.csv'].decode())))
  self.assertEqual(rows[-1]['D7_GP27'],'1');self.assertEqual(rows[-1]['time_s'],'0.000003000')
 @unittest.skipIf(os.name=='nt','POSIX pseudo-terminal integration test')
 def test_real_pyserial_fragmented_sump_transport(self):
  import pty, serial
  master,slave=pty.openpty();portname=os.ttyname(slave);data=bytes(range(256))*4;errors=[]
  def firmware():
   try:
    while True:
     b=os.read(master,1)
     if b==b'\x02':os.write(master,b'1ALS')
     elif b==b'\x01':
      raw=data[::-1]
      for i in range(0,len(raw),29):os.write(master,raw[i:i+29])
      break
     elif b[0]>=0x80:
      remaining=4
      while remaining:remaining-=len(os.read(master,remaining))
   except Exception as e:errors.append(e)
  t=threading.Thread(target=firmware,daemon=True);t.start()
  p=validate_capture({'samples':len(data)});p['port']=portname
  try:self.assertEqual(capture(p),data);t.join(1);self.assertFalse(errors)
  finally:os.close(master);os.close(slave)

class RPDeviceTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Studio(self.tmp.name)
  self.d=dict(id='rp:1',name='LA-RP2040',family='rp2040',profile='cmsis-dap',mode=4,bcd=0,serial='E660A112',port='/dev/ttyACM0')
  self.ports=[{'path':'/dev/ttyACM0','vid':0x2e8a,'pid':0xc,'serial':'E660A112'}]
  self.s.enumerate=lambda:([self.d],self.ports,[])
  self.which=patch('bridge.core.shutil.which',return_value='/usr/bin/openocd');self.which.start()
 def tearDown(self):self.which.stop();self.s.shutdown();self.tmp.cleanup()
 def prepare(self,op,params=None):return self.s.prepare({'op':op,'device_id':self.d['id'],'params':params or {}})
 def test_cmsisdap_command_and_serial_selection(self):
  p=self.prepare('mcu.start');cmd=self.s.command(p)
  self.assertIn('interface/cmsis-dap.cfg',cmd);self.assertIn('cmsis-dap backend usb_bulk',cmd);self.assertIn('adapter serial E660A112',cmd)
  self.assertNotIn('adapter driver ch347',cmd)
 def test_debugprobe_cannot_do_jtag_fpga_swo(self):
  for op,p in [('mcu.start',{'transport':'jtag'}),('fpga.detect',{}),('xvc.start',{}),('logic.capture',{}),('scope.capture',{})]:
   with self.assertRaises(UserError):self.prepare(op,p)
 def test_cmsisdap_serial_injection_rejected(self):
  self.d['serial']='hello;shutdown'
  with self.assertRaises(UserError):self.prepare('mcu.start')
 def test_ch347_and_rp2040_can_coexist(self):
  ch=dict(id='ch',family='ch347',mode=3)
  self.s.enumerate=lambda:([ch,self.d],self.ports,[])
  self.assertEqual(self.prepare('mcu.start')['device_id'],'rp:1')
 def test_wrong_uart_rejected(self):
  with self.assertRaisesRegex(UserError,'CDC'):self.prepare('uart.open',{'port':'/dev/ttyACM9'})
  self.assertEqual(self.prepare('uart.open',{'port':'/dev/ttyACM0'})['params']['port'],'/dev/ttyACM0')
 def test_unknown_rp_usb_pid_is_not_an_analyzer(self):
  self.assertEqual(profile(0xa,'Pico')[1],'unknown')
  self.assertEqual(profile(0xa,'LA-RP2040 ADC12 v1')[1],'adc12')
  self.assertEqual(profile(0xa,'LA-RP2040 SUMP8 v1')[1],'sump8')
 def test_acquisition_uses_device_port_not_user_port(self):
  self.d.update(mode=5,profile='sump8')
  p=self.prepare('logic.capture',{'port':'/some/other/device'})
  self.assertEqual(p['params']['port'],'/dev/ttyACM0')
 def test_scope_job_artifacts_come_from_transport(self):
  self.d.update(mode=7,profile='adc12');p=self.prepare('scope.capture',{'samples':4})
  raw=struct.pack('<4H',0,100,200,300)
  with patch('bridge.rp2040.adc_capture',return_value=(raw,measurements([0,100,200,300],3.3))):
   job=self.s.execute(p['id'],'');self.assertTrue(self.s.lock.acquire(timeout=2));self.s.lock.release()
  self.assertEqual(job['status'],'succeeded');self.assertEqual(base64.b64decode(job['result']['samples_b64']),raw)
  self.assertEqual(len(job['result']['downloads']),2)
  for f in job['result']['downloads']:self.assertTrue(Path(self.s.files[f['id']]['path']).exists())

if __name__=='__main__':unittest.main()

class HTTPADCIntegrationTest(unittest.TestCase):
 @unittest.skipIf(os.name=='nt','POSIX serial emulator')
 def test_http_plan_capture_and_csv_download(self):
  import http.client, pty
  from bridge.server import make_server
  master,slave=pty.openpty();path=os.ttyname(slave);failures=[]
  raw=struct.pack('<4H',0,1024,2048,4095)
  def firmware():
   try:
    for _ in range(2):
     request=bytearray()
     while len(request)<16:request.extend(os.read(master,16-len(request)))
     magic,op,ch,flags,n,rate=struct.unpack('<4sBBHII',request)
     if magic!=b'ADC1' or ch!=2:raise AssertionError('Wrong ADC request')
     reply=struct.pack('<4sIII',b'ADCI',500000,32768,1) if op==0 else struct.pack('<4sIII',b'ADC1',rate,n,0)+raw
     for i in range(0,len(reply),3):os.write(master,reply[i:i+3])
   except Exception as e:failures.append(e)
  thread=threading.Thread(target=firmware,daemon=True);thread.start()
  with tempfile.TemporaryDirectory() as root:
   server=make_server(0,root,'capture-test')
   device=dict(id='rp-test',name='ADC fixture',family='rp2040',profile='adc12',mode=7,port=path,bcd=0,serial='TEST')
   server.studio.enumerate=lambda:([device],[],[])
   http_thread=threading.Thread(target=server.serve_forever,daemon=True);http_thread.start()
   def request(url,body=None):
    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    conn.request('POST' if body is not None else 'GET','/api/'+url,body=json.dumps(body) if body is not None else None,headers={'Authorization':'Bearer capture-test','Content-Type':'application/json'})
    resp=conn.getresponse();status=resp.status;data=resp.read();conn.close()
    self.assertEqual(status,200,data[:300]);return data
   try:
    plan=json.loads(request('prepare',{'device_id':'rp-test','op':'scope.capture','params':{'channel':2,'samples':4,'rate':100000}}))
    job=json.loads(request('execute',{'plan_id':plan['id']}))
    self.assertTrue(server.studio.lock.acquire(timeout=3));server.studio.lock.release()
    job=json.loads(request('jobs/'+job['id']));self.assertEqual(job['status'],'succeeded',job.get('error'))
    self.assertEqual(base64.b64decode(job['result']['samples_b64']),raw)
    csv_file=job['result']['downloads'][0];download=request('download/'+csv_file['id'])
    self.assertIn(b'0.000010000,1024,0.825000000',download)
    thread.join(1);self.assertFalse(failures)
   finally:server.shutdown();server.studio.shutdown();server.server_close();os.close(master);os.close(slave)

class FirmwareArtifactTest(unittest.TestCase):
 def test_uf2_blocks_and_manifest_hashes(self):
  import hashlib
  root=Path(__file__).resolve().parent.parent/'dist/firmware'
  manifest=json.loads((root/'manifest.json').read_text())
  self.assertEqual(len(manifest['firmwares']),3)
  for f in manifest['firmwares']:
   raw=(root/f['filename']).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),f['sha256'])
   self.assertEqual(len(raw)%512,0);count=len(raw)//512
   for n in range(count):
    block=raw[n*512:(n+1)*512];h=struct.unpack('<8I',block[:32])
    self.assertEqual(h,(0x0a324655,0x9e5d5157,0x2000,0x10000000+n*256,256,n,count,0xe48bff56))
    self.assertEqual(struct.unpack('<I',block[508:])[0],0x0ab16f30)
