"""Refresh an idle serial-bound development binary; preserve original rollback."""
import base64,hashlib,json,os,secrets,subprocess,time,urllib.request
import paramiko
from pathlib import Path
ADB=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe'
SERIAL='3253c006806f5194'; DEVICE='CAM-000123'
BUTTON='/tmp/stability-buttons-20261013'
SOURCE=Path(r'\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\instrument_app')
def adb(*parts):
 r=subprocess.run([ADB,'-s',SERIAL,*parts],capture_output=True,check=True,timeout=45)
 return r.stdout.decode('utf-8','replace').replace('\r','').strip()
def hello():
 packet=dict(version=3,op='hello_query',device_id=DEVICE,host_id='stability-refresh',sequence=0,nonce=secrets.token_hex(16))
 body=json.dumps(dict(packet=base64.b64encode(json.dumps(packet).encode()).decode(),port=37020,wait_ms=2000)).encode()
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18085/debug/udp',data=body,headers={'Content-Type':'application/json'}),timeout=6) as r:
  return json.loads(base64.b64decode(json.load(r)['replies'][0]['packet']))
assert adb('shell','cat /proc/device-tree/serial-number').rstrip('\x00')==SERIAL
h=hello();assert h['phase']=='idle' and not h['gate_enabled'] and not h['paired_host_id'] and h['metrics']['pending_count']==0
kernel=h['system_boot_id'];pid=str(h['application_pid']);assert pid.isdecimal()
adb('shell','kill -TERM '+pid)
for _ in range(90):
 if adb('shell','test -d /proc/'+pid+' && echo running || echo stopped')=='stopped':break
 time.sleep(.25)
else:raise RuntimeError('coordinator did not stop')
dest='/opt/instrument/bin/instrument_app.stability-new'; expected=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
adb('push',str(SOURCE),dest)
assert adb('shell','sha256sum '+dest).split()[0]==expected
adb('shell','chmod 755 '+dest+' && mv '+dest+' /opt/instrument/bin/instrument_app')
adb('shell',"printf '0\\n' > "+BUTTON)
t=paramiko.Transport(('127.0.0.1',22023));t.start_client(timeout=5)
key=t.get_remote_server_key();kind={'ssh-ed25519':'ed25519','ecdsa-sha2-nistp256':'ecdsa','ssh-rsa':'rsa'}[key.get_name()]
assert base64.b64decode(adb('shell','cat /etc/ssh/ssh_host_'+kind+'_key.pub').split()[1])==key.asbytes()
t.auth_password('root',os.getenv('LUCKFOX_SSH_PASSWORD','luckfox'))
try:
 ch=t.open_session(timeout=5);ch.settimeout(5)
 ch.exec_command('nohup env INSTRUMENT_BUTTON_FILE='+BUTTON+' LD_LIBRARY_PATH=/oem/usr/lib:/usr/lib:/lib /opt/instrument/bin/instrument_app /opt/instrument/config.json </dev/null >/opt/instrument/logs/stability-refresh.log 2>&1 &')
 assert ch.recv_exit_status()==0;ch.close()
finally:t.close()
time.sleep(3)
h=hello();assert h['system_boot_id']==kernel and h['phase']=='idle'
print(json.dumps(dict(device=DEVICE,pid=h['application_pid'],boot=h['boot_id'],kernel=kernel,sha256=expected)))

