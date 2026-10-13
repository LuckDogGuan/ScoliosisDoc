"""Identity-bound development deployment; retains byte-for-byte rollback files."""
import base64,hashlib,json,os,secrets,shlex,socket,subprocess,time
from pathlib import Path
import paramiko
SERIAL='3253c006806f5194';DEVICE='CAM-000123';BUTTON='/tmp/stability-buttons-20261013'
ROOT=Path(__file__).resolve().parent
SOURCE=Path(r'\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis')
LOG=ROOT/'development-deploy.jsonl'
def log(**row):
 row['utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 with LOG.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
def adb(command):
 return subprocess.run(['adb','-s',SERIAL,'shell',command],check=True,capture_output=True,timeout=20).stdout.decode().replace('\r','').strip().rstrip('\x00')
t=paramiko.Transport(('127.0.0.1',22023));t.start_client(timeout=5)
key=t.get_remote_server_key();kind={'ssh-ed25519':'ed25519','ecdsa-sha2-nistp256':'ecdsa','ssh-rsa':'rsa'}[key.get_name()]
assert base64.b64decode(adb('cat /etc/ssh/ssh_host_'+kind+'_key.pub').split()[1])==key.asbytes()
t.auth_password('root',os.environ.get('LUCKFOX_SSH_PASSWORD','luckfox'))
def run(command):
 ch=t.open_session(timeout=5);ch.settimeout(40);ch.exec_command(command)
 out=ch.makefile('rb').read().decode().replace('\r','').strip();err=ch.makefile_stderr('rb').read().decode();code=ch.recv_exit_status();ch.close()
 log(command=command,exit_code=code,stdout=out,stderr=err)
 if code:raise RuntimeError('board command failed; preserved rollback')
 return out
sftp=paramiko.SFTPClient.from_transport(t)
try:
 assert run('cat /proc/device-tree/serial-number').rstrip('\x00')==SERIAL
 config=json.loads(sftp.open('/opt/instrument/config.json').read());assert config['device_id']==DEVICE
 packet=dict(version=3,op='hello_query',device_id=DEVICE,host_id='stability-deploy',sequence=0,nonce=secrets.token_hex(16))
 code="import socket,json;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(2);s.sendto("+repr(json.dumps(packet).encode())+",('127.0.0.1',37020));print(s.recvfrom(4097)[0].decode())"
 hello=json.loads(run('python3 -c '+shlex.quote(code)))
 assert hello['phase']=='idle' and not hello['gate_enabled'] and not hello['audio_busy'] and not hello['paired_host_id'] and hello['metrics']['pending_count']==0
 stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());backup='/opt/instrument/backups/stability-dev-'+stamp
 run('mkdir -p '+backup+'/sounds')
 run('cp -p /opt/instrument/bin/instrument_app '+backup+'/instrument_app')
 for path in ['/opt/instrument/config.json','/opt/instrument/state/pair-v3.json','/opt/instrument/state/version','/opt/instrument/installed-version']:
  run('cp -p '+path+' '+backup+'/'+Path(path).name.replace('version','version-'+('installed' if 'installed' in path else 'state')))
 for path in (SOURCE/'sounds').glob('*.wav'):
  old='/opt/instrument/sounds/'+path.name
  run('if [ -f '+old+' ]; then cp -p '+old+' '+backup+'/sounds/'+path.name+'; fi')
 pid=run('pidof instrument_app');assert pid.isdecimal()
 kernel=run('cat /proc/sys/kernel/random/boot_id');rkipc=run('pidof rkipc')
 run('kill -TERM '+pid)
 for i in range(70):
  if run('if [ -d /proc/'+pid+' ]; then echo running; else echo stopped; fi')=='stopped':break
  time.sleep(.5)
 else:raise RuntimeError('old application still running')
 files=[(SOURCE/'instrument_app','/opt/instrument/bin/instrument_app')]+[(p,'/opt/instrument/sounds/'+p.name) for p in (SOURCE/'sounds').glob('*.wav')]
 for path,dest in files:
  expected=hashlib.sha256(path.read_bytes()).hexdigest();temp=dest+'.stability-new'
  sftp.put(str(path),temp)
  assert run('sha256sum '+temp).split()[0]==expected
  run('chmod '+('755' if dest.endswith('instrument_app') else '644')+' '+temp+' && mv '+temp+' '+dest)
 run("printf '0\\n' > "+BUTTON)
 run("nohup env INSTRUMENT_BUTTON_FILE="+BUTTON+" LD_LIBRARY_PATH=/oem/usr/lib:/usr/lib:/lib /opt/instrument/bin/instrument_app /opt/instrument/config.json </dev/null >/opt/instrument/logs/stability-"+stamp+".log 2>&1 &")
 time.sleep(2)
 new_pid=run('pidof instrument_app');assert new_pid.isdecimal()
 assert run('cat /proc/sys/kernel/random/boot_id')==kernel
 assert run('pidof rkipc')==rkipc
 result=dict(backup=backup,serial=SERIAL,device=DEVICE,kernel_boot=kernel,rkipc_pid=rkipc,original_app_pid=pid,test_app_pid=new_pid,button_file=BUTTON,source_sha256=hashlib.sha256((SOURCE/'instrument_app').read_bytes()).hexdigest(),development_version='3.3.8',transport='usb_ssh',status='test_runtime_active')
 (ROOT/'development-deploy.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result))
finally:sftp.close();t.close()
