"""Restart only the identity-checked idle board's camera, preserving its INI."""
from pathlib import Path
import json, secrets, socket, time

root = Path(__file__).parent
prelude = (root / 'inspect_board.py').read_text(encoding='utf-8').split('\ntry:\n')[0]
exec(compile(prelude, 'inspect_board.py', 'exec'))
try:
    request = {'version': 3, 'op': 'hello_query', 'host_id': 'camera-repair-observer',
               'device_id': 'CAM-41eda5f2c5b00de1', 'sequence': 0, 'nonce': secrets.token_hex(16)}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('192.168.101.2', 0)); sock.settimeout(3)
        sock.sendto(json.dumps(request).encode(), ('192.168.101.4',37020))
        raw, peer = sock.recvfrom(16384)
    reply = json.loads(raw)
    assert peer == ('192.168.101.4',37020)
    assert all(reply.get(k) == request[k] for k in ['device_id','host_id','sequence','nonce'])
    assert reply['phase'] == 'idle' and not reply['gate_enabled'] and not reply['diagnostics_active'] and not reply['capture_id'] and not reply['uploading_capture_id']
    assert read('cat /proc/device-tree/serial-number')['stdout'].strip() == '41eda5f2c5b00de1'
    before = read('sha256sum /userdata/rkipc.ini; pidof rkipc; pidof instrument_app')
    camera_pid = read('pidof rkipc')['stdout'].strip()
    assert not camera_pid or camera_pid.isdigit(), 'Expected at most one camera process'
    stopped = read(f'kill -TERM {camera_pid}; n=0; while kill -0 {camera_pid} 2>/dev/null; do sleep 1; n=$((n+1)); test "$n" -lt 8 || exit 2; done') if camera_pid else {'status':0,'stdout':'Already stopped','stderr':''}
    assert stopped['status'] == 0, 'Camera did not stop; refused duplicate start'
    environment = read('find /oem/usr/lib -name librockit.so; grep LD_LIBRARY_PATH /etc/profile /etc/init.d/rcS 2>/dev/null')
    print(json.dumps({'loader_environment':environment}),flush=True)
    launched = read('nohup env TZ=CST-8 LD_LIBRARY_PATH=/oem/usr/lib:/usr/lib:/lib LD_PRELOAD=/opt/instrument/bin/luckfox_mux_adapter.so /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles </dev/null >/tmp/camera-repair-20261009.log 2>&1 &')
    time.sleep(3)
    after = read('sha256sum /userdata/rkipc.ini; pidof rkipc; pidof instrument_app; tail -40 /tmp/camera-repair-20261009.log')
    report = {'before':before, 'stopped':stopped, 'launched':launched, 'after':after}
    (root / 'camera-restart.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    assert read('pidof rkipc')['stdout'].strip().isdigit(), 'Camera startup failed'
    assert before['stdout'].splitlines()[0] == after['stdout'].splitlines()[0], 'Camera INI hash changed'
finally:
    transport.close()
