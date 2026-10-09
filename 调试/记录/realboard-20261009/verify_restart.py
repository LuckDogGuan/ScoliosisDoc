from pathlib import Path
import json, sqlite3

root = Path(__file__).parent
before, exited, after = [json.loads((root / name).read_text(encoding='utf-8')) for name in
    ['restart-before-exit.json', 'restart-after-exit.json', 'restart-after-unpair.json']]
target = 'CAM-41eda5f2c5b00de1'
host = '82cf4d132682a987d068c18f2bc0004f'
assert before['reply']['paired_host_id'] == exited['reply']['paired_host_id'] == host
assert after['reply']['paired_host_id'] == ''
assert before['reply']['boot_id'] == after['reply']['boot_id']
assert after['reply']['control_sequence'] > exited['reply']['control_sequence']
assert after['reply']['wifi_state'] == 'available' and after['reply']['phase'] == 'idle'
db = Path('C:/Users/31186/AppData/Local/ScoliosisScreening/screening.sqlite3')
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
    payload = conn.execute('SELECT payload FROM runtime_state WHERE key=?', ('devices',)).fetchone()
    assert payload, 'Device state missing'
    devices = json.loads(payload[0])
assert target not in devices['paired']
assert target not in devices.get('pendingUnpairEvents', {})
assert target not in devices.get('pairTransactions', {})
assert devices.get('currentDeviceId') != target
report = {'passed': True, 'device_id': target, 'firmware': '3.3.7', 'flutter': '3.3.3',
          'forced_exit_while_idle': True, 'reopened_online': True,
          'board_pair_cleared': True, 'local_pair_and_pending_unpair_cleared': True,
          'wifi_retained': True, 'boot_unchanged': True,
          'sequence_before': exited['reply']['control_sequence'],
          'sequence_after': after['reply']['control_sequence'],
          'button_acceptance_tested': False}
(root / 'restart-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
