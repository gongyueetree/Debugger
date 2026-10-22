"""WCH packed ABI + isolated HID transactions. No emulated hardware results."""
from __future__ import annotations
import ctypes as C, importlib.util, json, os, sys, time
from .core import UserError

class SPIConfig(C.Structure):
 _pack_=1
 _fields_=[('mode',C.c_uint8),('clock',C.c_uint8),('msb',C.c_uint8),('interval',C.c_uint16),('default',C.c_uint8),('cs',C.c_uint32),('cs1_high',C.c_uint8),('cs2_high',C.c_uint8),('auto_cs',C.c_uint16),('active_delay',C.c_uint16),('inactive_delay',C.c_uint32)]
assert C.sizeof(SPIConfig)==20
SPEEDS=[60000000,30000000,15000000,7500000,3750000,1875000,937500,468750]
def clock_level(hz):
 return next((i for i,v in enumerate(SPEEDS) if v<=hz),7)
def provider_info(mode,op):
 if mode==2 and not op.startswith('gpio.'):
  ok=bool(importlib.util.find_spec('ch347api') and importlib.util.find_spec('hid'))
  return {'available':ok,'reason':'模式 2 需要 ch347api 和 hidapi'}
 if op.startswith('gpio.') and mode!=3:return {'available':False,'reason':'GPIO 后端仅开放模式 3 的 GPIO3/5/6，避免 UART/I²C 复用冲突'}
 sdk=os.getenv('CH347_LIBRARY','')
 return {'available':bool(sdk and os.path.isfile(sdk) and sys.platform!='darwin'),'reason':'此操作需要 Windows/Linux 官方 WCH SDK；设置 CH347_LIBRARY 为 DLL/.so 的绝对路径（Linux 另需 CH347_DEVICE_PATH）'}

class SDK:
 def __init__(self):
  self.win=sys.platform=='win32';self.lib=(C.WinDLL if self.win else C.CDLL)(os.environ['CH347_LIBRARY']);self.arg=C.c_uint32 if self.win else C.c_int;self.ret=C.c_int32 if self.win else C.c_bool
  self.bind('CH347OpenDevice',[C.c_uint32] if self.win else [C.c_char_p],C.c_void_p if self.win else C.c_int)
  if self.win:
   self.handle=int(os.getenv('CH347_DEVICE_INDEX','0'));r=self.lib.CH347OpenDevice(self.handle)
   if r is None or r==C.c_void_p(-1).value:raise UserError('WCH SDK 无法打开设备，请检查驱动和设备索引')
  else:
   path=os.getenv('CH347_DEVICE_PATH','')
   if not path.startswith('/dev/ch34x_pis'):raise UserError('请设置 CH347_DEVICE_PATH=/dev/ch34x_pis0（以实际节点为准）')
   self.handle=self.lib.CH347OpenDevice(path.encode())
   if self.handle<0:raise UserError('WCH SDK 打开设备失败，请检查驱动、节点和权限')
  self.bind('CH347CloseDevice',[self.arg],self.ret)
  name='CH347SetTimeout' if self.win else 'CH34xSetTimeout'
  if hasattr(self.lib,name):self.bind(name,[self.arg,C.c_uint32,C.c_uint32],self.ret)(self.handle,1000,1000)
 def bind(self,name,args,ret):
  f=getattr(self.lib,name);f.argtypes=args;f.restype=ret;return f
 def checked(self,ok):
  if not ok:raise UserError('WCH SDK 返回失败，不能确认事务完成')
 def i2c_init(self):self.checked(self.bind('CH347I2C_Set',[self.arg,self.arg],self.ret)(self.handle,1))
 def i2c(self,address,data=b'',length=0):
  prefix=bytes([(address<<1) | (1 if length and not data else 0)])+data
  w=C.create_string_buffer(prefix);r=C.create_string_buffer(max(1,length))
  if not data and not length:
   ack=self.arg();name='CH347StreamI2C_RetACK' if self.win else 'CH347StreamI2C_RetAck'
   ok=self.bind(name,[self.arg,self.arg,C.c_void_p,self.arg,C.c_void_p,C.POINTER(self.arg)],self.ret)(self.handle,len(prefix),w,0,r,C.byref(ack))
   return bool(ok) and ack.value>=1,b''
  ok=self.bind('CH347StreamI2C',[self.arg,self.arg,C.c_void_p,self.arg,C.c_void_p],self.ret)(self.handle,len(prefix),w,length,r)
  return bool(ok),bytes(r.raw[:length])
 def spi(self,data,mode,hz):
  level=clock_level(hz);cfg=SPIConfig(mode,level,1,0,0xff,0x80,0,0,1,0,0)
  self.checked(self.bind('CH347SPI_Init',[self.arg,C.POINTER(SPIConfig)],self.ret)(self.handle,C.byref(cfg)))
  buf=C.create_string_buffer(data)
  args=[self.arg,C.c_uint32,C.c_uint32,C.c_void_p] if self.win else [self.arg,C.c_bool,C.c_uint8,C.c_int,C.c_void_p]
  f=self.bind('CH347SPI_WriteRead',args,self.ret)
  self.checked(f(self.handle,0x80,len(data),buf) if self.win else f(self.handle,False,0x80,len(data),buf))
  return bytes(buf.raw[:len(data)]),SPEEDS[level]
 def gpio(self,op,p):
  direction=C.c_uint8();levels=C.c_uint8()
  get=self.bind('CH347GPIO_Get',[self.arg,C.POINTER(C.c_uint8),C.POINTER(C.c_uint8)],self.ret)
  self.checked(get(self.handle,C.byref(direction),C.byref(levels)))
  if op=='gpio.write':
   bit=1<<p['pin'];out=(levels.value&~bit)|(p['value']<<p['pin'])
   self.checked(self.bind('CH347GPIO_Set',[self.arg,C.c_uint8,C.c_uint8,C.c_uint8],self.ret)(self.handle,bit,direction.value|bit,out))
   self.checked(get(self.handle,C.byref(direction),C.byref(levels)))
  return {'direction':direction.value,'levels':levels.value,'pins':[{'pin':n,'value':int(bool(levels.value&(1<<n))),'direction':'out' if direction.value&(1<<n) else 'in'} for n in [3,5,6]]}
 def close(self):self.lib.CH347CloseDevice(self.handle)

class HID:
 def __init__(self):
  from ch347api import CH347HIDDev
  class CheckedHID(CH347HIDDev):
   def read(self,max_length,timeout_ms=0):
    data=super().read(max_length,timeout_ms=timeout_ms or 1000)
    if len(data)<3 or int.from_bytes(bytes(data[:2]),'little')+2>len(data):raise UserError('HID 响应超时或帧不完整')
    return data
   def write(self,data):
    n=super().write(data)
    if n!=len(data):raise UserError('HID 请求未完整发送')
    return n
  self.dev=CheckedHID()
 def i2c_init(self):
  r=self.dev.init_I2C(clock_freq_level=1)
  if r is False:raise UserError('HID I²C 初始化失败')
 def i2c(self,address,data=b'',length=0):
  if length>63 or len(data)>62:raise UserError('HID 单事务限制：读取 ≤63 字节，寄存器地址与写入数据合计 ≤62 字节')
  if length:return self.dev.i2c_read(address,length,register_addr=data or None)
  return self.dev.i2c_write(address,data),b''
 def spi(self,data,mode,hz):
  from ch347api import SPIDevice
  level=clock_level(hz)
  spi=SPIDevice(ch347_device=self.dev,clock_freq_level=level,is_MSB=True,mode=mode,write_read_interval=0,CS1_high=False,CS2_high=False,is_16bits=False)
  try:rx=bytes(spi.writeRead_CS1(data,keep_cs_active=False))
  finally:self.dev.set_CS1(False)
  if len(rx)!=len(data):raise UserError(f'SPI 返回 {len(rx)}/{len(data)} 字节，事务不完整')
  return rx,SPEEDS[level]
 def close(self):self.dev.close()

def operate(device,op,p):
 dev=HID() if device['mode']==2 else SDK()
 try:
  if op.startswith('i2c.'):
   dev.i2c_init()
   if op=='i2c.scan':
    found=[]
    for addr in range(8,120):
     ok,_=dev.i2c(addr)
     if ok:found.append(f'0x{addr:02X}')
    return {'addresses':found,'clock_hz':100000,'method':'address ACK probe'}
   reg=p['register'].to_bytes(p['reg_width'],'big')
   ok,data=dev.i2c(p['address'],reg+(bytes.fromhex(p['data']) if op=='i2c.write' else b''),p['length'] if op=='i2c.read' else 0)
   if not ok:raise UserError('I²C 未收到 ACK 或事务失败')
   if op=='i2c.read' and len(data)!=p['length']:raise UserError('I²C 返回长度不完整')
   return {'address':f'0x{p["address"]:02X}','hex':bytes(data).hex(' ').upper(),'bytes':len(data) if op=='i2c.read' else len(bytes.fromhex(p['data'])),'ack':True}
  if op=='spi.transfer':
   rx,hz=dev.spi(bytes.fromhex(p['data']),p['spi_mode'],p['freq'])
   return {'tx':p['data'],'rx':rx.hex(' ').upper(),'bytes':len(rx),'actual_clock_hz':hz,'chip_select':'SCS0'}
  if op.startswith('gpio.'):return dev.gpio(op,p)
  raise UserError('未实现的总线事务')
 finally:dev.close()

class HIDUART:
 def __init__(self,baud):
  from ch347api.__device import CH347HIDUART1
  self.dev=CH347HIDUART1();self.closed=False
  if not self.dev.init_UART(baudrate=baud,stop_bits=1,verify_bits=0,timeout=32):self.dev.close();raise UserError('HID UART 初始化失败')
 def read(self,n):
  if self.closed:return b''
  data=bytes(self.dev.read_raw(length=-1))
  if not data:time.sleep(.02)
  return data
 def write(self,data):
  import struct
  count=0
  for start in range(0,len(data),510):
   chunk=data[start:start+510];packet=struct.pack('<BH',0,len(chunk))+chunk
   if self.dev.write(packet)!=len(packet):raise UserError('HID UART 发送不完整')
   count+=len(chunk)
  return count
 def close(self):self.closed=True;self.dev.close()
def open_hid_uart(baud):return HIDUART(baud)

if __name__=='__main__':
 try:
  d=json.load(sys.stdin);result=operate(d['device'],d['op'],d['params']);print(json.dumps({'result':result}),flush=True)
 except Exception as e:print(json.dumps({'error':str(e)}),flush=True);sys.exit(1)
