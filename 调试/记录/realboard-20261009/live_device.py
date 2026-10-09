"""Identity-matched read-only hello; never sends a control command."""
from pathlib import Path
from datetime import datetime
import json, secrets, socket

request = {'version': 3, 'op': 'hello_query', 'host_id': 'realboard-observer',
           'device_id': 'CAM-41eda5f2c5b00de1', 'sequence': 0, 'nonce': secrets.token_hex(16)}
report = {'time': datetime.now().astimezone().isoformat(), 'read_only': True}
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('192.168.101.2', 0)); sock.settimeout(3)
        sock.sendto(json.dumps(request).encode(), ('192.168.101.4', 37020))
        raw, peer = sock.recvfrom(16384)
    reply = json.loads(raw)
    assert peer == ('192.168.101.4', 37020)
    assert reply.get('op') == 'hello_reply' and reply.get('ok') is True
    assert all(reply.get(key) == request[key] for key in ['version', 'host_id', 'device_id', 'sequence', 'nonce'])
    report.update(identity_verified=True, reply=reply)
except Exception as error:
    report.update(identity_verified=False, error=str(error))
Path(__file__).with_name('live-device.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
