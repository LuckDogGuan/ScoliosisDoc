"""USB-only diagnostic V3 transport: pinned SSH over ADB, raw UDP and reverse HTTP."""
import argparse,base64,hashlib,http.server,json,os,secrets,shlex,socket,subprocess,threading,time
from pathlib import Path
import paramiko
parser=argparse.ArgumentParser()
parser.add_argument('--serial',required=True)
parser.add_argument('--device',required=True)
parser.add_argument('--port',type=int,default=18085)
parser.add_argument('--flutter-port',type=int,default=8081)
parser.add_argument('--ssh-local-port',type=int,default=22023)
parser.add_argument('--log',type=Path,required=True)
parser.add_argument('--fault-config',type=Path)
parser.add_argument('--fault-log',type=Path)
args=parser.parse_args()
transport=None
control_transport=None
lock=threading.Lock()
fault_claims={}
def fault_policy():
    if args.fault_config is None:return {}
    try:
        policy=json.loads(args.fault_config.read_text(encoding='utf-8-sig'))
        if policy.get('serial')!=args.serial or policy.get('device_id')!=args.device:return {}
        if not isinstance(policy.get('expires_at'),(int,float)) or policy['expires_at']<time.time():return {}
        return policy
    except (OSError,ValueError):return {}
def fault_record(mode,policy,**row):
    row.update(event='injected_fault',mode=mode,fault_id=policy.get('fault_id'),device=args.device,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    if args.fault_log:
        with lock:
            with args.fault_log.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
def fault_once(policy,mode):
    key=(policy.get('fault_id'),mode)
    with lock:
        count=fault_claims.get(key,0)
        if count>=1:return False
        fault_claims[key]=count+1;return True
def record(**row):
    row['utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    with lock:
        with args.log.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
def adb(*parts):
    return subprocess.run(['adb','-s',args.serial,*parts],capture_output=True,check=True,timeout=20).stdout.decode('utf-8','replace').replace('\r','').strip()
def remote(command):
    channel=control_transport.open_session(timeout=5);channel.settimeout(5);channel.exec_command(command)
    result=channel.makefile('rb').read();code=channel.recv_exit_status();channel.close()
    if code:raise RuntimeError('remote diagnostic command failed')
    return result
def forward(channel,*_):
    def handle():
        peer=None
        try:
            channel.settimeout(65)
            policy=fault_policy();initial=b'';path='';phase=''
            if policy:
                channel.settimeout(5)
                while b'\r\n\r\n' not in initial:
                    chunk=channel.recv(4096)
                    if not chunk:raise EOFError()
                    initial+=chunk
                    if len(initial)>16384:raise ValueError('debug HTTP header too large')
                header,body=initial.split(b'\r\n\r\n',1)
                path=header.split(b' ')[1].decode('ascii','replace')
                if path=='/api/v1/capture/status':
                    lengths=[line.split(b':',1)[1].strip() for line in header.split(b'\r\n') if line.lower().startswith(b'content-length:')]
                    length=int(lengths[0]) if lengths else 0
                    if not 0<length<=4096:raise ValueError('invalid debug status length')
                    while len(body)<length:
                        chunk=channel.recv(length-len(body))
                        if not chunk:raise EOFError()
                        body+=chunk;initial+=chunk
                    phase=json.loads(body[:length]).get('phase','')
                if policy.get('block_http') or (policy.get('drop_recording_status') and phase=='recording'):
                    fault_record('http_blocked' if policy.get('block_http') else 'recording_status_dropped',policy,path=path,phase=phase)
                    return
            peer=socket.create_connection(('127.0.0.1',args.flutter_port),timeout=5)
            channel.settimeout(65);peer.settimeout(65)
            drop_response=phase=='completed' and policy.get('drop_completed_response') and fault_once(policy,'completed_response')
            upload=path=='/api/v1/capture/file'
            cut=upload and policy.get('cut_upload_once') and fault_once(policy,'upload_cut')
            delay=min(max(float(policy.get('slow_upload_ms',0))/1000,0),2) if upload else 0
            if initial:peer.sendall(initial)
            def pump(reader,writer,to_board):
                transferred=len(initial) if not to_board else 0
                try:
                    while True:
                        chunk=reader.recv(65536)
                        if not chunk:break
                        if to_board and drop_response:
                            fault_record('completed_response_dropped',policy,path=path)
                            break
                        if not to_board and delay:time.sleep(delay)
                        writer.sendall(chunk);transferred+=len(chunk)
                        if not to_board and cut and transferred>=131072:
                            fault_record('half_upload_cut',policy,path=path,bytes=transferred)
                            break
                except (OSError,EOFError):pass
                finally:
                    try:writer.shutdown(socket.SHUT_WR)
                    except (OSError,AttributeError):pass
            if delay:fault_record('slow_upload',policy,path=path,milliseconds=int(delay*1000))
            thread=threading.Thread(target=pump,args=(peer,channel,True),daemon=True);thread.start()
            try:pump(channel,peer,False);thread.join(66)
            finally:peer.close();channel.close()
        except (OSError,EOFError,ValueError) as error:
            record(event='forward_error',error=type(error).__name__)
        finally:
            if peer is not None:peer.close()
            channel.close()
    threading.Thread(target=handle,daemon=True).start()

class Bridge(http.server.BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_POST(self):
        try:
            if self.path!='/debug/udp':raise ValueError('unsupported debug path')
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=12288:raise ValueError('invalid packet size')
            self.connection.settimeout(5)
            body=json.loads(self.rfile.read(n));raw=base64.b64decode(body['packet'],validate=True)
            packet=json.loads(raw)
            if len(raw)>4096 or body.get('port')!=37020:raise ValueError('invalid UDP destination')
            if packet.get('version')==3:
                if packet.get('device_id')!=args.device:raise ValueError('wrong instrument')
            elif packet.get('version')!=2 or packet.get('op')!='discover':raise ValueError('unsupported protocol')
            timeout=max(.05,min(body.get('wait_ms',1000)/1000,2))
            code=("import socket,base64,json;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout("+repr(timeout)+");s.sendto(base64.b64decode("+repr(base64.b64encode(raw).decode())+"),('127.0.0.1',37020));"
                  "\ntry:\n r,a=s.recvfrom(4097);print(base64.b64encode(r).decode())\nexcept socket.timeout:print('')\nfinally:s.close()")
            started=time.monotonic();policy=fault_policy()
            if policy.get('block_udp'):
                fault_record('udp_blocked',policy,op=packet.get('op'));received=b''
            else:received=remote('python3 -c '+shlex.quote(code)).strip()
            replies=[] if not received else [dict(packet=received.decode(),address='127.0.0.1',port=37020)]
            record(op=packet.get('op'),device=args.device,sequence=packet.get('sequence'),received=bool(received),control_elapsed_ms=round((time.monotonic()-started)*1000))
            data=json.dumps(dict(replies=replies)).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        except Exception as error:
            record(error=type(error).__name__)
            try:self.send_error(502,'USB debug transport failed')
            except OSError:pass
args.log.parent.mkdir(exist_ok=True,parents=True)
if args.fault_log:args.fault_log.parent.mkdir(exist_ok=True,parents=True)
try:
    serial=adb('shell','cat /proc/device-tree/serial-number').rstrip('\x00')
    config=json.loads(adb('shell','cat /opt/instrument/config.json'))
    if serial!=args.serial or config.get('device_id')!=args.device:raise RuntimeError('device identity mismatch')
    adb('forward','tcp:'+str(args.ssh_local_port),'tcp:22')
    transport=paramiko.Transport(('127.0.0.1',args.ssh_local_port));transport.start_client(timeout=5)
    key=transport.get_remote_server_key()
    keyfile={'ssh-ed25519':'ed25519','ecdsa-sha2-nistp256':'ecdsa','ssh-rsa':'rsa'}.get(key.get_name())
    if keyfile is None:raise RuntimeError('unsupported SSH host key')
    pinned=adb('shell','cat /etc/ssh/ssh_host_'+keyfile+'_key.pub').split()[1]
    if base64.b64decode(pinned)!=key.asbytes():raise RuntimeError('SSH identity mismatch')
    transport.auth_password('root',os.environ.get('LUCKFOX_SSH_PASSWORD','luckfox'))
    # Keep control traffic off the SSH stream carrying multi-megabyte videos.
    control_transport=paramiko.Transport(('127.0.0.1',args.ssh_local_port));control_transport.start_client(timeout=5)
    if control_transport.get_remote_server_key().asbytes()!=key.asbytes():raise RuntimeError('control SSH identity mismatch')
    control_transport.auth_password('root',os.environ.get('LUCKFOX_SSH_PASSWORD','luckfox'))
    transport.request_port_forward('127.0.0.1',args.port,handler=forward)
    record(event='ready',serial=args.serial,device=args.device,transport='usb_ssh',ssh_fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('='),port=args.port,flutter_port=args.flutter_port)
    print('USB_DEBUG_READY '+str(args.port),flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1',args.port),Bridge).serve_forever()
finally:
    if control_transport is not None:control_transport.close()
    if transport is not None:transport.close()
    try:adb('forward','--remove','tcp:'+str(args.ssh_local_port))
    except Exception:pass
