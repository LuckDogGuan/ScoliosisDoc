from pathlib import Path
from datetime import datetime
import base64, hashlib, json, socket, os
import paramiko

key = 'SHA256:QLjOSdI3DrGRFdzX72pAcNRo4l6QPngLFHBNr6SYKgk'
transport = paramiko.Transport(socket.create_connection(('192.168.101.4', 22), timeout=6))
transport.start_client(timeout=6)
fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(transport.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
assert fingerprint == key, 'Identity mismatch; refuse authentication'
transport.auth_password('root', os.environ['LUCKFOX_SSH_PASSWORD'])
def read(command):
    channel = transport.open_session(timeout=6); channel.settimeout(12)
    channel.exec_command(command)
    out = channel.makefile('rb').read().decode(errors='replace').replace('\x00', '')
    error = channel.makefile_stderr('rb').read().decode(errors='replace')
    status = channel.recv_exit_status(); channel.close()
    return {'stdout': out, 'stderr': error, 'status': status}
try:
    assert read('cat /proc/device-tree/serial-number')['stdout'].strip() == '41eda5f2c5b00de1'
    report = {'time': datetime.now().astimezone().isoformat(), 'fingerprint': fingerprint, 'read_only': True,
      'runtime': read('pidof instrument_app; pidof rkipc; ls -l /var/tmp/rkipc; ls /opt/instrument'),
      'camera_files': read('find /video0 -maxdepth 1 -type f -name "*.jpeg" | wc -l; df -h /video0; ls -ld /video0'),
      'trace_paths': read('ls -l /opt/instrument/state; ls -l /tmp/*log 2>/dev/null'),
      'recent_system': read('tail -80 /tmp/rkipc.log /tmp/instrument.log 2>/dev/null'),
      'diagnostic_trace': read('grep diagnostics /opt/instrument/state/runtime.jsonl | tail -45'),
      'jpeg_inventory': read('ls -l /video0/*.jpeg 2>/dev/null'),
      'camera_jpeg_config': read("grep -A35 '^\\[video.jpeg\\]' /userdata/rkipc.ini; grep enable_jpeg /userdata/rkipc.ini; readlink /proc/437/fd/1; readlink /proc/437/fd/2; tr '\\0' ' ' </proc/437/cmdline"),
      'camera_process_threads': read('ls /proc/437/task | wc -l; cat /proc/437/status | head -18; ls -l /tmp | head -18'),
      'camera_errors': read("grep -i 'jpeg\\|venc\\|photo\\|rkipc' /tmp/messages | tail -40; ls /proc/rk* 2>/dev/null"),
      'camera_stop_state': read('pidof rkipc; cat /proc/437/status | head -12; for t in /proc/437/task/*; do cat "$t/comm" "$t/wchan" 2>/dev/null; done')}
    Path(__file__).with_name('board-inspection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
finally:
    transport.close()
