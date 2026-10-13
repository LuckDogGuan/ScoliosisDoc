"""Replay the optional fault transport against a local HTTP server; no device access."""
import ast,json,socket,tempfile,threading,time,types,http.server
from pathlib import Path
source=Path(__file__).parents[2]/'工具/Python中间层/usb_debug_transport.py'
# Only the pure policy/forward functions are loaded; setup/authentication never executes.
tree=ast.parse(source.read_text(encoding='utf-8'))
names={'fault_policy','fault_record','fault_once','record','forward'}
module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
folder=Path(tempfile.mkdtemp(prefix='usb-fault-selfcheck-'))
args=types.SimpleNamespace(serial='serial-test',device='CAM-test',fault_config=folder/'policy.json',fault_log=folder/'faults.jsonl',log=folder/'transport.jsonl',flutter_port=0)
env=dict(args=args,json=json,threading=threading,time=time,socket=socket,lock=threading.Lock(),fault_claims={})
exec(compile(module,str(source),'exec'),env)
seen=[]
class Receiver(http.server.BaseHTTPRequestHandler):
 def log_message(self,*_):pass
 def do_POST(self):
  data=self.rfile.read(int(self.headers['Content-Length']));seen.append((self.path,len(data)))
  self.send_response(200 if len(data)==int(self.headers['Content-Length']) else 400)
  self.send_header('Connection','close');self.end_headers();self.wfile.write(b'{"ok":true}')
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Receiver);args.flutter_port=server.server_port
threading.Thread(target=server.serve_forever,daemon=True).start()
def policy(name,**flags):
 args.fault_config.write_text(json.dumps(dict(serial=args.serial,device_id=args.device,fault_id=name,expires_at=time.time()+60,**flags)))
def exchange(path,body):
 client,channel=socket.socketpair();client.settimeout(3)
 env['forward'](channel)
 request=(f'POST {path} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()+body
 try:client.sendall(request);client.shutdown(socket.SHUT_WR)
 except OSError:pass
 answer=b''
 try:
  while True:
   chunk=client.recv(65536)
   if not chunk:break
   answer+=chunk
 except OSError:pass
 finally:client.close()
 return answer
try:
 policy('normal')
 assert b'200' in exchange('/api/v1/capture/status',b'{"phase":"recording"}')
 before=len(seen);policy('record-loss',drop_recording_status=True)
 assert exchange('/api/v1/capture/status',b'{"phase":"recording"}')==b'';assert len(seen)==before
 policy('ack-loss',drop_completed_response=True)
 assert exchange('/api/v1/capture/status',b'{"phase":"completed"}')==b''
 assert b'200' in exchange('/api/v1/capture/status',b'{"phase":"completed"}')
 policy('half-upload',cut_upload_once=True)
 exchange('/api/v1/capture/file',b'x'*500000)
 assert seen[-1][1]<500000
 assert b'200' in exchange('/api/v1/capture/file',b'x'*500000)
 modes={json.loads(line)['mode'] for line in args.fault_log.read_text().splitlines()}
 assert {'recording_status_dropped','completed_response_dropped','half_upload_cut'}<=modes
 args.fault_config.write_text(json.dumps(dict(serial='wrong',device_id=args.device,expires_at=time.time()+60,block_http=True)))
 assert env['fault_policy']()=={}
 print(json.dumps(dict(check='passed',modes=sorted(modes),retained_evidence=str(folder))))
finally:server.shutdown();server.server_close()

