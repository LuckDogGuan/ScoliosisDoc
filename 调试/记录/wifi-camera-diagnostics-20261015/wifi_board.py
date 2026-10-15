"""Pinned Wi-Fi maintenance for the camera path repair; never changes pairing."""
from pathlib import Path
import argparse, base64, configparser, difflib, hashlib, json, os, shlex, socket, sys, tarfile, time
import paramiko
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
DEVICE='CAM-211ec7045815bf02'
SAVED=json.loads((PROJECT/'调试/工具/一键烧录/wifi-devices.json').read_text(encoding='utf-8-sig'))[DEVICE]
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['inspect','install','shell','buttons','test-mode','normal','reboot'])
parser.add_argument('value',nargs='?')
args=parser.parse_args()
t=paramiko.Transport(socket.create_connection((SAVED['address'],22),5));t.start_client(timeout=5)
key='SHA256:'+base64.b64encode(hashlib.sha256(t.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
assert key==SAVED['host_key'],'SSH fingerprint mismatch'
t.auth_password('root',os.environ.get('LUCKFOX_SSH_PASSWORD','luckfox'))
def read(cmd,timeout=40):
    ch=t.open_session(timeout=6);ch.settimeout(timeout);ch.exec_command(cmd)
    out=ch.makefile('rb').read().decode(errors='replace').replace('\x00','')
    error=ch.makefile_stderr('rb').read().decode(errors='replace')
    rc=ch.recv_exit_status();ch.close()
    if rc:raise RuntimeError(f'remote rc={rc}: {out[-1500:]} {error[-1000:]}')
    return out.strip()
assert read('cat /proc/device-tree/serial-number')==SAVED['serial']
assert json.loads(read('cat /opt/instrument/config.json'))['device_id']==DEVICE
def hello():
    nonce=os.urandom(16).hex()
    packet=dict(version=3,op='hello_query',host_id='camera-maintenance-readonly',device_id=DEVICE,sequence=0,nonce=nonce)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
        udp.settimeout(3);udp.sendto(json.dumps(packet).encode(),(SAVED['address'],37020))
        while True:
            data,peer=udp.recvfrom(4096);r=json.loads(data)
            if peer[0]==SAVED['address'] and r.get('nonce')==nonce:return r
def idle():
    r=hello()
    assert r.get('phase')=='idle' and not any(r.get(k) for k in ('gate_enabled','uploading_capture_id','diagnostics_active','audio_busy')),r
    assert json.loads(read('cat /opt/instrument/state/active-v3.json'))=={}
    assert not read('find /opt/instrument/capture/writing -type f')
    return r
def log(name,value):
    (ROOT/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(value,ensure_ascii=True),flush=True)
try:
    if args.action=='inspect':
        r=hello()
        details=dict(identity=DEVICE,address=SAVED['address'],host_key=key,state=r,
          installed=read('cat /opt/instrument/installed-version; cat /opt/instrument/installed-build.txt'),
          paths=read('ls -ld /video0 /userdata/video0; ls -l /userdata/video0/*.mp4; df -k / /userdata'),
          processes=read('ps | grep -E "instrument_app|rkipc" | head -12'))
        remote_startup=read('cat /RkLunch.sh')+'\n'
        source=Path(r'\\wsl.localhost\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\deploy\RkLunch.sh').read_text()
        details['startup_diff']='\n'.join(difflib.unified_diff(remote_startup.splitlines(),source.splitlines(),fromfile='board',tofile='reviewed-source'))
        log('before',details)
    elif args.action=='shell':
        print(read(args.value),flush=True)
    elif args.action=='buttons':
        value=int(args.value);assert value in (0,1,2,4,5)
        print(read(f"printf '%s\\n' {value} >/tmp/wifi-camera-buttons-20261015"),flush=True)
    elif args.action in ('test-mode','normal'):
        idle();read('kill -TERM $(pidof instrument_app); n=0; while pidof instrument_app >/dev/null; do n=$((n+1)); [ "$n" -lt 20 ] || exit 2; sleep 1; done')
        env='INSTRUMENT_BUTTON_FILE=/tmp/wifi-camera-buttons-20261015 ' if args.action=='test-mode' else ''
        if env:read("printf '0\\n' >/tmp/wifi-camera-buttons-20261015")
        print(read('nohup env '+env+'/opt/instrument/bin/instrument_app /opt/instrument/config.json >/tmp/wifi-camera-app.log 2>&1 </dev/null & sleep 2; pidof instrument_app'))
    elif args.action=='install':
        state=idle()
        package=Path(args.value);blob=package.read_bytes();digest=hashlib.sha256(blob).hexdigest()
        with tarfile.open(package) as archive:
            names=archive.getnames();prefix=next(n.rsplit('/',1)[0] for n in names if n.endswith('/VERSION'))
            version=archive.extractfile(prefix+'/VERSION').read().decode().strip()
            app_hash=hashlib.sha256(archive.extractfile(prefix+'/instrument_app').read()).hexdigest()
        assert version=='3.3.13'
        stamp=time.strftime('%Y%m%dT%H%M%S',time.gmtime())
        backup='/opt/instrument/backups/wifi-camera-'+stamp
        read('mkdir -m 700 '+backup+'; cp /userdata/rkipc.ini '+backup+'/rkipc-before.ini; cp /RkLunch.sh '+backup+'/RkLunch-before.sh; sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json /etc/wpa_supplicant.conf /userdata/wpa_supplicant.conf >'+backup+'/preserved.sha256')
        sftp=t.open_sftp_client()
        with sftp.open('/opt/instrument/state/runtime.jsonl','rb') as f:
            events=[]
            for line in f:
                try:
                    row=json.loads(line)
                    if row.get('event') in ('diagnostics_camera','diagnostics_frame','capture_completed','record_rpc_start_return','record_rpc_stop_return'):events.append(row)
                except (ValueError,UnicodeDecodeError):pass
        (ROOT/'before-camera-events.json').write_text(json.dumps(events,indent=2),encoding='utf-8')
        remote='/tmp/wifi-camera-'+stamp;read('mkdir '+remote)
        with sftp.open(remote+'/bundle.tar.gz','wb') as f:f.write(blob)
        sftp.close()
        assert read('sha256sum '+remote+'/bundle.tar.gz').split()[0]==digest
        read('cd '+remote+'; gzip -dc bundle.tar.gz >payload.tar; tar -xf payload.tar; sh '+prefix+'/deploy/install_bundle.sh --check')
        idle()
        read('kill -TERM $(pidof instrument_app); if pidof rkipc >/dev/null; then kill -TERM $(pidof rkipc); fi; n=0; while pidof instrument_app rkipc aplay >/dev/null; do n=$((n+1)); [ "$n" -lt 35 ] || exit 2; sleep 1; done',timeout=45)
        output=read('sh '+remote+'/'+prefix+'/deploy/install_bundle.sh --install --idle-confirmed --replace-startup')
        read("sed -i 's|^mount_path[[:space:]]*=.*|mount_path = /|' /userdata/rkipc.ini; mkdir -p /video0 /video1 /video2; sha256sum -c "+backup+'/preserved.sha256')
        assert read('sha256sum /opt/instrument/bin/instrument_app').split()[0]==app_hash
        log('install',dict(result='installed',version=version,device=DEVICE,address=SAVED['address'],
            package_sha256=digest,app_sha256=app_hash,backup=backup,installer_output=output,adb_used=False))
        print(read('nohup env TZ=CST-8 LD_LIBRARY_PATH=/oem/usr/lib:/usr/lib:/lib LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles >/tmp/wifi-camera-rkipc.log 2>&1 </dev/null & sleep 3; nohup /opt/instrument/bin/instrument_app /opt/instrument/config.json >/tmp/wifi-camera-app.log 2>&1 </dev/null & sleep 2; pidof rkipc instrument_app'))
    elif args.action=='reboot':
        idle()
        try:read('sync; reboot',timeout=8)
        except (OSError,EOFError,paramiko.SSHException):pass
finally:
    t.close()
