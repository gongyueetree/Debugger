"""CH347 Studio: validated operations and hardware adapters. No shell execution."""
from __future__ import annotations
import base64, hashlib, importlib.util, json, os, platform, re, secrets, shutil, signal, subprocess, sys, threading, time, uuid
from pathlib import Path

MODES={0:'双 UART',1:'UART + SPI + I²C',2:'HID · UART + SPI + I²C',3:'UART + JTAG / SWD'}
PIDS={0x55da:0,0x55db:1,0x55dc:2,0x55dd:3}
TARGETS={'stm32f1':'stm32f1x.cfg','stm32f4':'stm32f4x.cfg','rp2040':'rp2040.cfg','nrf52':'nrf52.cfg','esp32':'esp32.cfg'}
OPS={
 'fpga.detect':('扫描 JTAG 链',[3],False), 'fpga.sram':('加载 FPGA SRAM',[3],True),
 'fpga.flash':('写入 FPGA 配置 Flash',[3],True), 'flash.detect':('识别 SPI Flash',[1],False),
 'flash.read':('备份 SPI Flash',[1],False), 'flash.write':('写入 SPI Flash',[1],True),
 'flash.verify':('校验 SPI Flash',[1],False), 'flash.erase':('擦除 SPI Flash',[1],True),
 'mcu.start':('启动 MCU 调试',[3,4],True), 'mcu.stop':('停止 MCU 调试',[3,4],False),
 'mcu.halt':('暂停 MCU',[3,4],True), 'mcu.resume':('继续 MCU',[3,4],True), 'mcu.step':('单步 MCU',[3,4],True),
 'mcu.reset':('复位并暂停 MCU',[3,4],True), 'mcu.registers':('读取 CPU 寄存器',[3,4],False),
 'mcu.memory':('读取 MCU 内存',[3,4],False), 'mcu.program':('烧录 MCU 固件',[3,4],True),
 'uart.open':('打开 UART',[0,1,2,3,4],False), 'uart.close':('关闭 UART',[0,1,2,3,4],False),
 'uart.send':('发送串口数据',[0,1,2,3,4],True), 'i2c.scan':('扫描 I²C 地址',[1,2],False),
 'i2c.read':('读取 I²C 寄存器',[1,2],False), 'i2c.write':('写入 I²C 寄存器',[1,2],True),
 'spi.transfer':('SPI 全双工传输',[1,2],True), 'gpio.read':('读取 GPIO',[3],False),
 'gpio.write':('设置 GPIO',[3],True), 'jtag.svf':('执行 SVF 测试向量',[3],True),
 'scope.capture':('采集 ADC 波形',[7],False), 'logic.capture':('采集逻辑波形',[5],False),
 'xvc.start':('启动 XVC 服务',[3],True),'xvc.stop':('停止 XVC 服务',[3],False)
}
class UserError(Exception):pass

def integer(v,lo,hi,label):
 try:
  if isinstance(v,bool) or isinstance(v,float):raise ValueError()
  n=int(str(v),0) if isinstance(v,str) and str(v).lower().startswith('0x') else int(v)
 except (ValueError,TypeError):raise UserError(label+' 必须为整数')
 if not lo<=n<=hi:raise UserError(f'{label} 范围应为 {lo}–{hi}')
 return n

def hexbytes(v,limit=4096):
 s=re.sub(r'\s','',str(v))
 if not re.fullmatch(r'(?:[0-9a-fA-F]{2})*',s):raise UserError('十六进制数据必须成对，例如 9F 00 00 00')
 b=bytes.fromhex(s)
 if len(b)>limit:raise UserError('数据长度超出限制')
 return b

def enumerate_devices():
 devices=[];warnings=[]
 try:
  import usb.core,usb.util
  for d in usb.core.find(find_all=True,idVendor=0x1a86):
   if d.idProduct not in PIDS:continue
   try: serial=usb.util.get_string(d,d.iSerialNumber) if d.iSerialNumber else ''
   except Exception: serial=''
   v=f'{d.bcdDevice>>8:X}.{d.bcdDevice&255:02X}'
   devices.append({'id':f'{d.bus}:{d.address}:{d.idProduct:04x}','name':'CH347T','vid':'1A86','pid':f'{d.idProduct:04X}','mode':PIDS[d.idProduct],'version':v,'bcd':d.bcdDevice,'serial':serial,'bus':d.bus,'address':d.address})
 except Exception as e:warnings.append('USB 枚举不可用：'+str(e))
 ports=[]
 try:
  from serial.tools import list_ports
  ports=[{'path':p.device,'description':p.description,'vid':p.vid,'pid':p.pid,'serial':p.serial_number,'location':p.location,'product':p.product or ''} for p in list_ports.comports()]
 except ImportError:warnings.append('未安装 pyserial')
 if not devices:
  try:
   import hid
   found={}
   for d in hid.enumerate(0x1a86,0x55dc):
    if d.get('interface_number')!=1:continue
    key=bytes(d['path']).hex() if isinstance(d['path'],bytes) else str(d['path'])
    found[key]={'id':'hid:'+key,'name':'CH347T','vid':'1A86','pid':'55DC','mode':2,'version':f"{d.get('release_number',0)>>8:X}.{d.get('release_number',0)&255:02X}",'bcd':d.get('release_number',0),'serial':key}
   devices.extend(found.values())
  except ImportError:pass
 if not devices:
  found={}
  for p in ports:
   if p['vid']==0x1a86 and p['pid'] in PIDS:
    key=p['serial'] or (p.get('location') or p['path']).split(':')[0];found[key]={'id':'serial:'+key,'name':'CH347T','vid':'1A86','pid':f"{p['pid']:04X}",'mode':PIDS[p['pid']],'version':'未知','bcd':0,'serial':p['serial'] or ''}
  devices.extend(found.values())
 for d in devices:d['family']='ch347';d['profile']='ch347'
 from .rp2040 import discover
 rp,w=discover(ports);devices.extend(rp);warnings.extend(w)
 return devices,ports,warnings

class Studio:
 def __init__(self,root):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);os.chmod(self.root,0o700)
  self.files={};self.plans={};self.jobs={};self.lock=threading.Lock();self.state_lock=threading.Lock();self.serials={};self.debug=None;self.xvc=None;self.debug_device=None;self.xvc_device=None
  self.child=None;self.seq=0;self.uart_log=[];self.enumerate=enumerate_devices
  self.load_history()
 def load_history(self):
  path=self.root/'history.json'
  if path.exists():
   try:
    for j in json.loads(path.read_text())[-200:]:
     if j['status'] in ['running','queued']:j['status']='interrupted';j['logs'].append('服务重启，任务不会自动重放。请核实目标状态。')
     self.jobs[j['id']]=j
   except (ValueError,KeyError):pass
 def persist(self):
  with self.state_lock:
   p=self.root/'history.tmp';p.write_text(json.dumps(list(self.jobs.values())[-200:],ensure_ascii=False));p.replace(self.root/'history.json')
 def status(self):
  devices,ports,warnings=self.enumerate()
  return {'version':'0.2.0','platform':platform.system(),'devices':devices,'ports':ports,'warnings':warnings,
   'tools':{n:bool(shutil.which(n)) for n in ['openFPGALoader','openocd','flashrom']},
   'providers':{n:importlib.util.find_spec(n) is not None for n in ['usb','serial','ch347','ch347api','hid']},
   'debug':self.debug is not None and self.debug.poll() is None,'xvc':self.xvc is not None and self.xvc.poll() is None,
   'uart_open':list(self.serials),'busy':self.lock.locked(),'targets':TARGETS,'ai':bool(os.getenv('CH347_EVE_URL'))}
 def upload(self,name,data):
  name=Path(name).name
  suffix=Path(name).suffix.lower()
  if suffix not in ['.bit','.bin','.jed','.fs','.mcs','.svf','.elf','.hex','.cfg']:raise UserError('不支持的文件类型')
  if not data or len(data)>64*1024*1024:raise UserError('文件必须介于 1 字节和 64 MiB')
  fid=uuid.uuid4().hex;p=self.root/(fid+suffix);p.write_bytes(data)
  f={'id':fid,'name':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'path':str(p)};self.files[fid]=f
  return {k:v for k,v in f.items() if k!='path'}
 def artifact(self,name,data):
  fid=uuid.uuid4().hex;p=self.root/(fid+Path(name).suffix);p.write_bytes(data)
  f={'id':fid,'name':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'path':str(p)}
  self.files[fid]=f
  return {k:v for k,v in f.items() if k!='path'}
 @staticmethod
 def family(d):return d.get('family','ch347')
 def unambiguous(self,d,ds):
  peers=[x for x in ds if self.family(x)==self.family(d)]
  if len(peers)!=1:raise UserError('请仅保留一个同系列调试器；CH347 与 RP2040 可以同时连接并选择')
 def device(self,device_id):
  ds,_,_=self.enumerate();d=next((d for d in ds if d['id']==device_id),None)
  if not d:raise UserError('设备已断开或已切换模式，请重新连接并生成计划')
  return d,ds
 def prepare(self,data):
  op=data.get('op');p=dict(data.get('params') or {})
  if op not in OPS:raise UserError('不支持的操作')
  d,ds=self.device(data.get('device_id'))
  title,modes,write=OPS[op]
  if d['mode'] not in modes:raise UserError(f'{title} 需要模式 {" / ".join(map(str,modes))}；当前实际模式为 {d["mode"]}。请切换硬件并重新上电。')
  self.unambiguous(d,ds)
  p['freq']=integer(p.get('freq',1000000),100000,30000000,'时钟 Hz')
  p['target']=str(p.get('target','stm32f1'))
  if op.startswith('mcu.') and p['target'] not in TARGETS:raise UserError('未列入验证目标配置列表')
  p['transport']=p.get('transport','swd')
  if p['transport'] not in ['jtag','swd']:raise UserError('无效调试接口')
  if op in ['mcu.start','mcu.program'] and p['transport']=='swd' and self.family(d)=='ch347' and d['bcd']<0x441:raise UserError('此 CH347T 版本不支持原生 SWD，请使用兼容芯片版本')
  if op in ['mcu.start','mcu.program'] and p['target']=='esp32' and p['transport']!='jtag':raise UserError('ESP32 配置需要 JTAG 接口')
  if self.family(d)=='rp2040' and op.startswith('mcu.') and p['transport']!='swd':raise UserError('debugprobe 固件仅支持 SWD，不支持 JTAG / SWO')
  if self.family(d)=='rp2040' and op.startswith('mcu.'):
   p['freq']=integer(p['freq'],100000,1000000,'本板首版 SWD 时钟 Hz')
   if d.get('serial') and not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',d['serial']):raise UserError('设备序列号格式异常')
  if op in ['logic.capture','scope.capture']:
   from .rp2040 import validate_capture
   p=validate_capture(p,analog=op=='scope.capture')
   required='adc12' if op=='scope.capture' else 'sump8'
   if d.get('profile')!=required:raise UserError('请先刷入本板的 '+required+' 固件')
   p['port']=d['port']
   if p['port'] in self.serials:raise UserError('采集端口已被串口终端占用')
  file=None
  if op in ['fpga.sram','fpga.flash','flash.write','flash.verify','mcu.program','jtag.svf']:
   file=self.files.get(p.get('file_id'))
   if not file or not Path(file['path']).exists():raise UserError('请先上传固件或向量文件')
   ext=Path(file['name']).suffix.lower()
   allowed={'fpga.sram':['.bit','.bin','.fs'],'fpga.flash':['.bit','.bin','.jed','.fs','.mcs'], 'flash.write':['.bin'],'flash.verify':['.bin'],'mcu.program':['.elf','.hex'],'jtag.svf':['.svf']}[op]
   if ext not in allowed:raise UserError(f'{title} 的文件类型必须为：'+', '.join(allowed))
   p['file_id']=file['id']
  if op.startswith('flash.'):
   p['chip']=str(p.get('chip','')).strip()
   if p['chip'] and not re.fullmatch(r'[A-Za-z0-9_ /().+-]{1,100}',p['chip']):raise UserError('Flash 芯片名称无效')
   if op in ['flash.write','flash.erase'] and not p['chip']:raise UserError('写入/擦除前请先识别并填写 flashrom 返回的精确 Flash 型号')
  if op.startswith('i2c.'):
   p['address']=integer(p.get('address','0x68'),8,119,'I²C 地址')
   p['register']=integer(p.get('register',0),0,65535,'寄存器地址');p['reg_width']=integer(p.get('reg_width',1),1,2,'寄存器地址字节数')
   if p['register'] >= 1<<(8*p['reg_width']):raise UserError('寄存器地址超过地址宽度')
   p['length']=integer(p.get('length',16),1,256,'读取长度')
   p['data']=hexbytes(p.get('data',''),256).hex()
   if op=='i2c.write' and not p['data']:raise UserError('写入数据不能为空')
  if d['mode']==2 and op.startswith('i2c.'):
   if op=='i2c.read' and p['length']>63:raise UserError('HID I²C 单次读取最多 63 字节')
   if op=='i2c.write' and len(bytes.fromhex(p['data']))+p['reg_width']>62:raise UserError('HID I²C 寄存器地址加写数据最多 62 字节')
  if op=='spi.transfer':
   p['freq']=integer(p['freq'],468750,30000000,'SPI 时钟 Hz')
   p['data']=hexbytes(p.get('data',''),4096).hex();p['spi_mode']=integer(p.get('spi_mode',0),0,3,'SPI 模式')
   if not p['data']:raise UserError('SPI 数据不能为空')
  if op.startswith('gpio.'):
   p['pin']=integer(p.get('pin',3),0,7,'GPIO');p['value']=integer(p.get('value',0),0,1,'电平')
   if p['pin'] not in [3,5,6]:raise UserError('此板仅开放 GPIO3(SCL)、GPIO5(TRST)、GPIO6(CTS)，请先确认复用冲突')
  if op.startswith('uart.'):
   p['port']=str(p.get('port',''));p['baud']=integer(p.get('baud',115200),1200,3000000,'波特率')
   p['channel']=integer(p.get('channel',1),0,1,'UART 通道')
   p['text']=str(p.get('text',''))
   if len(p['text'].encode())>4096:raise UserError('串口发送数据过长')
   if d['mode']!=2 and op=='uart.open':
    _,ports,_=self.enumerate()
    if self.family(d)=='rp2040':
     if p['port']!=d.get('port') or not any(x['path']==p['port'] and x['vid']==0x2e8a and x['pid']==0x000c for x in ports):raise UserError('请选择此 RP2040 的 CDC UART 端口')
    elif not any(x['path']==p['port'] and x['vid']==0x1a86 and x['pid'] in PIDS for x in ports):raise UserError('请选择枚举出的 CH347 串口')
   if d['mode']!=0 and p['channel']==0:raise UserError('UART0 仅可在模式 0 使用')
  if op=='mcu.memory':p['address']=integer(p.get('address','0x20000000'),0,0xffffffff,'地址');p['count']=integer(p.get('count',16),1,64,'读取字数')
  if op=='jtag.svf':
   p['irlen']=integer(p.get('irlen',8),1,32,'IR 长度');p['idcode']=integer(p.get('idcode','0x012ba043'),1,0xffffffff,'IDCODE')
  requirements=[]
  tool='openFPGALoader' if op.startswith('fpga.') else 'flashrom' if op.startswith('flash.') else 'openocd' if op.startswith('mcu.') or op=='jtag.svf' else None
  if op.startswith('xvc.') and (not importlib.util.find_spec('usb') or 'bus' not in d):requirements.append('XVC 需要 pyusb / libusb 与完整 USB 设备枚举')
  if tool and not shutil.which(tool):requirements.append(f'未安装 {tool}')
  if op.startswith(('i2c.','spi.','gpio.')) or (op.startswith('uart.') and d['mode']==2):
   from .bus import provider_info
   info=provider_info(d['mode'],op)
   if not info['available']:requirements.append(info['reason'])
  if requirements:raise UserError('；'.join(requirements))
  plan={'id':uuid.uuid4().hex,'device_id':d['id'],'device':d,'op':op,'title':title,'params':p,'write':write,'created':time.time(),'used':False,'file':({k:v for k,v in file.items() if k!='path'} if file else None),'confirmation':secrets.token_hex(4).upper(), 'warning':'执行前确认接线和目标电压。读取寄存器也可能有清除状态等副作用。'}
  plan['preview']=self.command(plan,preview=True) or f'{op} {json.dumps(p,ensure_ascii=False)}'
  self.plans[plan['id']]=plan
  return plan
 def command(self,plan,preview=False):
  op,p=plan['op'],plan['params'];f=self.files.get(p.get('file_id'),{}).get('path','')
  if preview and plan.get('file'):f=plan['file']['name']
  if op.startswith('fpga.'):
   cmd=['openFPGALoader','-c','ch347_jtag','--freq',str(p['freq'])]
   return cmd+(['--detect'] if op=='fpga.detect' else ['-m' if op=='fpga.sram' else '-f',f])
  if op.startswith('flash.'):
   cmd=['flashrom','-p','ch347_spi']
   if p.get('chip'):cmd+=['-c',p['chip']]
   return cmd+({'flash.detect':[],'flash.read':['-r','backup.bin' if preview else str(self.root/(plan['id']+'-backup.bin'))],'flash.write':['-w',f],'flash.verify':['-v',f],'flash.erase':['-E']}[op])
  if op.startswith('mcu.') and op in ['mcu.start','mcu.program']:
   speed=min(p['freq']//1000,1000) if p['transport']=='swd' else p['freq']//1000
   adapter=['-c','adapter driver ch347']
   if self.family(plan['device'])=='rp2040':
    adapter=['-f','interface/cmsis-dap.cfg','-c','cmsis-dap backend usb_bulk']
    if plan['device'].get('serial'):adapter+=['-c','adapter serial '+plan['device']['serial']]
   cmd=['openocd',*adapter,'-c',f'transport select {p["transport"]}','-c',f'adapter speed {speed}','-c','bindto 127.0.0.1','-c','gdb_port 3333','-c','telnet_port 4444','-c','tcl_port disabled','-f','target/'+TARGETS[p['target']]]
   if op=='mcu.program':cmd+=['-c',f'program {{{f}}} verify reset exit']
   return cmd
  if op=='jtag.svf':return ['openocd','-c','adapter driver ch347','-c','transport select jtag','-c',f'adapter speed {p["freq"]//1000}','-c','gdb_port disabled','-c','telnet_port disabled','-c','tcl_port disabled','-c',f'jtag newtap target tap -irlen {p["irlen"]} -expected-id {p["idcode"]:#x}','-c','init','-c',f'svf {{{f}}}','-c','shutdown']
  if op=='xvc.start':return [sys.executable,'-m','bridge.xvc','--bus',str(plan['device'].get('bus',0)),'--address',str(plan['device'].get('address',0)),'--freq',str(p['freq']),'--port','2542']
  return None
 def execute(self,plan_id,confirmation):
  plan=self.plans.get(plan_id)
  if not plan:raise UserError('计划不存在')
  with self.state_lock:
   if plan['used']:
    return next((j for j in self.jobs.values() if j['plan_id']==plan_id),{'status':'already-used'})
   if time.time()-plan['created']>300:raise UserError('计划已过期，请重新生成')
   if plan['write'] and confirmation!=plan['confirmation']:raise UserError('需要对本次操作进行明确确认')
  d,ds=self.device(plan['device_id'])
  self.unambiguous(d,ds)
  if any(d.get(k)!=plan['device'].get(k) for k in ['mode','family','profile','serial','port']):raise UserError('设备模式、固件或端口已变化，请重新生成计划')
  if plan.get('file'):
   f=self.files.get(plan['params']['file_id'])
   if not f or hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()!=plan['file']['sha256']:raise UserError('文件已变化，请重新上传并生成计划')
  if not self.lock.acquire(blocking=False):raise UserError('有硬件任务正在执行，请等待完成')
  with self.state_lock:
   if plan['used']:self.lock.release();raise UserError('计划已执行')
   plan['used']=True
  j={'id':uuid.uuid4().hex,'plan_id':plan_id,'title':plan['title'],'op':plan['op'],'mode':d['mode'],'device':d,'file':plan['file'],'params':plan['params'],'preview':plan['preview'],'status':'queued','created':time.time(),'logs':[],'result':None,'cancel_requested':False}
  self.jobs[j['id']]=j;self.persist();threading.Thread(target=self._run,args=(plan,j),daemon=True).start();return j
 def cancel(self,jid):
  j=self.jobs.get(jid)
  if not j:raise UserError('任务不存在')
  if j['status'] in ['queued','running']:j['cancel_requested']=True
  return j
 def log(self,j,s):
  j['logs'].append(str(s));j['logs']=j['logs'][-1500:]
 def _run(self,p,j):
  j['status']='running';self.log(j,'真实硬件任务 · '+p['title'])
  try:
   d,ds=self.device(p['device_id'])
   self.unambiguous(d,ds)
   if any(d.get(k)!=p['device'].get(k) for k in ['mode','family','profile','serial','port']):raise UserError('实际设备模式、固件或端口已变化')
   if self.debug and self.debug.poll() is None and self.debug_device==p['device_id'] and not p['op'].startswith(('mcu.','uart.')):raise UserError('OpenOCD 正占用设备，请先停止 MCU 调试')
   if self.xvc and self.xvc.poll() is None and self.xvc_device==p['device_id'] and not p['op'].startswith(('xvc.','uart.')):raise UserError('XVC 正占用设备，请先停止 XVC')
   if p['op']=='mcu.program' and self.debug and self.debug.poll() is None:raise UserError('请先停止当前调试会话再烧录固件')
   if j['cancel_requested']:raise UserError('任务取消')
   j['result']=self.perform(p,j);j['status']='succeeded'
  except Exception as e:j['status']='cancelled' if j['cancel_requested'] else 'failed';self.log(j,str(e));j['error']=str(e)
  finally:j['finished']=time.time();self.persist();self.lock.release()
 def run_command(self,cmd,j,timeout=300,daemon=None):
  self.log(j,'> '+' '.join(cmd));proc=subprocess.Popen(cmd,cwd=str(Path(__file__).resolve().parent.parent),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',bufsize=1,start_new_session=(os.name!='nt'))
  self.child=proc
  def reader():
   with proc.stdout as stream:
    for line in stream:self.log(j,line.rstrip())
  t=threading.Thread(target=reader,daemon=True);t.start();start=time.monotonic()
  while proc.poll() is None:
   if j['cancel_requested'] or time.monotonic()-start>timeout:
    self.stop_process(proc);raise UserError('任务取消，目标可能已被部分写入；请重新读取或校验' if j['cancel_requested'] else '任务超时，目标状态待核实')
   if daemon and any(('Listening on port 3333' in line if daemon=='debug' else 'XVC ready on 127.0.0.1:' in line) for line in j['logs']):
    self.child=None;return proc
   if daemon and time.monotonic()-start>15:
    self.stop_process(proc);raise UserError('服务未确认就绪，请查看初始化日志')
   time.sleep(.1)
  t.join(1)
  if proc.returncode!=0:raise UserError(f'外部工具退出码 {proc.returncode}；请查看日志')
  if daemon:raise UserError('服务提前退出，未建立调试会话')
  return {'exit_code':proc.returncode}
 @staticmethod
 def stop_process(p):
  if p and p.poll() is None:
   if os.name=='nt':p.terminate()
   else:os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(3)
   except subprocess.TimeoutExpired:
    if os.name=='nt':p.kill()
    else:os.killpg(p.pid,signal.SIGKILL)
 def perform(self,plan,j):
  op,p=plan['op'],plan['params']
  if op=='scope.capture':
   from .rp2040 import adc_capture, adc_exports
   raw,stats=adc_capture(p,lambda:j['cancel_requested'],lambda s:self.log(j,s))
   return {'source':'hardware','capture':{'rate':p['rate'],'count':len(raw)//2,'channels':1,'channel':p['channel'],'gpio_base':26+p['channel'],'vref':p['vref'],'bits':12},'measurements':stats,'samples_b64':base64.b64encode(raw).decode(),'downloads':[self.artifact(n,b) for n,b in adc_exports(raw,p)]}
  if op=='logic.capture':
   from .rp2040 import capture, exports
   samples=capture(p,lambda:j['cancel_requested'],lambda s:self.log(j,s))
   downloads=[self.artifact(name,data) for name,data in exports(samples,p['rate'])]
   return {'source':'hardware','capture':{'rate':p['rate'],'count':len(samples),'channels':8,'gpio_base':20,'trigger':p['trigger'],'pretrigger':0},'samples_b64':base64.b64encode(samples).decode(),'downloads':downloads}
  if op in ['mcu.stop','xvc.stop']:
   key='debug' if op=='mcu.stop' else 'xvc'
   if getattr(self,key) and getattr(self,key+'_device')!=plan['device_id']:raise UserError('此设备不拥有该调试会话')
   self.stop_process(getattr(self,key));setattr(self,key,None);return {'stopped':True}
  if op in ['mcu.start','xvc.start']:
   key='debug' if op=='mcu.start' else 'xvc'
   if getattr(self,key) and getattr(self,key).poll() is None:raise UserError('该服务已启动')
   proc=self.run_command(self.command(plan),j,daemon=key);setattr(self,key,proc);setattr(self,key+'_device',plan['device_id'])
   return {'service':key,'host':'127.0.0.1','port':3333 if key=='debug' else 2542,'note':'本机服务已确认就绪；目标状态及实际时钟请查看日志'}
  if op.startswith('mcu.') and op!='mcu.program':
   if not self.debug or self.debug.poll() is not None or self.debug_device!=plan['device_id']:raise UserError('请先启动此设备的 MCU 调试会话')
   commands={'mcu.halt':'halt','mcu.resume':'resume','mcu.step':'step','mcu.reset':'reset halt','mcu.registers':'reg','mcu.memory':f'mdw {p.get("address",0):#x} {p.get("count",16)}'}
   import socket
   with socket.create_connection(('127.0.0.1',4444),timeout=3) as s:
    s.settimeout(1);s.recv(4096);s.sendall((commands[op]+'\n').encode());parts=[]
    while True:
     try:
      b=s.recv(8192)
      if not b:break
      parts.append(b)
      if b.endswith(b'> '):break
     except TimeoutError:break
   output=b''.join(parts).decode(errors='replace');self.log(j,output)
   if not output.strip() or 'error' in output.lower() or 'invalid command' in output.lower():raise UserError(output or 'OpenOCD 未返回响应')
   return {'output':output}
  if op.startswith('uart.'):return self.uart(plan,j)
  if op.startswith(('i2c.','spi.','gpio.')):
   proc=subprocess.Popen([sys.executable,'-m','bridge.bus'],cwd=str(Path(__file__).resolve().parent.parent),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=(os.name!='nt'))
   self.child=proc
   payload=json.dumps({'device':plan['device'],'op':op,'params':p});start=time.monotonic();first=True
   while True:
    try:
     out,err=proc.communicate(input=payload if first else None,timeout=.2);break
    except subprocess.TimeoutExpired:
     first=False
     if j['cancel_requested'] or time.monotonic()-start>45:
      self.stop_process(proc);raise UserError('总线事务取消或超时，目标状态待核实')
   try:result=json.loads(out.strip().splitlines()[-1])
   except (ValueError,IndexError):raise UserError('总线后端未返回有效结果：'+err[-1000:])
   if proc.returncode or 'error' in result:raise UserError(result.get('error',err[-1000:]))
   self.log(j,json.dumps(result['result'],ensure_ascii=False));return result['result']
  result=self.run_command(self.command(plan),j)
  if op=='flash.read':
   f=self.root/(plan['id']+'-backup.bin')
   meta=self.upload('flash-backup.bin',f.read_bytes());result['download']=meta
  return result
 def uart(self,plan,j):
  p=plan['params'];key='hid:1' if plan['device']['mode']==2 else p['port'];op=plan['op']
  if op=='uart.open':
   if key in self.serials:raise UserError('该串口已打开')
   if plan['device']['mode']==2:
    from .bus import open_hid_uart
    s=open_hid_uart(p['baud'])
   else:
    import serial
    s=serial.Serial();s.port=key;s.baudrate=p['baud'];s.timeout=.2;s.dtr=False;s.rts=False;s.open()
   self.serials[key]=s
   def read():
    while self.serials.get(key) is s:
     try:
      b=s.read(4096)
      if b:
       self.seq+=1;self.uart_log.append({'seq':self.seq,'time':time.time(),'port':key,'direction':'rx','text':b.decode(errors='replace'),'hex':b.hex()});self.uart_log=self.uart_log[-3000:]
     except Exception as e:
      self.seq+=1;self.uart_log.append({'seq':self.seq,'time':time.time(),'port':key,'direction':'error','text':str(e)});self.serials.pop(key,None);break
   threading.Thread(target=read,daemon=True).start();return {'port':key,'baud':p['baud']}
  s=self.serials.get(key)
  if not s:raise UserError('请先打开串口')
  if op=='uart.close':self.serials.pop(key,None);s.close();return {'closed':key}
  data=p['text'].encode();n=s.write(data)
  if n!=len(data):raise UserError('串口未完整发送数据')
  self.seq+=1;self.uart_log.append({'seq':self.seq,'time':time.time(),'port':key,'direction':'tx','text':p['text']});return {'bytes':n}
 def shutdown(self):
  for j in self.jobs.values():
   if j['status'] in ['queued','running']:j['cancel_requested']=True
  self.stop_process(self.child)
  self.stop_process(self.debug);self.stop_process(self.xvc)
  serials=list(self.serials.values());self.serials.clear()
  for s in serials:
   try:s.close()
   except Exception:pass
