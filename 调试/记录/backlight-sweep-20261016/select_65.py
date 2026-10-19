"""Apply the reviewed 65/100 setting using the identity-bound diagnostic API."""
import base64, hashlib, json, os, socket, time
import paramiko
import sweep as s

assert not (s.ROOT/'selection.json').exists(), 'Preserve previous selection evidence'
owned=False
try:
    s.transport=paramiko.Transport(socket.create_connection((s.SAVED['address'],22),5))
    s.transport.start_client(timeout=5)
    fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(s.transport.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
    assert fingerprint==s.SAVED['host_key']
    s.transport.auth_password('root',os.environ.get('LUCKFOX_SSH_PASSWORD','luckfox'))
    assert s.remote('cat /proc/device-tree/serial-number')==s.SAVED['serial']
    assert json.loads(s.remote('cat /opt/instrument/config.json'))['device_id']==s.DEVICE
    state=s.exchange('hello_query')
    assert state['phase']=='idle' and not any(state.get(k) for k in ('gate_enabled','diagnostics_active','uploading_capture_id','audio_busy'))
    assert json.loads(s.remote('cat /opt/instrument/state/active-v3.json'))=={}
    s.host,s.boot=state['paired_host_id'],state['boot_id']
    s.control('diagnostics_start',ttl_ms=6000);owned=True
    reply=s.control('diagnostics_backlight',brightness=65)
    assert reply['saved_brightness']==65
    s.control('diagnostics_end');owned=False
    time.sleep(.5)
    after=s.exchange('hello_query')
    assert after['phase']=='idle' and not after['diagnostics_active'] and not after['gate_enabled']
    value=json.loads(s.remote('cat /opt/instrument/state/backlight.json'))['brightness']
    assert value==65
    original=json.loads((s.ROOT/'before.json').read_text(encoding='utf-8'))
    preserved=s.remote('sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json /opt/instrument/bin/instrument_app /userdata/rkipc.ini')
    assert preserved==original['preserved_sha256']
    s.write('selection.json',dict(device=s.DEVICE,selected_brightness=value,recommended_range=[60,70],
        initial_brightness=original['saved_brightness'],phase=after['phase'],diagnostics_active=False,gate_enabled=False,
        camera_fault=after.get('camera_fault'),preserved_match=True,stored_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        note='Normal test exit turns lamp off. Next formal capture reuses saved brightness 65. Fixed-pose recommendation only.'))
    print(json.dumps(dict(selected=value,phase=after['phase'],diagnostics_active=False,preserved_match=True)))
finally:
    if owned:
        try: s.control('diagnostics_end')
        except Exception: pass
    if s.transport: s.transport.close()
