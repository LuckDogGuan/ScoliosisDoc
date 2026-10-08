"""One named board, pinned SSH key, WSL-owned package, retained rollback evidence."""
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
import socket
import sys
import tarfile
import time

import paramiko

ROOT = Path(__file__).resolve().parent
SERIAL = '41eda5f2c5b00de1'
DEVICE = 'CAM-' + SERIAL
ADDRESS = '192.168.101.4'
PACKAGE = Path(r'\\wsl$\Luckfox-Ubuntu-22.04\home\guanjx\luckfox\Scoliosis\releases\3.3.5\instrument-v3.3.5.tar.gz')
DIGEST = 'ad6e619b4b90c1690dc2ac94c1b19a64c1424601dc8bb3c9f8711abe89d0573b'
KEY = 'SHA256:QLjOSdI3DrGRFdzX72pAcNRo4l6QPngLFHBNr6SYKgk'
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
LOG = ROOT / ('wifi-update-' + stamp + '.jsonl')
transport = None
stopped = False


def record(**row):
    row['local_time'] = datetime.now().astimezone().isoformat()
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps(row, ensure_ascii=False), flush=True)


def connect():
    t = paramiko.Transport(socket.create_connection((ADDRESS, 22), timeout=6))
    try:
        t.start_client(timeout=6)
        fp = 'SHA256:' + base64.b64encode(hashlib.sha256(t.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
        if fp != KEY:
            raise RuntimeError('Wrong SSH key; refused before authentication')
        t.auth_password('root', password)
        return t
    except BaseException:
        t.close()
        raise


def ssh(command):
    ch = transport.open_session(timeout=10)
    ch.settimeout(45)
    ch.exec_command(command)
    out = ch.makefile('rb').read().decode(errors='replace').replace('\x00', '')
    err = ch.makefile_stderr('rb').read().decode(errors='replace')
    code = ch.recv_exit_status()
    ch.close()
    record(command=command, stdout=out, stderr=err, exit_code=code)
    if code:
        raise RuntimeError('Remote operation failed; following steps refused')
    return out.strip()


def hello():
    p = dict(version=3, op='hello_query', host_id='realboard-upgrade-observer', device_id=DEVICE,
             sequence=0, nonce=secrets.token_hex(16))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(('192.168.101.2', 0))
        s.settimeout(3)
        s.sendto(json.dumps(p).encode(), (ADDRESS, 37020))
        raw, peer = s.recvfrom(8192)
    r = json.loads(raw)
    if peer != (ADDRESS, 37020) or r.get('op') != 'hello_reply' or r.get('ok') is not True or any(r.get(k) != p[k] for k in ('version', 'host_id', 'device_id', 'sequence', 'nonce')):
        raise RuntimeError('Unmatched live reply')
    record(live_state=r)
    return r


password = sys.stdin.readline().rstrip('\r\n')
try:
    blob = PACKAGE.read_bytes()
    if hashlib.sha256(blob).hexdigest() != DIGEST:
        raise RuntimeError('Package hash mismatch')
    with tarfile.open(PACKAGE) as a:
        app_hash = hashlib.sha256(a.extractfile('instrument-v3.3.5/instrument_app').read()).hexdigest()
        startup_hash = hashlib.sha256(a.extractfile('instrument-v3.3.5/deploy/RkLunch.sh').read()).hexdigest()
    transport = connect()
    if ssh('cat /proc/device-tree/serial-number') != SERIAL:
        raise RuntimeError('Wrong serial; no write')
    config = json.loads(ssh('cat /opt/instrument/config.json'))
    if config.get('device_id') != DEVICE:
        raise RuntimeError('Wrong device ID; no write')
    before = hello()
    if before.get('phase') != 'idle' or any(before.get(k) for k in ('paired_host_id', 'gate_enabled', 'capture_id', 'uploading_capture_id', 'diagnostics_active', 'audio_busy')):
        raise RuntimeError('Not idle/unpaired; no write')
    if json.loads(ssh('cat /opt/instrument/state/active-v3.json')) or ssh('find /opt/instrument/capture/writing -type f'):
        raise RuntimeError('Active capture or unfinished writing; no write')
    if ssh('sha256sum /RkLunch.sh').split()[0] != startup_hash:
        raise RuntimeError('Startup differs; manual review required')
    preserved = '/opt/instrument/config.json /opt/instrument/state/pair-v3.json /userdata/rkipc.ini /etc/wpa_supplicant.conf /userdata/wpa_supplicant.conf'
    before_hashes = ssh('sha256sum ' + preserved)
    ssh('/opt/instrument/bin/instrument_app --version; pidof instrument_app; pidof rkipc || true; df -k /opt /tmp')
    remote = '/tmp/instrument-335-wifi-' + stamp
    pkg = remote + '/instrument-v3.3.5'
    ssh('mkdir ' + remote)
    ch = transport.open_session(timeout=10)
    ch.settimeout(45)
    ch.exec_command('cat > ' + remote + '/bundle.tar.gz')
    ch.sendall(blob)
    ch.shutdown_write()
    code = ch.recv_exit_status()
    ch.close()
    if code:
        raise RuntimeError('Package transfer failed')
    if ssh('sha256sum ' + remote + '/bundle.tar.gz').split()[0] != DIGEST:
        raise RuntimeError('Remote package hash mismatch')
    ssh('set -e; cd ' + remote + '; gzip -dc bundle.tar.gz > payload.tar; tar -xf payload.tar; sh ' + pkg + '/deploy/install_bundle.sh --check')
    # Recheck immediately before stopping services; no pair/gate authorization is created.
    live = hello()
    if live.get('phase') != 'idle' or any(live.get(k) for k in ('paired_host_id', 'gate_enabled', 'capture_id', 'uploading_capture_id', 'diagnostics_active', 'audio_busy')):
        raise RuntimeError('Business started during preflight; installation refused')
    stopped = True
    ssh('set -e; kill -TERM $(pidof instrument_app); if pidof rkipc >/dev/null; then kill -TERM $(pidof rkipc); fi; n=0; while pidof instrument_app rkipc aplay >/dev/null; do n=$((n+1)); if [ "$n" -ge 35 ]; then ps; exit 2; fi; sleep 1; done; echo SERVICES_STOPPED')
    result = ssh('sh ' + pkg + '/deploy/install_bundle.sh --install --idle-confirmed')
    backup = re.search(r'RECORD=(\S+)', result).group(1)
    if ssh('cat ' + backup + '/result.txt') != 'exit_code=0':
        raise RuntimeError('Installation result failed')
    ssh('tail -n 8 ' + backup + '/install.log; sha256sum -c ' + backup + '/after-SHA256SUMS')
    if ssh('sha256sum ' + preserved) != before_hashes:
        raise RuntimeError('Preserved business/config files changed')
    if ssh('sha256sum /opt/instrument/bin/instrument_app').split()[0] != app_hash:
        raise RuntimeError('Installed binary hash mismatch')
    # Export the actual rollback and audit, never a second firmware release copy.
    ch = transport.open_session(timeout=10)
    ch.settimeout(45)
    ch.exec_command('tar -cf - -C / ' + backup.lstrip('/'))
    evidence = ch.makefile('rb').read()
    if ch.recv_exit_status():
        raise RuntimeError('Rollback evidence export failed')
    ch.close()
    (ROOT / ('rollback-audit-' + stamp + '.tar')).write_bytes(evidence)
    record(result='WIFI_INSTALL_PASS', serial=SERIAL, address=ADDRESS, version='3.3.5',
           backup=backup, package_sha256=DIGEST, app_sha256=app_hash, config_pair_wifi_camera_preserved=True)
    ssh('sync; reboot')
    transport.close()
    transport = None
    for attempt in range(30):
        time.sleep(2)
        try:
            transport = connect()
            break
        except (OSError, paramiko.SSHException):
            continue
    if transport is None:
        raise RuntimeError('Wi-Fi did not return after reboot')
    if ssh('cat /proc/device-tree/serial-number') != SERIAL:
        raise RuntimeError('Reboot identity mismatch')
    if ssh('/opt/instrument/bin/instrument_app --version') != '3.3.5':
        raise RuntimeError('Reboot version mismatch')
    if ssh('sha256sum /opt/instrument/bin/instrument_app').split()[0] != app_hash:
        raise RuntimeError('Reboot binary mismatch')
    if ssh('sha256sum ' + preserved) != before_hashes:
        raise RuntimeError('Reboot changed preserved files')
    ssh('pidof instrument_app; pidof rkipc; test -S /var/tmp/rkipc; ip -4 addr show wlan0; date; cat /etc/TZ')
    after = hello()
    if after.get('boot_id') == before.get('boot_id') or after.get('wifi_state') != 'available' or after.get('phase') != 'idle':
        raise RuntimeError('Reboot/live state failed')
    stopped = False
    record(result='WIFI_REBOOT_VERIFY_PASS', version='3.3.5', adb_used=False, live_state=after)
finally:
    if stopped and transport and transport.is_active():
        try:
            ssh('if ! pidof rkipc >/dev/null; then nohup env TZ=CST-8 LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles > /tmp/335-recovery-camera.log 2>&1 < /dev/null & sleep 2; fi; if ! pidof instrument_app >/dev/null; then nohup /opt/instrument/bin/instrument_app /opt/instrument/config.json > /tmp/335-recovery-app.log 2>&1 < /dev/null & sleep 1; fi')
        except Exception as e:
            record(recovery_error=str(e))
    if transport:
        transport.close()
    del password
