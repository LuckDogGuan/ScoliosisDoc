"""Controlled coordinator SIGKILL, bound to serial, live capture and program hash."""
import argparse,base64,hashlib,json,os,re,secrets,shlex,subprocess,time
from pathlib import Path
import paramiko
p=argparse.ArgumentParser()
for key in ('serial','device','capture-id','expected-sha','button-file'):p.add_argument('--'+key,required=True)
p.add_argument('--raw-before',type=Path)
p.add_argument('--adb',default=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe')
args=p.parse_args()
assert re.fullmatch('[A-Za-z0-9_-]{1,128}',args.capture_id) and args.capture_id.startswith(args.device+'-')
assert re.fullmatch('/tmp/stability-buttons-[A-Za-z0-9_-]+',args.button_file)
def adb(command):
 return subprocess.check_output([args.adb,'-s',args.serial,'shell',command],timeout=20).decode().replace('\r','').strip().rstrip('\x00')
assert adb('cat /proc/device-tree/serial-number')==args.serial
assert json.loads(adb('cat /opt/instrument/config.json'))['device_id']==args.device
t=paramiko.Transport(('127.0.0.1',22023));t.start_client(timeout=5)
key=t.get_remote_server_key();kind={'ssh-ed25519':'ed25519','ecdsa-sha2-nistp256':'ecdsa','ssh-rsa':'rsa'}[key.get_name()]
assert base64.b64decode(adb('cat /etc/ssh/ssh_host_'+kind+'_key.pub').split()[1])==key.asbytes()
t.auth_password('root',os.getenv('LUCKFOX_SSH_PASSWORD','luckfox'))
def run(command):
 ch=t.open_session(timeout=5);ch.settimeout(20);ch.exec_command(command)
 out=ch.makefile('rb').read().decode().strip();code=ch.recv_exit_status();ch.close()
 if code:raise RuntimeError('controlled restart command failed')
 return out
def hello():
 q=dict(version=3,op='hello_query',device_id=args.device,host_id='injected-restart-observer',sequence=0,nonce=secrets.token_hex(16))
 code="import socket,json;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(2);s.sendto("+repr(json.dumps(q).encode())+",('127.0.0.1',37020));print(s.recvfrom(4097)[0].decode())"
 return json.loads(run('python3 -c '+shlex.quote(code)))
def camera():
 code="import socket,struct;s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(4);s.connect('/var/tmp/rkipc');f=s.makefile('rb');read=f.read;assert struct.unpack('<i',read(4))[0]==0;name=b'rk_storage_record_statue_get\\0';s.sendall(struct.pack('<i',len(name))+name);value=struct.unpack('<i',read(4))[0];assert struct.unpack('<i',read(4))[0]==0;print(value);f.close();s.close()"
 return int(run('python3 -c '+shlex.quote(code)))
try:
 before=hello()
 assert before['capture_id']==args.capture_id and before['phase']=='recording' and before['volume']==10
 assert run('sha256sum /opt/instrument/bin/instrument_app').split()[0]==args.expected_sha
 assert camera()==1
 old_pid=str(before['application_pid']);assert old_pid.isdecimal()
 kernel=before['system_boot_id'];rkipc=run('pidof rkipc')
 prior=set(json.loads(args.raw_before.read_text(encoding='utf-8'))) if args.raw_before else set(run('find /video0 -type f').splitlines())
 assert all(file.startswith('/video0/') for file in prior)
 run('kill -KILL '+old_pid)
 run("printf '0\\n' > "+args.button_file)
 for _ in range(60):
  if run('test -d /proc/'+old_pid+' && echo running || echo stopped')=='stopped':break
  time.sleep(.1)
 else:raise RuntimeError('killed coordinator still present')
 run('nohup env INSTRUMENT_BUTTON_FILE='+args.button_file+' LD_LIBRARY_PATH=/oem/usr/lib:/usr/lib:/lib /opt/instrument/bin/instrument_app /opt/instrument/config.json </dev/null >/opt/instrument/logs/stability-injected-restart.log 2>&1 &')
 for _ in range(30):
  try:
   after=hello()
   if not after['camera_fault'] and camera()==0:break
  except (RuntimeError,OSError,ValueError,KeyError):pass
  time.sleep(.2)
 else:raise RuntimeError('camera stopped state was not confirmed')
 assert after['boot_id']!=before['boot_id'] and after['system_boot_id']==kernel and run('pidof rkipc')==rkipc
 assert not after['gate_enabled'] and after['volume']==10 and after['saved_volume']==10
 raw_files=set(run('find /video0 -type f').splitlines())-prior
 # The interrupted raw camera file stays on the device and is never assigned to another person.
 retained=[]
 for file in sorted(raw_files):
  retained.append(dict(path=file,sha256=run('sha256sum '+shlex.quote(file)).split()[0]))
 print(json.dumps(dict(check='controlled_restart',device=args.device,capture_id=args.capture_id,
   old_boot=before['boot_id'],new_boot=after['boot_id'],kernel_boot=kernel,
   old_pid=int(old_pid),new_pid=after['application_pid'],rkipc_pid=rkipc,
   camera_stopped=True,gate_enabled=after['gate_enabled'],volume=10,retained_raw_files=retained)))
finally:t.close()

