"""Identity/idle-guarded reversible installation on the explicitly named ADB board."""
import hashlib, json, secrets, socket, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERIAL = '41eda5f2c5b00de1'
DEVICE = 'CAM-' + SERIAL
ADDRESS = '192.168.101.4'
BUNDLE = ROOT.parents[2] / 'releases/3.3.4/instrument-v3.3.4.tar.gz'

def adb(*args):
    return subprocess.check_output(['adb', '-s', SERIAL, *args], timeout=45).decode().replace('\x00', '').replace('\r', '').strip()

def shell(command):
    return adb('shell', command)

def hello():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        nonce = secrets.token_hex(8)
        sock.sendto(json.dumps(dict(version=3, op='hello_query', device_id=DEVICE,
                                   host_id='read-only', sequence=1, nonce=nonce)).encode(), (ADDRESS, 37020))
        while True:
            reply = json.loads(sock.recv(4096))
            if reply.get('nonce') == nonce:
                assert reply['device_id'] == DEVICE
                return reply

assert shell('cat /proc/device-tree/serial-number') == SERIAL
config = json.loads(shell('cat /opt/instrument/config.json'))
assert config['device_id'] == DEVICE
before = hello()
assert before['phase'] == 'idle' and not before['gate_enabled']
assert not before['diagnostics_active'] and not before['uploading_capture_id'] and not before['audio_busy']
assert json.loads(shell('cat /opt/instrument/state/active-v3.json')) == {}
assert not shell('find /opt/instrument/capture/writing -type f')
assert shell('sha256sum /RkLunch.sh').split()[0] == 'aa436305bfa8fd5c68b72e38d7f5e4b4422ec8a1b5443a418046f1757493fc57'
before_hashes = shell('sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json')
(ROOT / 'before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
digest = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
assert digest == 'a19337728116c1f9da408feb2ed04d9e7ec3757c150e8330b63b8f6f7eb38462'
shell('mkdir -p /tmp/instrument-334-fixes')
adb('push', str(BUNDLE), '/tmp/instrument-334-fixes/bundle.tar.gz')
assert shell('sha256sum /tmp/instrument-334-fixes/bundle.tar.gz').split()[0] == digest
shell('set -e; cd /tmp/instrument-334-fixes; gzip -dc bundle.tar.gz > payload.tar; tar -xf payload.tar; sh instrument-v3.3.4/deploy/install_bundle.sh --check')
backup = '/opt/instrument/backups/capture-fixes-20261007-' + str(int(time.time()))
shell('mkdir -p ' + backup + '; cp /userdata/rkipc.ini ' + backup + '/rkipc.before.ini; sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json > ' + backup + '/business.before.sha256')
(ROOT / 'device-backup.txt').write_text(backup + '\n', encoding='utf-8')
print('IDENTITY_AND_IDLE_OK; backup=' + backup, flush=True)

stopped = False
try:
    shell('kill -TERM $(pidof instrument_app)')
    stopped = True
    for _ in range(100):
        if not shell('pidof instrument_app || true'): break
        time.sleep(.1)
    else: raise RuntimeError('instrument_app did not stop')
    shell('kill -TERM $(pidof rkipc)')
    for _ in range(100):
        if not shell('pidof rkipc || true'): break
        time.sleep(.1)
    else: raise RuntimeError('rkipc did not stop')
    output = shell('sh /tmp/instrument-334-fixes/instrument-v3.3.4/deploy/install_bundle.sh --install --idle-confirmed --replace-startup')
    (ROOT / 'install.txt').write_text(output + '\n', encoding='utf-8')
    assert 'RECORD=' in output
    record = output.split('RECORD=', 1)[1].splitlines()[0]
    assert shell('cat ' + record + '/result.txt') == 'exit_code=0'
    (ROOT / 'install-device-log.txt').write_text(shell('cat ' + record + '/install.log'), encoding='utf-8')
    shell("sed -i 's/^jpeg_qfactor[[:space:]]*=.*/jpeg_qfactor = 95/; s/^jpeg_buffer_size[[:space:]]*=.*/jpeg_buffer_size = 4194304/' /userdata/rkipc.ini")
    shell('cp /userdata/rkipc.ini ' + backup + '/rkipc.after.ini')
    shell('nohup env TZ=CST-8 LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles > ' + backup + '/rkipc.log 2>&1 < /dev/null & sleep 1')
    time.sleep(3)
    assert shell('pidof rkipc')
    assert shell('test -S /var/tmp/rkipc && echo RPC_OK') == 'RPC_OK'
    shell('nohup /opt/instrument/bin/instrument_app /opt/instrument/config.json > ' + backup + '/app.log 2>&1 < /dev/null & sleep 1')
    time.sleep(1)
    assert shell('/opt/instrument/bin/instrument_app --version') == '3.3.4'
    assert shell('sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json') == before_hashes
    after = hello()
    assert 'backlight_brightness' in after['capabilities']
    assert after['paired_host_id'] == before['paired_host_id']
    (ROOT / 'after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
    (ROOT / 'timezone-camera-after.txt').write_text(shell("date; cat /etc/TZ; grep -A7 '^\\[video.jpeg\\]' /userdata/rkipc.ini; cat /proc/$(pidof rkipc)/environ | tr '\\000' '\\n' | grep '^TZ='"), encoding='utf-8')
    stopped = False
    print('INSTALL_AND_STARTUP_OK 3.3.4; config/pair hashes unchanged', flush=True)
finally:
    if stopped:
        # Preserve failure evidence and restart the available installed services.
        shell('if ! pidof rkipc >/dev/null; then nohup env TZ=CST-8 LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles > ' + backup + '/recovery-camera.log 2>&1 < /dev/null & sleep 1; fi')
        shell('if ! pidof instrument_app >/dev/null; then nohup /opt/instrument/bin/instrument_app /opt/instrument/config.json > ' + backup + '/recovery-app.log 2>&1 < /dev/null & sleep 1; fi')
