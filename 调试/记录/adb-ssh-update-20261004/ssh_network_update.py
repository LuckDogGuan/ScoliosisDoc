"""Independent LAN SSH deployment. Locks board serial and device ID before any write."""
import argparse
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

import paramiko

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--address', required=True)
parser.add_argument('--verify-only', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parent
serial = '41eda5f2c5b00de1'
device_id = 'CAM-' + serial
release = 'instrument-v3.3.0-20261004-minmax-volume20-bundle2'
bundle = root / (release + '.tar.gz')
expected = 'b4cf975d1c3a4076f42ae366c578d4f14727e7ea82d20ee3fda8b22740e94b71'
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == expected
with tarfile.open(bundle) as archive:
    app_hash = hashlib.sha256(archive.extractfile(release + '/instrument_app').read()).hexdigest()
    defaults = json.load(archive.extractfile(release + '/config.example.json'))
assert defaults['audio']['volume'] == 20
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
log = root / ('lan-ssh-' + stamp + '.jsonl')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
password = sys.stdin.readline().rstrip('\r\n')


def record(**row):
    row['local_time'] = datetime.now().astimezone().isoformat()
    with log.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps(row, ensure_ascii=False), flush=True)


def ssh(command):
    _, stdout, stderr = client.exec_command(command, timeout=45)
    output = stdout.read().decode(errors='replace')
    error = stderr.read().decode(errors='replace')
    code = stdout.channel.recv_exit_status()
    record(command=command, stdout=output, stderr=error, exit_code=code)
    if code:
        raise RuntimeError('SSH operation failed; no following operations allowed')
    return output


try:
    # No ADB executable, localhost, port forwarding or proxy used anywhere in this runner.
    client.connect(args.address, port=22, username='root', password=password, timeout=6,
                   auth_timeout=6, banner_timeout=6, look_for_keys=False, allow_agent=False)
    key = client.get_transport().get_remote_server_key()
    key_sha = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
    if key_sha != (root / 'board-hostkey.txt').read_text().strip():
        raise RuntimeError('Unrecognized host key; no write performed')
    found = ssh('cat /proc/device-tree/serial-number').strip('\x00\r\n')
    if found != serial:
        raise RuntimeError('WRONG DEVICE: serial mismatch; no write performed')
    config = json.loads(ssh('cat /opt/instrument/config.json'))
    if config['device_id'] != device_id:
        raise RuntimeError('WRONG DEVICE: application identity mismatch; no write performed')
    record(transport='independent-LAN-SSH', address=args.address, serial=found,
           device_id=config['device_id'], host_key_sha256=key_sha, identity_locked=True)
    if not args.verify_only:
        query = dict(version=3, op='hello_query', device_id=device_id,
                     host_id='ssh-upgrade-observer', sequence=0, nonce=secrets.token_hex(16))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.settimeout(2)
            udp.sendto(json.dumps(query).encode(), (args.address, 37020))
            raw, peer = udp.recvfrom(4096)
        state = json.loads(raw)
        if peer != (args.address, 37020) or any(state.get(k) != query[k] for k in
                ('version', 'device_id', 'host_id', 'sequence', 'nonce')):
            raise RuntimeError('Unmatched live device state; no write performed')
        if (state.get('phase') != 'idle' or state.get('gate_enabled') or
                state.get('capture_id') or state.get('uploading_capture_id') or state.get('paired_host_id')):
            raise RuntimeError('Device is busy or paired; stop business before updating')
        record(live_state_checked=True, phase=state['phase'], gate_enabled=False)
        before_hash = ssh('sha256sum /opt/instrument/config.json').split()[0]
        remote = '/tmp/scoliosis-lan-' + stamp
        pkg = remote + '/' + release
        ssh('mkdir ' + remote)
        _, stdout, stderr = client.exec_command("cat > '" + remote + '/' + release + ".tar.gz'", timeout=45)
        stdout.channel.sendall(bundle.read_bytes())
        stdout.channel.shutdown_write()
        error = stderr.read().decode(errors='replace')
        code = stdout.channel.recv_exit_status()
        record(transport='SSH-file-transfer', bytes=bundle.stat().st_size, exit_code=code, stderr=error)
        assert code == 0
        outer = ssh("sha256sum '" + remote + '/' + release + ".tar.gz'").split()[0]
        assert outer == expected
        ssh(f"gzip -dc '{remote}/{release}.tar.gz' > '{remote}/payload.tar' && tar -xf '{remote}/payload.tar' -C '{remote}' && sh '{pkg}/deploy/install_bundle.sh' --check")
        ssh("if [ -d /opt/instrument/capture/writing ]; then test -z \"$(ls -A /opt/instrument/capture/writing)\" || exit 2; fi; if pidof instrument_app >/dev/null; then killall -TERM instrument_app; fi; if pidof rkipc >/dev/null; then killall -TERM rkipc; fi; sleep 4; for p in instrument_app rkipc aplay; do if pidof $p >/dev/null; then exit 2; fi; done")
        output = ssh(f"sh '{pkg}/deploy/install_bundle.sh' --install --idle-confirmed")
        backup = re.search(r'RECORD=(\S+)', output).group(1)
        output = ssh(f"cat '{backup}/result.txt'; tail -n 5 '{backup}/install.log'; sha256sum -c '{backup}/after-SHA256SUMS'")
        assert 'exit_code=0' in output and 'INSTALL_OK' in output
        assert ssh('sha256sum /opt/instrument/config.json').split()[0] == before_hash
        assert ssh('sha256sum /opt/instrument/bin/instrument_app').split()[0] == app_hash
        record(result='LAN_SSH_INSTALL_PASS', backup=backup, config_preserved=True)
        ssh('sync; reboot')
    else:
        assert ssh('/opt/instrument/bin/instrument_app --version').strip() == '3.3.0'
        assert ssh('sha256sum /opt/instrument/bin/instrument_app').split()[0] == app_hash
        pid = ssh('pidof instrument_app').strip()
        mixer = ssh("amixer -c 0 cget 'name=DAC LINEOUT Volume'")
        assert ': values=20' in mixer and config['audio']['volume'] == 20
        record(result='LAN_SSH_REBOOT_VERIFY_PASS', pid=pid, volume=20)
finally:
    del password
    client.close()
