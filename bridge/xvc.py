"""Experimental loopback XVC server over CH347T raw JTAG bit commands.
Wire commands cross-checked against openFPGALoader ch347jtag.cpp (Apache-2.0).
Independent Python implementation; hardware qualification is still required.
"""
from __future__ import annotations
import argparse, math, socket, struct, sys
MAX_BITS=16384
CLOCKS=[468750,937500,1875000,3750000,7500000,15000000,30000000,60000000]
class CH347JTAG:
 def __init__(self,bus,address,freq):
  import usb.core,usb.util
  self.util=usb.util;self.detached=False
  candidates=list(usb.core.find(find_all=True,idVendor=0x1a86,idProduct=0x55dd))
  if len(candidates)!=1:raise RuntimeError('XVC requires exactly one CH347T in mode 3')
  self.dev=candidates[0]
  if self.dev.bus!=bus or self.dev.address!=address:raise RuntimeError('USB identity changed')
  if self.dev.bcdDevice<0x241:raise RuntimeError('XVC requires CH347T 2.41 or later')
  try:
   if self.dev.is_kernel_driver_active(2):self.dev.detach_kernel_driver(2);self.detached=True
  except (NotImplementedError,usb.core.USBError):pass
  self.util.claim_interface(self.dev,2)
  try:self.dev.read(0x86,512,timeout=100)
  except usb.core.USBTimeoutError:pass
  self.clock(freq)
 def transfer(self,command,payload,expected):
  packet=bytes([command])+struct.pack('<H',len(payload))+payload
  written=self.dev.write(0x06,packet,timeout=1000)
  if written!=len(packet):raise RuntimeError('Incomplete USB write')
  reply=bytearray()
  while len(reply)<expected+3:
   part=self.dev.read(0x86,512,timeout=1000)
   if not part:raise RuntimeError('Empty USB reply')
   reply.extend(part)
  if reply[0]!=command or struct.unpack('<H',reply[1:3])[0]!=expected or len(reply)!=expected+3:raise RuntimeError('Invalid CH347 JTAG reply')
  return bytes(reply[3:])
 def clock(self,hz):
  index=max((i for i,v in enumerate(CLOCKS) if v<=hz),default=0)
  reply=self.transfer(0xd0,bytes([0,index,0,0,0,0]),1)
  if reply!=b'\x00':raise RuntimeError('CH347 clock configuration failed')
  self.hz=CLOCKS[index];return math.ceil(1_000_000_000/self.hz)
 def shift(self,count,tms,tdi):
  if count<1 or count>MAX_BITS:raise ValueError('Invalid shift length')
  n=(count+7)//8
  if len(tms)!=n or len(tdi)!=n:raise ValueError('Invalid vector length')
  result=bytearray(n)
  for start in range(0,count,248):
   size=min(248,count-start);payload=bytearray();value=0
   for i in range(start,start+size):
    value=((tms[i//8]>>(i%8))&1)*2+((tdi[i//8]>>(i%8))&1)*16
    payload.extend([value,value|1])
   payload.append(value)
   reply=self.transfer(0xd2,bytes(payload),size)
   for offset,bit in enumerate(reply):
    if bit not in [0,1]:raise RuntimeError('Invalid TDO bit')
    if bit:result[(start+offset)//8]|=1<<((start+offset)%8)
  return bytes(result)
 def close(self):
  try:self.util.release_interface(self.dev,2)
  finally:
   if self.detached:
    try:self.dev.attach_kernel_driver(2)
    except Exception:pass
   self.util.dispose_resources(self.dev)

def exact(sock,length):
 out=bytearray()
 while len(out)<length:
  data=sock.recv(length-len(out))
  if not data:raise EOFError()
  out.extend(data)
 return bytes(out)
def serve_client(sock,jtag):
 while True:
  name=bytearray()
  while not name.endswith(b':'):
   name.extend(exact(sock,1))
   if len(name)>8:raise ValueError('Invalid XVC command')
  if name==b'getinfo:':sock.sendall(b'xvcServer_v1.0:2048\n')
  elif name==b'settck:':
   ns=struct.unpack('<I',exact(sock,4))[0]
   if ns==0:raise ValueError('TCK period must be nonzero')
   sock.sendall(struct.pack('<I',jtag.clock(min(30000000,1_000_000_000//ns))))
  elif name==b'shift:':
   count=struct.unpack('<I',exact(sock,4))[0]
   if not 1<=count<=MAX_BITS:raise ValueError('XVC shift too large or empty')
   n=(count+7)//8;tms=exact(sock,n);tdi=exact(sock,n);sock.sendall(jtag.shift(count,tms,tdi))
  else:raise ValueError('Unsupported XVC command')
def main():
 a=argparse.ArgumentParser();a.add_argument('--bus',type=int,required=True);a.add_argument('--address',type=int,required=True);a.add_argument('--freq',type=int,default=1000000);a.add_argument('--port',type=int,default=2542);args=a.parse_args()
 adapter=CH347JTAG(args.bus,args.address,args.freq)
 try:
  with socket.socket() as server:
   server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('127.0.0.1',args.port));server.listen(1)
   print(f'XVC ready on 127.0.0.1:{args.port} · experimental · {adapter.hz} Hz',flush=True)
   while True:
    conn,addr=server.accept()
    with conn:
     conn.settimeout(30)
     try:serve_client(conn,adapter)
     except EOFError:pass
     except (ValueError,TimeoutError,ConnectionError) as e:print('XVC client closed: '+str(e),flush=True)
 finally:adapter.close()
if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:pass
 except Exception as e:print('XVC failed: '+str(e),flush=True);sys.exit(1)
