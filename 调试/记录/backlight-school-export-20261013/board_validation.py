"""Identity-bound isolated capture validation; production configuration stays intact."""
import argparse
import hashlib
import json
import pathlib
import shlex
import socket
import subprocess
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
ADB = r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe'
SERIAL = '41eda5f2c5b00de1'
DEVICE = 'CAM-' + SERIAL
ADDRESS = '192.168.101.4'
ROOT = '/userdata/backlight-validation-20261013'
BUTTONS = '/tmp/stability-buttons-backlight-20261013'


def adb(*args, timeout=40):
    return subprocess.check_output([ADB, '-s', SERIAL, *args], timeout=timeout).decode('utf-8', errors='replace').strip()


def shell(command, timeout=40):
    text = adb('shell', 'sh -c ' + shlex.quote(command) + "; result=$?; printf '\\n__RESULT__=%s' \"$result\"", timeout=timeout)
    body, marker, code = text.rpartition('__RESULT__=')
    if not marker or code != '0':
        raise RuntimeError(body or text)
    return body.strip()


def query():
    packet = dict(version=3, op='hello_query', host_id='backlight-validation', device_id=DEVICE,
                  sequence=0, nonce=uuid.uuid4().hex)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        sock.sendto(json.dumps(packet).encode(), (ADDRESS, 37020))
        value = json.loads(sock.recv(8192))
    assert all(value.get(k) == packet[k] for k in ['device_id', 'host_id', 'nonce', 'sequence']), 'Query identity mismatch'
    return value


def hashes():
    names = ['/opt/instrument/config.json', '/opt/instrument/state/pair-v3.json',
             '/opt/instrument/state/backlight.json', '/opt/instrument/bin/instrument_app']
    return {name: shell('sha256sum ' + shlex.quote(name)).split()[0] for name in names}


def stop_owned(expected_prefix):
    state = query()
    assert state['phase'] == 'idle' and not state['gate_enabled'] and not state['uploading_capture_id'], 'Board busy'
    pid = str(state['application_pid'])
    assert pid.isdigit()
    command = shell('cat /proc/' + pid + '/cmdline').replace('\0', ' ')
    assert command.startswith(expected_prefix), 'Wrong process: refuse stop'
    shell('kill -TERM ' + pid)
    for _ in range(100):
        if shell('if [ -d /proc/' + pid + ' ]; then echo running; fi') != 'running':
            return
        time.sleep(.1)
    raise RuntimeError('Owned process did not stop')


def setup():
    assert shell('cat /proc/device-tree/serial-number').rstrip('\0') == SERIAL
    assert shell('/opt/instrument/bin/instrument_app --version') == '3.3.11'
    before = query()
    assert not before['diagnostics_active'] and not before['audio_busy'] and not before['camera_fault']
    snapshot = dict(serial=SERIAL, device_id=DEVICE, before=before, preserved=hashes(), root=ROOT, buttons=BUTTONS)
    (HERE / 'board-before-test.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    config = json.loads(shell('cat /opt/instrument/config.json'))
    config['audio']['volume'] = 10
    config['pc_base_url'] = 'http://127.0.0.1:49159'
    cfg = HERE / 'isolated-config.json'
    cfg.write_text(json.dumps(config), encoding='utf-8')
    shell('[ ! -e ' + ROOT + ' ] && mkdir ' + ROOT + ' && mkdir ' + ROOT + '/bin ' + ROOT + '/state && ln -s /opt/instrument/sounds ' + ROOT + '/sounds')
    adb('push', r'\\wsl.localhost\Luckfox-Ubuntu-22.04\tmp\backlight-validation-emmc-20261013.bin', ROOT + '/bin/instrument_app')
    adb('push', str(cfg), ROOT + '/config.json')
    # This local file contains production network settings; do not archive it.
    cfg.unlink()
    shell('chmod 755 ' + ROOT + '/bin/instrument_app; printf \'{"brightness":37}\' > ' + ROOT + '/state/backlight.json; printf 0 > ' + BUTTONS)
    stop_owned('/opt/instrument/bin/instrument_app ')
    shell('setsid env INSTRUMENT_BUTTON_FILE=' + BUTTONS + ' ' + ROOT + '/bin/instrument_app ' + ROOT + '/config.json </dev/null >' + ROOT + '/stdout.log 2>&1 & sleep 1')
    time.sleep(3)
    state = query()
    assert not state['paired_host_id'] and state['phase'] == 'idle'
    assert state['volume'] == state['saved_volume'] == 10
    print(json.dumps(dict(setup='PASS', serial=SERIAL, version=shell('/opt/instrument/bin/instrument_app --version'), root=ROOT, application_pid=state['application_pid'])))


def restore():
    assert shell('cat /proc/device-tree/serial-number').rstrip('\0') == SERIAL
    # Save only test-owned logs, never production students or videos.
    for name in ['runtime.jsonl', 'runtime.jsonl.1', 'runtime.jsonl.2']:
        path = ROOT + '/state/' + name
        if shell('if [ -f ' + path + ' ]; then echo yes; fi') == 'yes':
            adb('pull', path, str(HERE / ('board-test-' + name)))
    state = query()
    if state['gate_enabled']:
        raise RuntimeError('Test permission still enabled: stop test controller before restore')
    stop_owned(ROOT + '/bin/instrument_app ')
    shell('/etc/init.d/S80instrument start')
    for _ in range(50):
        time.sleep(.2)
        try:
            state = query()
            if not state['audio_busy']:
                break
        except (socket.timeout, OSError):
            continue
    before = json.loads((HERE / 'board-before-test.json').read_text(encoding='utf-8'))
    assert hashes() == before['preserved'], 'Production config/pair/brightness/program changed'
    assert shell('/opt/instrument/bin/instrument_app --version') == '3.3.11' and state['phase'] == 'idle' and not state['gate_enabled'] and not state['camera_fault']
    result = dict(restored='PASS', serial=SERIAL, state=state, preserved=hashes())
    (HERE / 'board-restored.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(restored='PASS', serial=SERIAL, version=shell('/opt/instrument/bin/instrument_app --version'), phase=state['phase'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['setup', 'restore'])
    args = parser.parse_args()
    (setup if args.operation == 'setup' else restore)()
