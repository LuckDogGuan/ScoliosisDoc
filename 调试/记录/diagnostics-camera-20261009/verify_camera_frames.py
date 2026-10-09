from pathlib import Path
from io import BytesIO
import hashlib, json, re
from PIL import Image

root = Path(__file__).parent
prelude = (root / 'inspect_board.py').read_text(encoding='utf-8').split('\ntry:\n')[0]
exec(compile(prelude, 'inspect_board.py', 'exec'))
try:
    assert read('cat /proc/device-tree/serial-number')['stdout'].strip() == '41eda5f2c5b00de1'
    probe = json.loads((root / 'snapshot-probe.json').read_text(encoding='utf-8'))
    names = re.findall(r'/video0/([0-9]{14}\.jpeg)', probe['after'])
    name = names[-1]
    sftp = paramiko.SFTPClient.from_transport(transport)
    with sftp.open('/video0/' + name, 'rb') as image_file:
        data = image_file.read(4*1024*1024 + 1)
    sftp.close()
    assert 4 <= len(data) <= 4*1024*1024
    assert data[:2] == bytes([255,216]) and data[-2:] == bytes([255,217])
    snapshot = Image.open(BytesIO(data)); snapshot.load()
    rtsp_path = root / 'rtsp-probe.jpg'
    rtsp = Image.open(rtsp_path); rtsp.load()
    restarted = json.loads((root / 'camera-restart.json').read_text(encoding='utf-8'))
    assert restarted['before']['stdout'].splitlines()[0] == restarted['after']['stdout'].splitlines()[0]
    report = {'snapshot_rpc': 'passed', 'snapshot_valid_jpeg': True,
      'snapshot_bytes': len(data), 'snapshot_size': snapshot.size,
      'snapshot_sha256': hashlib.sha256(data).hexdigest(),
      'rtsp_valid_frame': True, 'rtsp_size': rtsp.size,
      'rtsp_sha256': hashlib.sha256(rtsp_path.read_bytes()).hexdigest(),
      'camera_ini_hash_preserved': True, 'business_program_restarted': False,
      'firmware_source_changed': False, 'gui_preview': 'pending', 'cold_boot_regression': 'pending'}
    (root / 'camera-recovery-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report))
finally:
    transport.close()
