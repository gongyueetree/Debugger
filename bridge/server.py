from __future__ import annotations
import argparse,base64,hmac,json,os,secrets,sys,subprocess,threading,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .core import Studio,UserError
BASE=Path(__file__).resolve().parent.parent
class Handler(BaseHTTPRequestHandler):
 server_version='DebugStudio/0.2'
 def log_message(self,*args):pass
 def send(self,data,status=200,kind='application/json'):
  raw=json.dumps(data,ensure_ascii=False).encode() if kind=='application/json' else data
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  origin=self.headers.get('Origin')
  if origin in self.server.origins:
   self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Vary','Origin');self.send_header('Access-Control-Allow-Private-Network','true')
  self.end_headers();self.wfile.write(raw)
 def allowed(self,auth=True):
  if self.headers.get('Host') not in self.server.hosts:raise UserError('Host 不在允许列表')
  origin=self.headers.get('Origin')
  if origin and origin not in self.server.origins:raise UserError('此网页来源未授权，请在本地服务启动参数中添加精确来源')
  if auth and not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.token):raise UserError('配对码无效，请使用本次启动的配对码')
 def do_OPTIONS(self):
  try:self.allowed(False)
  except UserError as e:return self.send({'error':str(e)},403)
  self.send_response(204);self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin',''));self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type');self.send_header('Access-Control-Allow-Private-Network','true');self.end_headers()
 def do_GET(self):
  try:
   path=urlparse(self.path).path;self.allowed(path.startswith('/api/'))
   s=self.server.studio
   if path=='/api/status':return self.send(s.status())
   if path=='/api/jobs':return self.send(list(s.jobs.values())[-200:][::-1])
   if path=='/api/uart':return self.send(s.uart_log)
   if path.startswith('/api/download/'):
    fid=path.rsplit('/',1)[-1];f=s.files.get(fid)
    if not f:raise UserError('文件不存在或服务已重启')
    return self.send(Path(f['path']).read_bytes(),kind='application/octet-stream')
   if path.startswith('/api/jobs/'):return self.send(s.jobs.get(path.rsplit('/',1)[-1]) or {})
   rel='index.html' if path=='/' else path.lstrip('/')
   file=(BASE/'dist'/rel).resolve()
   if not file.is_relative_to((BASE/'dist').resolve()) or not file.is_file():return self.send({'error':'Not found'},404)
   mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.zip':'application/zip','.json':'application/json'}.get(file.suffix,'application/octet-stream')
   return self.send(file.read_bytes(),kind=mime)
  except UserError as e:return self.send({'error':str(e)},403)
  except Exception as e:return self.send({'error':str(e)},500)
 def do_POST(self):
  try:
   self.allowed();n=int(self.headers.get('Content-Length',0))
   if n<1 or n>90*1024*1024:raise UserError('请求大小不合法')
   if not self.headers.get('Content-Type','').startswith('application/json'):raise UserError('仅接受 JSON 请求')
   d=json.loads(self.rfile.read(n));p=urlparse(self.path).path;s=self.server.studio
   if p=='/api/upload':return self.send(s.upload(str(d.get('name','')),base64.b64decode(d.get('data',''),validate=True)))
   if p=='/api/prepare':return self.send(s.prepare(d))
   if p=='/api/execute':return self.send(s.execute(d.get('plan_id'),d.get('confirmation')))
   if p=='/api/cancel':return self.send(s.cancel(d.get('job_id')))
   if p=='/api/disconnect':
    if s.lock.locked():raise UserError('请先取消并等待当前任务结束')
    s.shutdown();return self.send({'disconnected':True})
   if p=='/api/assistant':
    if not os.getenv('CH347_EVE_URL'):raise UserError('尚未启用 eve AI。内置任务助手无需模型即可使用。')
    message=str(d.get('message',''))[:6000]
    env=os.environ.copy();env['CH347_BRIDGE_TOKEN']=self.server.token;env['CH347_BRIDGE_URL']=f'http://127.0.0.1:{self.server.server_port}'
    proc=subprocess.run(['node',str(BASE/'agent-runtime'/'ask.mjs')],input=json.dumps({'message':message}),capture_output=True,text=True,timeout=90,env=env)
    if proc.returncode:raise UserError(proc.stderr[-1500:])
    return self.send(json.loads(proc.stdout))
   return self.send({'error':'Not found'},404)
  except (UserError,ValueError) as e:return self.send({'error':str(e)},400)
  except Exception as e:return self.send({'error':str(e)},500)

def make_server(port=8765,root=None,token=None,origins=()):
 s=ThreadingHTTPServer(('127.0.0.1',port),Handler);s.token=token or secrets.token_urlsafe(32);s.hosts={f'127.0.0.1:{s.server_port}',f'localhost:{s.server_port}'};s.origins={f'http://{h}' for h in s.hosts}|set(origins);s.studio=Studio(root or Path.home()/'.ch347-studio');return s

def main():
 a=argparse.ArgumentParser();a.add_argument('--port',type=int,default=8765);a.add_argument('--allow-origin',action='append',default=[]);a.add_argument('--no-browser',action='store_true');args=a.parse_args()
 origins=args.allow_origin+['https://ch347-debug-studio-gy.gongyusu.chatgpt.site']
 for o in origins:
  u=urlparse(o)
  if u.scheme not in ['https','http'] or u.path or u.query or u.fragment:raise SystemExit('--allow-origin 必须是精确 origin，无路径')
 s=make_server(args.port,origins=origins)
 print(f'\nDebug Studio · CH347 + RP2040\n本地网页：http://127.0.0.1:{s.server_port}\n本次配对码：{s.token}\n仅监听本机。按 Ctrl+C 停止。\n',flush=True)
 if not args.no_browser:webbrowser.open(f'http://127.0.0.1:{s.server_port}/#pair={s.token}')
 try:s.serve_forever()
 except KeyboardInterrupt:pass
 finally:s.studio.shutdown();s.server_close()
if __name__=='__main__':main()
