import ctypes, hashlib, http.client, json, socket, struct, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch
from bridge.core import Studio, UserError, integer, hexbytes
from bridge.bus import SPIConfig, clock_level
from bridge.server import make_server
from bridge.xvc import CH347JTAG, serve_client, MAX_BITS

class CoreTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Studio(self.tmp.name)
  self.d={'id':'1:2:55dd','name':'CH347T','pid':'55DD','mode':3,'bcd':0x544,'version':'5.44','bus':1,'address':2}
  self.s.enumerate=lambda:([self.d],[],[])
  self.which=patch('bridge.core.shutil.which',return_value='/test/tool');self.which.start()
 def tearDown(self):self.which.stop();self.s.shutdown();self.tmp.cleanup()
 def plan(self,op='fpga.detect',params=None):return self.s.prepare({'op':op,'device_id':self.d['id'],'params':params or {}})
 def test_mode_is_physical(self):
  self.d['mode']=1
  with self.assertRaisesRegex(UserError,'实际模式'):self.plan(params={'mode':3})
 def test_unknown_op_rejected(self):
  with self.assertRaises(UserError):self.plan('shell.exec',{'command':'echo bad'})
 def test_confirm_required(self):
  f=self.s.upload('test.bit',b'abc');p=self.plan('fpga.sram',{'file_id':f['id']})
  with self.assertRaisesRegex(UserError,'确认'):self.s.execute(p['id'],'bad')
  self.assertFalse(p['used'])
 def test_upload_sanitized_and_digest(self):
  f=self.s.upload('../../x.bit',b'abc');path=Path(self.s.files[f['id']]['path'])
  self.assertEqual(path.parent,Path(self.tmp.name));self.assertEqual(f['sha256'],hashlib.sha256(b'abc').hexdigest());self.assertEqual(f['name'],'x.bit')
 def test_extension_is_operation_specific(self):
  f=self.s.upload('x.svf',b'RUNTEST 1 TCK;')
  with self.assertRaises(UserError):self.plan('mcu.program',{'file_id':f['id']})
 def test_firmware_change_after_plan(self):
  f=self.s.upload('x.bit',b'a');p=self.plan('fpga.sram',{'file_id':f['id']});Path(self.s.files[f['id']]['path']).write_bytes(b'b')
  with self.assertRaisesRegex(UserError,'文件已变化'):self.s.execute(p['id'],p['confirmation'])
 def test_expired_plan(self):
  p=self.plan();p['created']-=301
  with self.assertRaisesRegex(UserError,'过期'):self.s.execute(p['id'],'')
 def test_unplug_after_plan(self):
  p=self.plan();self.s.enumerate=lambda:([],[],[])
  with self.assertRaisesRegex(UserError,'断开'):self.s.execute(p['id'],'')
 def test_mode_change_after_plan(self):
  p=self.plan();self.d={**self.d,'mode':1}
  with self.assertRaisesRegex(UserError,'模式'):self.s.execute(p['id'],'')
 def test_multiple_device_after_plan(self):
  p=self.plan();self.s.enumerate=lambda:([self.d,{**self.d,'id':'other'}],[],[])
  with self.assertRaisesRegex(UserError,'一个'):self.s.execute(p['id'],'')
 def test_no_double_execution(self):
  done=threading.Event();calls=[]
  def perform(p,j):calls.append(p['id']);done.set();return {'exit_code':0}
  self.s.perform=perform;p=self.plan();j=self.s.execute(p['id'],'');done.wait(1)
  j2=self.s.execute(p['id'],'');self.assertEqual(j['id'],j2['id']);self.assertEqual(calls,[p['id']]);self.s.lock.acquire(timeout=2);self.s.lock.release()
 def test_swd_reject_old_chip(self):
  self.d['bcd']=0x241
  with self.assertRaisesRegex(UserError,'SWD'):self.plan('mcu.start')
 def test_mcu_target_injection(self):
  with self.assertRaises(UserError):self.plan('mcu.start',{'target':'stm32f1; exec bad'})
 def test_flash_needs_exact_chip(self):
  self.d['mode']=1
  with self.assertRaisesRegex(UserError,'型号'):self.plan('flash.erase')
 def test_hid_limits_before_execution(self):
  self.d['mode']=2
  with self.assertRaisesRegex(UserError,'63'):self.plan('i2c.read',{'length':64})
 def test_nonzero_tool_is_failure(self):
  j={'logs':[],'cancel_requested':False}
  with self.assertRaisesRegex(UserError,'退出码 7'):self.s.run_command([sys.executable,'-c','import sys; print("real failure"); sys.exit(7)'],j)
  self.assertIn('real failure',j['logs'])
 def test_cancel_terminates_child(self):
  j={'logs':[],'cancel_requested':True}
  with self.assertRaisesRegex(UserError,'取消'):self.s.run_command([sys.executable,'-c','import time; time.sleep(20)'],j)
 def test_interrupted_job_not_replayed(self):
  Path(self.tmp.name,'history.json').write_text(json.dumps([{'id':'j','status':'running','logs':[]}]))
  s=Studio(self.tmp.name);self.assertEqual(s.jobs['j']['status'],'interrupted')
 def test_abi_is_packed(self):self.assertEqual(ctypes.sizeof(SPIConfig),20);self.assertEqual(SPIConfig.cs.offset,6)
 def test_numeric_validation(self):
  for x in [True,1.5,'1; halt','NaN']:
   with self.assertRaises(UserError):integer(x,0,10,'x')
  with self.assertRaises(UserError):hexbytes('0FF')
  self.assertEqual(clock_level(1000000),6)

class HTTPTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.server=make_server(0,self.tmp.name,'test-token',origins=['https://approved.test']);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
 def req(self,path,headers=None,method='GET',body=None):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2);c.request(method,path,body=body,headers=headers or {});r=c.getresponse();status=r.status;data=r.read();h=dict(r.getheaders());c.close();return status,data,h
 def test_auth_required(self):self.assertEqual(self.req('/api/status')[0],403)
 def test_dns_rebinding_blocked(self):self.assertEqual(self.req('/api/status',{'Host':'attacker.test','Authorization':'Bearer test-token'})[0],403)
 def test_bad_origin_blocked(self):self.assertEqual(self.req('/api/status',{'Origin':'https://attacker.test','Authorization':'Bearer test-token'})[0],403)
 def test_good_origin_and_token(self):
  code,body,h=self.req('/api/jobs',{'Origin':'https://approved.test','Authorization':'Bearer test-token'});self.assertEqual(code,200);self.assertEqual(json.loads(body),[]);self.assertEqual(h['Access-Control-Allow-Origin'],'https://approved.test')
 def test_preflight(self):self.assertEqual(self.req('/api/prepare',{'Origin':'https://approved.test'},'OPTIONS')[0],204)
 def test_static_path_escape(self):self.assertEqual(self.req('/../bridge/server.py')[0],404)
 def test_api_prepare_execute_history(self):
  studio=self.server.studio;device={'id':'test','name':'CH347T','mode':3,'bcd':0x544,'version':'5.44'}
  studio.enumerate=lambda:([device],[],[])
  studio.command=lambda plan,preview=False: [sys.executable,'-c','print("TEST ONLY: subprocess completed")']
  headers={'Authorization':'Bearer test-token','Content-Type':'application/json'}
  with patch('bridge.core.shutil.which',return_value=sys.executable):
   code,raw,_=self.req('/api/prepare',headers,'POST',json.dumps({'op':'fpga.detect','device_id':'test'}));self.assertEqual(code,200);plan=json.loads(raw)
   code,raw,_=self.req('/api/execute',headers,'POST',json.dumps({'plan_id':plan['id']}));self.assertEqual(code,200);job=json.loads(raw)
   studio.lock.acquire(timeout=3);studio.lock.release()
   code,raw,_=self.req('/api/jobs/'+job['id'],headers);finished=json.loads(raw)
   self.assertEqual(finished['status'],'succeeded');self.assertEqual(finished['result']['exit_code'],0);self.assertTrue(any('TEST ONLY' in l for l in finished['logs']))
   code,raw,_=self.req('/api/execute',headers,'POST',json.dumps({'plan_id':plan['id']}));self.assertEqual(json.loads(raw)['id'],job['id'])
 def test_upload_endpoint(self):
  code,body,_=self.req('/api/upload',{'Authorization':'Bearer test-token','Content-Type':'application/json'},'POST',json.dumps({'name':'test.bit','data':'YWJj'}));self.assertEqual(code,200);self.assertEqual(json.loads(body)['sha256'],hashlib.sha256(b'abc').hexdigest())

class XVCTest(unittest.TestCase):
 def test_arbitrary_tms_and_chunk_boundary(self):
  a=CH347JTAG.__new__(CH347JTAG);packets=[]
  def transfer(cmd,payload,n):
   packets.append(payload);self.assertEqual(cmd,0xd2);self.assertEqual(len(payload),2*n+1);self.assertLessEqual(len(payload)+3,512)
   for i in range(n):self.assertEqual(payload[i*2+1],payload[i*2]|1)
   self.assertEqual(payload[-1]&1,0)
   return bytes((payload[i*2]>>4)&1 for i in range(n))
  a.transfer=transfer;count=499;tms=bytes([0x96]*63);tdi=bytes([0xa5]*62+[0x05]);self.assertEqual(a.shift(count,tms,tdi),tdi);self.assertEqual(len(packets),3)
 def test_packet_header_validation(self):
  a=CH347JTAG.__new__(CH347JTAG)
  class Bad:
   def write(self,e,d,timeout):return len(d)
   def read(self,e,n,timeout):return bytes([0xd1,1,0,0])
  a.dev=Bad()
  with self.assertRaisesRegex(RuntimeError,'Invalid'):a.transfer(0xd2,b'abc',1)
 def test_xvc_protocol(self):
  a,b=socket.socketpair();a.settimeout(2);b.settimeout(2)
  class Fake:
   def clock(self,hz):return 1000
   def shift(self,n,tms,tdi):return tdi
  errors=[]
  def run():
   try:serve_client(b,Fake())
   except EOFError:pass
   except Exception as e:errors.append(e)
   finally:b.close()
  t=threading.Thread(target=run);t.start()
  a.sendall(b'getinfo:');self.assertEqual(a.recv(100),b'xvcServer_v1.0:2048\n')
  a.sendall(b'settck:'+struct.pack('<I',900));self.assertEqual(struct.unpack('<I',a.recv(4))[0],1000)
  a.sendall(b'shift:'+struct.pack('<I',9)+b'\xff\x01'+b'\x55\x01');self.assertEqual(a.recv(2),b'\x55\x01');a.close();t.join(2);self.assertEqual(errors,[])
 def test_oversized_shift_rejected(self):
  a=CH347JTAG.__new__(CH347JTAG)
  with self.assertRaises(ValueError):a.shift(MAX_BITS+1,b'',b'')

if __name__=='__main__':unittest.main()
