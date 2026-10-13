"""Validate the WSL release, restore saved pairing/config with volume 10, start normal runtime.

Read-only by default. --apply requires an idle, unpaired, gated-off instrument,
the exact tested binary, and identical camera/startup/sound payloads. No video is deleted.
"""
import argparse,base64,hashlib,io,json,os,secrets,shlex,subprocess,tarfile,time
from pathlib import Path
import paramiko

p=argparse.ArgumentParser()
for name in ('serial','device','package','package-sha','backup','report'):p.add_argument('--'+name,required=True)
p.add_argument('--apply',action='store_true')
p.add_argument('--adb',default=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe')
args=p.parse_args()
package=Path(args.package)
assert hashlib.sha256(package.read_bytes()).hexdigest()==args.package_sha
payload={}
with tarfile.open(package,'r:gz') as archive:
 for member in archive.getmembers():
  if member.isfile():payload[member.name.split('/',1)[1]]=archive.extractfile(member).read()
assert payload['VERSION'].strip()==b'3.3.9'
for line in payload['SHA256SUMS'].decode().splitlines():
 digest,name=line.split(None,1);name=name.strip().lstrip('*').removeprefix('./')
 assert hashlib.sha256(payload[name]).hexdigest()==digest
expected=hashlib.sha256(payload['instrument_app']).hexdigest()

def adb(command):
 return subprocess.check_output([args.adb,'-s',args.serial,'shell',command],timeout=20).decode().replace('\r','').strip().rstrip('\x00')
assert adb('cat /proc/device-tree/serial-number')==args.serial
assert args.backup.startswith('/opt/instrument/backups/stability-dev-')
assert Path(args.backup).name==args.backup.split('/')[-1]
t=paramiko.Transport(('127.0.0.1',22023));t.start_client(timeout=5)
key=t.get_remote_server_key();kind={'ssh-ed25519':'ed25519','ecdsa-sha2-nistp256':'ecdsa','ssh-rsa':'rsa'}[key.get_name()]
assert base64.b64decode(adb('cat /etc/ssh/ssh_host_'+kind+'_key.pub').split()[1])==key.asbytes()
t.auth_password('root',os.getenv('LUCKFOX_SSH_PASSWORD','luckfox'))
sftp=paramiko.SFTPClient.from_transport(t)

def run(command):
 channel=t.open_session(timeout=5);channel.settimeout(20);channel.exec_command(command)
 out=channel.makefile('rb').read().decode().strip();code=channel.recv_exit_status();channel.close()
 if code:raise RuntimeError('finalization command failed')
 return out

def hello():
 q=dict(version=3,op='hello_query',device_id=args.device,host_id='finalize-observer',sequence=0,nonce=secrets.token_hex(16))
 code="import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(2);s.sendto("+repr(json.dumps(q).encode())+",('127.0.0.1',37020));print(s.recvfrom(4097)[0].decode())"
 reply=json.loads(run('python3 -c '+shlex.quote(code)))
 assert reply['device_id']==args.device and reply['nonce']==q['nonce']
 return reply

def write(path,data,mode=0o600):
 with sftp.open(path+'.stability-final','wb') as f:f.write(data);f.flush()
 sftp.chmod(path+'.stability-final',mode)
 assert run('sha256sum '+shlex.quote(path+'.stability-final')).split()[0]==hashlib.sha256(data).hexdigest()
 sftp.posix_rename(path+'.stability-final',path)

report=dict(device=args.device,serial=args.serial,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),apply=args.apply,package_sha256=args.package_sha,binary_sha256=expected)
try:
 config=json.loads(sftp.open('/opt/instrument/config.json').read());assert config['device_id']==args.device
 restored=json.loads(sftp.open(args.backup+'/config.json').read());assert restored['device_id']==args.device
 restored['audio']['volume']=10
 pair=sftp.open(args.backup+'/pair-v3.json').read();assert not json.loads(pair)['host_id']
 check_map={'instrument_app':'/opt/instrument/bin/instrument_app','luckfox_mux_adapter.so':'/opt/instrument/bin/luckfox_mux_adapter.so','deploy/RkLunch.sh':'/RkLunch.sh','deploy/S80instrument':'/oem/usr/etc/init.d/S80instrument'}
 check_map.update({name:'/opt/instrument/'+name for name in payload if name.startswith('sounds/') and name.endswith('.wav')})
 verified=[]
 for name,path in check_map.items():
  digest=hashlib.sha256(payload[name]).hexdigest()
  actual=run('sha256sum '+shlex.quote(path)).split()[0]
  assert actual==digest,(path,'installed bytes differ from release')
  verified.append(dict(path=path,sha256=digest))
 report['payload_files_verified']=verified
 before=hello();kernel=before['system_boot_id'];rkipc=run('pidof rkipc')
 report.update(before_boot=before['boot_id'],kernel_boot=kernel,rkipc_pid=rkipc)
 if args.apply:
  assert before['phase']=='idle' and not before['gate_enabled'] and not before['paired_host_id'] and before['metrics']['pending_count']==0
  pid=str(before['application_pid']);assert pid.isdecimal()
  rollback='/opt/instrument/backups/stability-final-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
  run('mkdir -p '+rollback)
  for path in ('/opt/instrument/config.json','/opt/instrument/state/pair-v3.json','/opt/instrument/installed-version','/opt/instrument/installed-build.txt','/opt/instrument/state/version'):
   run('cp -p '+path+' '+rollback+'/'+Path(path).name)
  run('kill -TERM '+pid)
  for _ in range(80):
   if run('test -d /proc/'+pid+' && echo running || echo stopped')=='stopped':break
   time.sleep(.1)
  else:raise RuntimeError('normal shutdown did not finish; rollback retained')
  write('/opt/instrument/config.json',(json.dumps(restored,ensure_ascii=False,indent=2)+'\n').encode())
  write('/opt/instrument/state/pair-v3.json',pair)
  write('/opt/instrument/installed-version',payload['VERSION'],0o644)
  write('/opt/instrument/installed-build.txt',payload['BUILD.txt'],0o644)
  if 'sounds/stability-voice-manifest.json' in payload:write('/opt/instrument/sounds/stability-voice-manifest.json',payload['sounds/stability-voice-manifest.json'],0o644)
  run('sync')
  run('env LD_LIBRARY_PATH=/oem/usr/lib:/usr/lib:/lib sh /oem/usr/etc/init.d/S80instrument start')
  for _ in range(30):
   try:
    after=hello()
    if after['phase']=='idle' and not after['camera_fault']:break
   except (RuntimeError,OSError,ValueError):pass
   time.sleep(.2)
  else:raise RuntimeError('normal runtime not ready; rollback retained')
  assert after['system_boot_id']==kernel and run('pidof rkipc')==rkipc
  assert after['volume']==after['saved_volume']==10 and not after['gate_enabled'] and not after['paired_host_id']
  environment=sftp.open('/proc/'+str(after['application_pid'])+'/environ').read().split(b'\0')
  assert not any(value.startswith(b'INSTRUMENT_BUTTON_FILE=') for value in environment)
  assert json.loads(sftp.open('/opt/instrument/config.json').read())==restored
  assert sftp.open('/opt/instrument/state/pair-v3.json').read()==pair
  assert sftp.open('/opt/instrument/installed-version').read()==payload['VERSION']
  assert sftp.open('/opt/instrument/installed-build.txt').read()==payload['BUILD.txt']
  assert run('sha256sum /opt/instrument/bin/instrument_app').split()[0]==expected
  report.update(rollback=rollback,after_boot=after['boot_id'],normal_pid=after['application_pid'],volume=10,saved_volume=10,config_restored_except_volume=True,pair_restored=True,simulation_disabled=True,status='normal_runtime_verified')
 else:report['status']='release_payload_verified_readonly'
finally:
 sftp.close();t.close()
 Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
