"""One-board ADB install / SSH reinstall evidence runner, using the existing release."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

import paramiko

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('phase', choices=['adb-install', 'ssh-update', 'verify'])
args = parser.parse_args()
root = Path(__file__).resolve().parent
adb = r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe'
serial = '41eda5f2c5b00de1'
release = 'instrument-v3.3.0-20261002-results-bundle1'
bundle = root.parent / 'single-bundle-20261002' / (release + '.tar.gz')
expected = 'd6eff1c88504d12a951c40b30adea719d9deb1dac714de9a9ee1cea996fbbdbf'
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == expected
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
log = root / (args.phase + '-' + stamp + '.jsonl')


def record(**row):
    row['local_time'] = datetime.now().astimezone().isoformat()
    with log.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps(row, ensure_ascii=False), flush=True)


def adb_call(*command, check=True, timeout=40):
    invocation = list(command)
    if command[0] == 'shell':
        invocation = ['shell', 'sh -c ' + shlex.quote(command[1]) + '; rc=$?; echo __REMOTE_EXIT=$rc']
    result = subprocess.run([adb, '-s', serial, *invocation], capture_output=True, timeout=timeout)
    output = result.stdout.decode('utf-8', errors='replace').replace('\r', '')
    record(transport='adb', command=list(command), exit_code=result.returncode,
           stdout=output, stderr=result.stderr.decode('utf-8', errors='replace'))
    remote_code = re.search(r'__REMOTE_EXIT=(\d+)', output)
    if check and (result.returncode or (command[0] == 'shell' and (not remote_code or int(remote_code.group(1)) != 0))):
        raise RuntimeError('ADB operation failed')
    return output


remote = '/tmp/scoliosis-' + args.phase + '-' + stamp
pkg = remote + '/' + release
integrity = f"sha256sum '{remote}/{release}.tar.gz' && gzip -dc '{remote}/{release}.tar.gz' > '{remote}/payload.tar' && tar -xf '{remote}/payload.tar' -C '{remote}' && sh '{pkg}/deploy/install_bundle.sh' --check"
snapshot = "date -u; /opt/instrument/bin/instrument_app --version; cat /opt/instrument/installed-version; sha256sum /opt/instrument/bin/instrument_app /opt/instrument/bin/luckfox_mux_adapter.so /opt/instrument/config.json /RkLunch.sh; pidof instrument_app; pidof rkipc; cat /proc/device-tree/serial-number; ip -4 addr show; ls -l /opt/instrument; find /opt/instrument -name '*.log'; dmesg | tail -n 25"

if args.phase == 'adb-install':
    identity = adb_call('shell', 'cat /proc/device-tree/model; cat /proc/device-tree/serial-number; test ! -e /opt/instrument/config.json')
    assert 'Luckfox Pico Zero' in identity and serial in identity
    adb_call('shell', f"mkdir '{remote}'")
    adb_call('push', str(bundle), remote + '/' + release + '.tar.gz')
    output = adb_call('shell', integrity)
    assert expected in output and 'CHECK_OK' in output
    # Fresh board only: unique serial-derived identity, USB test endpoint, no Wi-Fi changes.
    config = dict(device_id='CAM-' + serial, wifi_ssid='__USB_DEPLOYMENT_TEST__',
                  pc_base_url='http://172.32.0.100:8080', audio=dict(volume=10),
                  capture=dict(width=1280, height=1080, fps_fraction='60/2', codec='h265',
                               container='mp4', bitrate_kbps=4000, duration_ms=10000),
                  battery=dict(present=False))
    (root / 'initial-config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    adb_call('shell', f"mkdir -p /userdata/deploy-records/{stamp}; cp /RkLunch.sh /userdata/deploy-records/{stamp}/RkLunch.before.sh; cp /userdata/rkipc.ini /userdata/deploy-records/{stamp}/rkipc.before.ini; mkdir -p /opt/instrument; test ! -e /opt/instrument/config.json")
    adb_call('push', str(root / 'initial-config.json'), '/opt/instrument/config.json')
    adb_call('shell', 'chmod 600 /opt/instrument/config.json')
    output = adb_call('shell', f"sh '{pkg}/deploy/install_bundle.sh' --install --idle-confirmed --replace-startup")
    backup = re.search(r'RECORD=(\S+)', output).group(1)
    output = adb_call('shell', f"cat '{backup}/result.txt'; tail -n 5 '{backup}/install.log'; sha256sum -c '{backup}/after-SHA256SUMS'")
    assert 'exit_code=0' in output and 'INSTALL_OK' in output
    record(install_backup=backup, result='ADB_INSTALL_PASS')
    adb_call('shell', 'sync; reboot', check=False)
else:
    port = int(adb_call('forward', 'tcp:0', 'tcp:22').strip())
    client = paramiko.SSHClient()
    keys = root / 'known_hosts'
    if keys.exists():
        client.load_host_keys(str(keys))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    password = sys.stdin.readline().rstrip('\r\n')
    try:
        client.connect('127.0.0.1', port=port, username='root', password=password,
                       look_for_keys=False, allow_agent=False, timeout=8, auth_timeout=8)
        key = client.get_transport().get_remote_server_key()
        key_sha = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        pinned = root / 'board-hostkey.txt'
        if pinned.exists():
            assert pinned.read_text().strip() == key_sha, 'Board host key changed'
        else:
            pinned.write_text(key_sha + '\n')
        client.save_host_keys(str(keys))
        record(transport='ssh-over-adb-usb', authenticated=True, port=port, host_key_sha256=key_sha)

        def ssh(command, check=True):
            _, stdout, stderr = client.exec_command(command, timeout=45)
            output = stdout.read().decode(errors='replace')
            error = stderr.read().decode(errors='replace')
            code = stdout.channel.recv_exit_status()
            record(transport='ssh', command=command, stdout=output, stderr=error, exit_code=code)
            if check and code:
                raise RuntimeError('SSH command failed')
            return output

        assert serial in ssh('cat /proc/device-tree/serial-number')
        ssh(snapshot)
        if args.phase == 'ssh-update':
            ssh(f"mkdir '{remote}'")
            # This Buildroot lacks SFTP: transmit one archive via SSH exec stdin.
            _, stdout, stderr = client.exec_command(f"cat > '{remote}/{release}.tar.gz'", timeout=45)
            channel = stdout.channel
            channel.sendall(bundle.read_bytes())
            channel.shutdown_write()
            error = stderr.read().decode(errors='replace')
            code = channel.recv_exit_status()
            record(transport='ssh-file-transfer', bytes=bundle.stat().st_size, sha256=expected, exit_code=code, stderr=error)
            assert code == 0
            output = ssh(integrity)
            assert expected in output and 'CHECK_OK' in output
            preserved = ssh("sha256sum /opt/instrument/config.json; find /opt/instrument/state /opt/instrument/capture /opt/instrument/events -type f -exec sha256sum {} \\; 2>/dev/null", check=False)
            ssh("if [ -d /opt/instrument/capture/writing ]; then test -z \"$(ls -A /opt/instrument/capture/writing)\" || exit 2; fi; if pidof instrument_app >/dev/null; then killall -TERM instrument_app; fi; if pidof rkipc >/dev/null; then killall -TERM rkipc; fi; sleep 3; for p in instrument_app rkipc aplay; do if pidof $p >/dev/null; then exit 2; fi; done")
            output = ssh(f"sh '{pkg}/deploy/install_bundle.sh' --install --idle-confirmed")
            backup = re.search(r'RECORD=(\S+)', output).group(1)
            output = ssh(f"cat '{backup}/result.txt'; tail -n 5 '{backup}/install.log'; sha256sum -c '{backup}/after-SHA256SUMS'")
            assert 'exit_code=0' in output and 'INSTALL_OK' in output
            record(install_backup=backup, result='SSH_REINSTALL_PASS', preservation_before=preserved)
            try:
                ssh('sync; reboot', check=False)
            except (EOFError, paramiko.SSHException):
                record(result='reboot disconnected SSH; verify next')
    finally:
        del password
        client.close()
        adb_call('forward', '--remove', 'tcp:' + str(port), check=False)
