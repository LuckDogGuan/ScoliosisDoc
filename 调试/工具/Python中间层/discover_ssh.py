"""Read-only known-device discovery through the existing bridge; optional SSH proof."""
import argparse
import base64
from datetime import datetime
import getpass
import hashlib
import http.client
import http.server
import json
import logging
from pathlib import Path
import secrets
import sys
import threading

import instrument_debug_proxy as proxy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parents[4] / 'ScoliosisFlutter/data')
parser.add_argument('--bind', action='append', required=True, help='Local IPv4 interface; repeat for multiple NICs')
parser.add_argument('--target', action='append', default=[], help='Broadcast or known candidate IPv4; repeat as needed')
parser.add_argument('--ssh', action='store_true', help='Prompt for password and run read-only identity commands')
parser.add_argument('--password-stdin', action='store_true', help='Read password from stdin for unattended use; never save it')
parser.add_argument('--user', default='root')
parser.add_argument('--records', type=Path, default=Path(__file__).resolve().parents[2] / '记录/SSH登录')
args = parser.parse_args()
record = args.records / datetime.now().strftime('%Y%m%d-%H%M%S')
record.mkdir(parents=True, exist_ok=False)
proxy.LOG.setLevel(logging.INFO)
proxy.LOG.addHandler(logging.FileHandler(record / 'proxy.jsonl', encoding='utf-8'))
book = json.loads((args.data_root / '设备.json').read_text(encoding='utf-8-sig'))
results = []
devices = {}
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), proxy.Bridge)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    for device in book['paired']:
        for bind in args.bind:
            for target in args.target or ['255.255.255.255']:
                packet = dict(version=3, op='hello_query', host_id=book['hostId'],
                              device_id=device, sequence=0, nonce=secrets.token_hex(16))
                body = dict(packet=base64.b64encode(json.dumps(packet).encode()).decode(),
                            address=target, port=37020, wait_ms=800, broadcast=True, bind_address=bind)
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    client.request('POST', '/debug/udp', json.dumps(body), {'Content-Type': 'application/json'})
                    response = client.getresponse()
                    payload = json.loads(response.read())
                    row = dict(local_time=datetime.now().astimezone().isoformat(), bind=bind,
                               target=target, http_status=response.status, replies=[])
                    for item in payload.get('replies', []):
                        reply = json.loads(base64.b64decode(item['packet']))
                        matched = item['port'] == 37020 and all(reply.get(k) == packet[k] for k in
                                  ('version', 'host_id', 'device_id', 'sequence', 'nonce')) and reply.get('op') == 'hello_reply' and reply.get('ok') is True
                        row['replies'].append(dict(address=item['address'], matched=matched, packet=reply))
                        if matched:
                            devices[(device, item['address'])] = reply
                    if 'error' in payload:
                        row['error'] = payload['error']
                    results.append(row)
                except (OSError, ValueError) as error:
                    results.append(dict(bind=bind, target=target, error=str(error)))
                finally:
                    client.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
(record / 'discovery.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(records=str(record), devices=[dict(device_id=d, address=a) for d, a in devices]), ensure_ascii=False))
ssh_results = []
if args.ssh and devices:
    import paramiko
    password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('SSH password (not saved): ')
    known_hosts = args.records / 'known_hosts'
    for device, address in devices:
        client = paramiko.SSHClient()
        if known_hosts.exists():
            client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        row = dict(local_time=datetime.now().astimezone().isoformat(), device_id=device,
                   address=address, port=22, user=args.user, first_use_trust='live paired discovery; fingerprint recorded')
        try:
            client.connect(address, port=22, username=args.user, password=password, timeout=5,
                           banner_timeout=5, auth_timeout=5, look_for_keys=False, allow_agent=False)
            key = client.get_transport().get_remote_server_key()
            row.update(host_key_type=key.get_name(), host_key_sha256='SHA256:' +
                       base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('='))
            client.save_host_keys(str(known_hosts))
            command = 'id; hostname; uname -a; cat /etc/os-release; ip -4 addr show; cat /opt/instrument/version; cat /proc/device-tree/serial-number'
            row['command'] = command
            _, stdout, stderr = client.exec_command(command, timeout=10)
            row.update(stdout=stdout.read().decode(errors='replace'), stderr=stderr.read().decode(errors='replace'),
                       exit_status=stdout.channel.recv_exit_status(), authenticated=True)
        except Exception as error:
            row.update(authenticated=False, error=type(error).__name__ + ': ' + str(error))
        finally:
            client.close()
        ssh_results.append(row)
        (record / 'ssh.json').write_text(json.dumps(ssh_results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(row, ensure_ascii=False))
    del password
print('records=' + str(record))
raise SystemExit(0 if devices and (not args.ssh or all(r['authenticated'] for r in ssh_results)) else 1)
