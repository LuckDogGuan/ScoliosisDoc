import subprocess,json,hashlib,tarfile,time,secrets,configparser
from pathlib import Path
from datetime import datetime
root=Path(r'D:\code\Scoliosis\Luckfox\调试\记录\usb-install-20261009')
adb=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe'
serial='3253c006806f5194'
package=Path(r'\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\releases\3.3.7\instrument-v3.3.7.tar.gz')
digest='65b9daa189517bedcb66882316662c1e724852076fb9d1b1e5a2fc4b9695748a'
log=root/'operations.jsonl'
def run(*args,timeout=60):
 r=subprocess.run([adb,'-s',serial,*args],capture_output=True,timeout=timeout)
 out=r.stdout.decode(errors='replace').replace('\x00','').replace('\r','').strip()
 with log.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=datetime.now().astimezone().isoformat(),args=args,code=r.returncode,stdout=out,stderr=r.stderr.decode(errors='replace')),ensure_ascii=False)+'\n')
 if r.returncode:raise RuntimeError(out+r.stderr.decode(errors='replace'))
 return out
def shell(cmd):return run('shell',cmd)
def hello():
 p=dict(version=3,op='hello_query',device_id='CAM-000123',host_id='flash-observer',sequence=0,nonce=secrets.token_hex(12))
 r=json.loads(shell("/tmp/deploy-hello-20261009 '"+json.dumps(p,separators=(',',':'))+"'"))
 assert r['ok'] and r['op']=='hello_reply' and all(r[k]==p[k] for k in ('device_id','host_id','nonce','sequence'))
 return r
def idle(r):
 assert r['phase']=='idle' and not any(r.get(k) for k in ('gate_enabled','capture_id','uploading_capture_id','diagnostics_active','audio_busy'))
 assert json.loads(shell('cat /opt/instrument/state/active-v3.json'))=={}
 assert not shell('ls -A /opt/instrument/capture/writing')
def ini(txt):
 c=configparser.ConfigParser(strict=False,interpolation=None);c.read_string(txt);return {s:dict(c[s]) for s in c.sections()}
assert shell('cat /proc/device-tree/serial-number')==serial
assert json.loads(shell('cat /opt/instrument/config.json'))['device_id']=='CAM-000123'
assert hashlib.sha256(package.read_bytes()).hexdigest()==digest
with tarfile.open(package) as t:
 app_hash=hashlib.sha256(t.extractfile('instrument-v3.3.7/instrument_app').read()).hexdigest()
 startup=t.extractfile('instrument-v3.3.7/deploy/RkLunch.sh').read().decode()
old_startup=shell('cat /RkLunch.sh')
(root/'RkLunch.before.sh').write_text(old_startup,encoding='utf-8')
(root/'RkLunch.package.sh').write_text(startup,encoding='utf-8')
before=hello();idle(before)
(root/'before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
preserved='/opt/instrument/config.json /opt/instrument/state/pair-v3.json /etc/wpa_supplicant.conf /userdata/wpa_supplicant.conf'
hashes=shell('sha256sum '+preserved)
camera=ini(shell('cat /userdata/rkipc.ini'))
remote='/tmp/instrument-337-usb-20261009';pkg=remote+'/instrument-v3.3.7'
shell('mkdir -p '+remote)
run('push',str(package),remote+'/bundle.tar.gz')
assert shell('sha256sum '+remote+'/bundle.tar.gz').split()[0]==digest
shell('set -e; cd '+remote+'; gzip -dc bundle.tar.gz > payload.tar; tar -xf payload.tar; sh '+pkg+'/deploy/install_bundle.sh --check')
idle(hello())
stopped=False
try:
 stopped=True
 shell('set -e; kill -TERM $(pidof instrument_app); if pidof rkipc >/dev/null; then kill -TERM $(pidof rkipc); fi; n=0; while pidof instrument_app rkipc aplay >/dev/null; do n=$((n+1)); [ "$n" -lt 40 ] || exit 2; sleep 1; done; echo SERVICES_STOPPED')
 result=shell('sh '+pkg+'/deploy/install_bundle.sh --install --idle-confirmed --replace-startup')
 backup=result.split('RECORD=',1)[1].splitlines()[0]
 assert shell('cat '+backup+'/result.txt')=='exit_code=0'
 shell('sha256sum -c '+backup+'/after-SHA256SUMS')
 assert shell('sha256sum '+preserved)==hashes
 assert shell('sha256sum /opt/instrument/bin/instrument_app').split()[0]==app_hash
 shell('cp /userdata/rkipc.ini '+backup+'/rkipc-before-reboot.ini')
 run('pull',backup,str(root/'board-backup'))
 (root/'installation.json').write_text(json.dumps(dict(serial=serial,device_id='CAM-000123',version='3.3.7',backup=backup,package_sha256=digest,app_sha256=app_hash),indent=2),encoding='utf-8')
 print('INSTALL_OK; rebooting',flush=True)
 shell('sync; reboot')
 stopped=False
 for i in range(45):
  time.sleep(2)
  try:
   if shell('cat /proc/device-tree/serial-number')==serial:break
  except (RuntimeError,subprocess.TimeoutExpired):pass
 else:raise RuntimeError('ADB did not return')
 for i in range(20):
  try:
   if shell('pidof instrument_app') and shell('pidof rkipc'):break
  except RuntimeError:pass
  time.sleep(2)
 assert shell('/opt/instrument/bin/instrument_app --version')=='3.3.7'
 assert shell('sha256sum /opt/instrument/bin/instrument_app').split()[0]==app_hash
 assert shell('sha256sum '+preserved)==hashes
 shell('pidof instrument_app; pidof rkipc; test -S /var/tmp/rkipc; sha256sum -c '+backup+'/after-SHA256SUMS')
 run('push',r'\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\tools\deploy-check-20261009\hello','/tmp/deploy-hello-20261009')
 shell('chmod 755 /tmp/deploy-hello-20261009')
 after=hello();idle(after);assert after['boot_id']!=before['boot_id']
 expected=dict((s,dict(v)) for s,v in camera.items())
 actual=ini(shell('cat /userdata/rkipc.ini'))
 changes=[(s,k,camera.get(s,{}).get(k),v) for s,items in actual.items() for k,v in items.items() if camera.get(s,{}).get(k)!=v]
 allowed={'enable_jpeg':'1','enable_cycle_snapshot':'0','jpeg_qfactor':'95','jpeg_buffer_size':'4194304'}
 assert all(k in allowed and v==allowed[k] for s,k,o,v in changes),changes
 assert all(s in actual and all(k in actual[s] for k in items) for s,items in camera.items())
 (root/'after.json').write_text(json.dumps(dict(result='INSTALL_REBOOT_PASS',state=after,camera_expected_changes=changes,config_pair_wifi_preserved=True),indent=2),encoding='utf-8')
 print('INSTALL_REBOOT_PASS 3.3.7',flush=True)
finally:
 if stopped:
  try:shell('if ! pidof rkipc >/dev/null; then nohup env TZ=CST-8 LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles >/tmp/337-recovery-camera.log 2>&1 </dev/null & sleep 2; fi; if ! pidof instrument_app >/dev/null; then nohup /opt/instrument/bin/instrument_app /opt/instrument/config.json >/tmp/337-recovery-app.log 2>&1 </dev/null & sleep 1; fi')
  except Exception as e:print('RECOVERY_ERROR',str(e),flush=True)
