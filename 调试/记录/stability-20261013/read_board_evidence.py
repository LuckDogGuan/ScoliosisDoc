"""Read-only USB/network fact collection; never stores SSID/password/voice data."""
import argparse
import collections
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import socket
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--serial', required=True)
parser.add_argument('--device', required=True)
parser.add_argument('--address', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--adb', default=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe')
args = parser.parse_args()


def shell(command):
    result = subprocess.run([args.adb, '-s', args.serial, 'shell', command],
                            capture_output=True, timeout=25, check=True)
    return result.stdout.decode('utf-8', 'replace').replace('\r', '').strip().rstrip('\x00')


config = json.loads(shell('cat /opt/instrument/config.json'))
assert config['device_id'] == args.device
assert shell('cat /proc/device-tree/serial-number') == args.serial
packet = dict(version=3, op='hello_query', device_id=args.device,
              host_id='stability-readonly', sequence=0, nonce=secrets.token_hex(16))
raw = shell("printf '%s' '" + json.dumps(packet) + "' | socat -T 2 - UDP4:127.0.0.1:37020")
reply = json.loads(raw)
assert all(reply[k] == packet[k] for k in ['version', 'device_id', 'host_id', 'sequence', 'nonce'])
reply['metrics'] = {k: v for k, v in reply.get('metrics', {}).items() if k != 'ssid'}
processes = {}
for name in ['instrument_app', 'rkipc']:
    if name == 'instrument_app' and isinstance(reply.get('application_pid'), int):
        pid = str(reply['application_pid'])
    else:
        candidates = shell('pidof ' + name).split()
        roots = [pid for pid in candidates if shell('awk \'/^PPid:/{print $2}\' /proc/' + pid + '/status') == '1']
        pid = roots[0] if len(roots) == 1 else candidates[0] if len(candidates) == 1 else ''
    assert pid.isdecimal(), f'expected one coordinator for {name}'
    processes[name] = dict(pid=int(pid), cmdline=shell('cat /proc/' + pid + '/cmdline').replace('\x00', ' '),
      environment=[v for v in shell('cat /proc/' + pid + '/environ').split('\x00')
                   if v.startswith(('INSTRUMENT_BUTTON_FILE=', 'LD_PRELOAD=', 'LD_LIBRARY_PATH=', 'TZ='))],
      stat=shell('cat /proc/' + pid + '/stat'))
profiles = subprocess.run(['netsh', 'wlan', 'show', 'profiles'], capture_output=True).stdout.decode('utf-8', 'replace')
network = []
for bind in ['0.0.0.0']:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        try:
            udp.bind((bind, 0)); udp.settimeout(1)
            udp.sendto(json.dumps(packet).encode(), (args.address, 37020))
            data, peer = udp.recvfrom(8192)
            network.append(dict(bind=bind, result='reply', peer=peer, valid=json.loads(data)['nonce'] == packet['nonce']))
        except OSError as error:
            network.append(dict(bind=bind, result=type(error).__name__))
groups = collections.defaultdict(list)
counts = collections.Counter()
for name in ['runtime.jsonl.2', 'runtime.jsonl.1', 'runtime.jsonl']:
    for line in shell('cat /opt/instrument/state/' + name).splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        counts[row.get('event')] += 1
        if row.get('boot_id'):
            groups[row['boot_id']].append(row)
boots = [dict(boot=b, count=len(rows), first_utc=rows[0]['utc_ms'], last_utc=rows[-1]['utc_ms'],
              first_mono=rows[0]['monotonic_ms'], last_mono=rows[-1]['monotonic_ms']) for b, rows in groups.items()]
report = dict(utc=datetime.now(timezone.utc).isoformat(), serial=args.serial, device=args.device,
              kernel_boot=shell('cat /proc/sys/kernel/random/boot_id'), uptime=shell('cat /proc/uptime'),
              app_version=shell('/opt/instrument/bin/instrument_app --version'),
              app_sha256=shell('sha256sum /opt/instrument/bin/instrument_app').split()[0],
              processes=processes, local_hello=reply, pc_udp_probe=network,
              board_ip=shell('ip -4 addr'), board_routes=shell('ip route'),
              saved_wifi_profile_matches_board=bool(config.get('wifi_ssid') and config['wifi_ssid'] in profiles),
              kernel_fault_evidence=shell("dmesg | grep -Ei 'out of memory|killed process|panic|segfault|watchdog|reset|error|fail' | tail -60"),
              event_counts=counts, runtime_boot_ranges=boots,
              boundary='application boot_id is generated on each runtime invocation; kernel reboot requires kernel boot_id or monotonic-reset evidence')
Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(output=args.output, local_hello_ok=reply['ok'], pc_udp_probe=network,
                     saved_wifi_profile_matches_board=report['saved_wifi_profile_matches_board'])))
