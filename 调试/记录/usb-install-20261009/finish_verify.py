from pathlib import Path
p=Path(r'D:\code\Scoliosis\Luckfox\调试\记录\usb-install-20261009\install.py')
s=p.read_text(encoding='utf-8-sig')
exec(s.split("assert shell('cat /proc/device-tree/serial-number')==serial",1)[0])
backup='/opt/instrument/backups/bundle-20261009T075447Z-1626'
rows=[json.loads(x) for x in log.read_text(encoding='utf-8').splitlines()]
hashes=next(r['stdout'] for r in rows if r['args']==['shell','sha256sum '+preserved]) if 'preserved' in globals() else None
preserved='/opt/instrument/config.json /opt/instrument/state/pair-v3.json /etc/wpa_supplicant.conf /userdata/wpa_supplicant.conf'
hashes=next(r['stdout'] for r in rows if r['args']==['shell','sha256sum '+preserved])
before=json.loads((root/'before.json').read_text())
camera=ini(next(r['stdout'] for r in rows if r['args']==['shell','cat /userdata/rkipc.ini']))
with tarfile.open(package) as t:app_hash=hashlib.sha256(t.extractfile('instrument-v3.3.7/instrument_app').read()).hexdigest()
assert shell('cat /proc/device-tree/serial-number')==serial
assert shell('cat '+backup+'/result.txt')=='exit_code=0'
b=Path(r'D:\code\Scoliosis\Luckfox\validation\usb-install-20261009\rollback-audit.tar').read_bytes()
(root/'rollback-audit.tar').write_bytes(b)
with tarfile.open(root/'rollback-audit.tar') as t:assert any(x.name.endswith('rollback-files.tar') for x in t.getmembers())
(root/'installation.json').write_text(json.dumps(dict(serial=serial,device_id='CAM-000123',version='3.3.7',backup=backup,package_sha256=digest,app_sha256=app_hash,backup_sha256=hashlib.sha256(b).hexdigest()),indent=2),encoding='utf-8')
assert shell('sha256sum '+preserved)==hashes
idle(hello())
print('BACKUP_EXPORTED; REBOOTING',flush=True)
shell('sync; reboot')
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
shell('set -e; pidof instrument_app; pidof rkipc; test -S /var/tmp/rkipc; sha256sum -c '+backup+'/after-SHA256SUMS')
run('push',r'\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\tools\deploy-check-20261009\hello','/tmp/deploy-hello-20261009')
shell('chmod 755 /tmp/deploy-hello-20261009')
after=hello();idle(after);assert after['boot_id']!=before['boot_id']
actual=ini(shell('cat /userdata/rkipc.ini'))
changes=[(s,k,camera.get(s,{}).get(k),v) for s,items in actual.items() for k,v in items.items() if camera.get(s,{}).get(k)!=v]
allowed={'enable_jpeg':'1','enable_cycle_snapshot':'0','jpeg_qfactor':'95','jpeg_buffer_size':'4194304'}
assert all(k in allowed and v==allowed[k] for s,k,o,v in changes),changes
assert all(s in actual and all(k in actual[s] for k in items) for s,items in camera.items())
(root/'after.json').write_text(json.dumps(dict(result='INSTALL_REBOOT_PASS',state=after,camera_expected_changes=changes,config_pair_wifi_preserved=True),indent=2),encoding='utf-8')
print('INSTALL_REBOOT_PASS 3.3.7',flush=True)
