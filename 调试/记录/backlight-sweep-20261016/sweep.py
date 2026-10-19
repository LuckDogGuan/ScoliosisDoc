"""Bounded Wi-Fi diagnostic sweep; uses the existing camera RTSP stream."""
from pathlib import Path
import base64, hashlib, json, os, socket, subprocess, sys, threading, time, uuid
import cv2
import numpy as np
import paramiko

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
REFINE = sys.argv[1:] == ['refine']
if REFINE:
    ROOT = ROOT/'refine'
    ROOT.mkdir(exist_ok=True)
DEVICE = 'CAM-211ec7045815bf02'
SAVED = json.loads((PROJECT/'调试/工具/一键烧录/wifi-devices.json').read_text(encoding='utf-8-sig'))[DEVICE]
FFMPEG = Path(r'D:\code\Scoliosis\ScoliosisFlutter\thirdPartyLibrary\ffmpeg\ffmpeg.exe')
lock = threading.Lock()
control_lock = threading.Lock()
latest = None
failure = []
stop = threading.Event()
token = 'diag-' + uuid.uuid4().hex
transport = None
decoder = None
owned = False

def write(name, value):
    (ROOT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def remote(command):
    ch = transport.open_session(timeout=5)
    ch.settimeout(8)
    ch.exec_command(command)
    out = ch.makefile('rb').read().decode().replace('\0','').strip()
    err = ch.makefile_stderr('rb').read().decode()
    code = ch.recv_exit_status()
    ch.close()
    if code: raise RuntimeError(f'SSH command failed ({code}): {err[:200]}')
    return out

def exchange(op, host='brightness-readonly', **fields):
    packet = dict(version=3, device_id=DEVICE, host_id=host, sequence=0,
                  op=op, nonce=uuid.uuid4().hex, **fields)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        sock.sendto(json.dumps(packet).encode(), (SAVED['address'],37020))
        while True:
            data, peer = sock.recvfrom(8192)
            row = json.loads(data)
            if (peer == (SAVED['address'],37020) and row.get('nonce') == packet['nonce']
                and row.get('device_id') == DEVICE and row.get('sequence') == packet['sequence']
                and row.get('op') == ('hello_reply' if op=='hello_query' else op+'_reply')):
                return row

def control(op, **fields):
    with control_lock:
        return command(op, **fields)

def command(op, **fields):
    for attempt in range(3):
        state = exchange('hello_query')
        if state.get('boot_id') != boot: raise RuntimeError('Device restarted')
        if state.get('gate_enabled') or state.get('phase') != 'idle' or state.get('uploading_capture_id'):
            raise RuntimeError('Business capture is active; abort comparison')
        seq = int(state['control_sequence'])+1
        # Read-only desktop polling does not consume control sequence numbers.
        packet = dict(version=3,device_id=DEVICE,host_id=host,sequence=seq,
                      nonce=uuid.uuid4().hex,op=op,boot_id=boot,diagnostics_id=token,**fields)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.sendto(json.dumps(packet).encode(),(SAVED['address'],37020))
            while True:
                data, peer = sock.recvfrom(8192)
                row=json.loads(data)
                if peer != (SAVED['address'],37020) or row.get('nonce') != packet['nonce']: continue
                assert row.get('device_id')==DEVICE and row.get('boot_id')==boot and row.get('sequence')==seq
                if row.get('error')=='stale_sequence': break
                if not row.get('ok'): raise RuntimeError(op+': '+str(row.get('error','rejected')))
                return row
    raise RuntimeError('Concurrent control sequence changes')

def renew():
    while not stop.wait(1.3):
        try: control('diagnostics_renew',ttl_ms=5000)
        except Exception as error:
            failure.append(str(error)); stop.set(); return

def frames():
    global latest
    size=1280*1080*3
    count=0
    while not stop.is_set():
        blob=bytearray()
        while len(blob)<size:
            part=decoder.stdout.read(size-len(blob))
            if not part: return
            blob.extend(part)
        count+=1
        with lock: latest=(count,time.monotonic(),bytes(blob))

def fresh(previous=0):
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        if failure: raise RuntimeError(failure[0])
        with lock: sample=latest
        if sample and sample[0]>previous and time.monotonic()-sample[1]<.6: return sample
        time.sleep(.05)
    raise RuntimeError('No fresh decoded frame')

def capture_pass(levels, label, settle=3):
    records=[]
    for level in levels:
        if failure: raise RuntimeError(failure[0])
        reply=control('diagnostics_backlight',brightness=level)
        assert reply.get('saved_brightness')==level
        if stop.wait(settle): raise RuntimeError('Diagnostic lease failed')
        previous=0
        for index in range(3):
            seq,decoded,blob=fresh(previous)
            previous=seq
            frame=np.frombuffer(blob,np.uint8).reshape(1080,1280,3)
            name=f'{label}-{level:03d}-{index+1}.png'
            ok,png=cv2.imencode('.png',frame)
            assert ok
            (ROOT/name).write_bytes(png.tobytes())
            record=dict(file=name,brightness=level,pass_name=label,index=index+1,
                received_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),decoded_sequence=seq,
                decoded_age_ms=round((time.monotonic()-decoded)*1000,1),
                sha256=hashlib.sha256(png).hexdigest(),width=1280,height=1080)
            records.append(record)
            with (ROOT/'captures.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(record)+'\n')
            time.sleep(.55)
        print(json.dumps(dict(pass_name=label,brightness=level,images=3)),flush=True)
    return records

if __name__=='__main__':
    assert not (ROOT/'before.json').exists(), 'Use a new output folder; preserve earlier captures'
    try:
        transport=paramiko.Transport(socket.create_connection((SAVED['address'],22),5))
        transport.start_client(timeout=5)
        fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(transport.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
        assert fingerprint==SAVED['host_key'], 'SSH key mismatch'
        transport.auth_password('root',os.environ.get('LUCKFOX_SSH_PASSWORD','luckfox'))
        assert remote('cat /proc/device-tree/serial-number')==SAVED['serial']
        assert json.loads(remote('cat /opt/instrument/config.json'))['device_id']==DEVICE
        assert json.loads(remote('cat /opt/instrument/state/active-v3.json'))=={}
        assert not remote('find /opt/instrument/capture/writing -type f')
        state=exchange('hello_query')
        assert state['phase']=='idle' and not any(state.get(k) for k in ('gate_enabled','diagnostics_active','uploading_capture_id','audio_busy'))
        host,boot=state['paired_host_id'],state['boot_id']
        assert host and state['peer_ip']
        original=json.loads(remote('cat /opt/instrument/state/backlight.json'))['brightness']
        preserved=remote('sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json /opt/instrument/bin/instrument_app /userdata/rkipc.ini')
        write('before.json',dict(device=DEVICE,address=SAVED['address'],firmware=remote('cat /opt/instrument/installed-version'),
            saved_brightness=original,ssh_host_key=fingerprint,phase=state['phase'],preserved_sha256=preserved,
            source='existing RTSP /live/0, decoded original-size PNG; not original sensor JPEG',
            note='Direct diagnostic lease; desktop diagnostic-image pushes may be rejected because GUI test is closed. No business capture is created.'))
        control('diagnostics_start',ttl_ms=5000); owned=True
        threading.Thread(target=renew,daemon=True).start()
        decoder=subprocess.Popen([str(FFMPEG),'-hide_banner','-loglevel','error','-nostdin','-rtsp_transport','tcp',
            '-stimeout','3000000','-i',f"rtsp://{SAVED['address']}:554/live/0",'-map','0:v:0',
            '-an','-sn','-pix_fmt','bgr24','-vsync','0','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,stderr=(ROOT/'decoder.log').open('wb'))
        threading.Thread(target=frames,daemon=True).start()
        fresh()
        levels=[55,65,75] if REFINE else [40,50,60,70,80,90,100]
        captures=capture_pass(levels,'up')
        captures+=capture_pass(list(reversed(levels)),'down')
        write('sweep.json',dict(captures=len(captures),levels=levels,repeats_per_level=6,
            completed=True,focus='unchanged',pose='single fixed pose; angle not independently verified'))
    finally:
        stop.set()
        time.sleep(.2)
        if owned:
            try:
                control('diagnostics_backlight',brightness=original)
                control('diagnostics_end')
            except Exception as error: write('cleanup-error.json',dict(error=str(error),lease_autoexpires_ms=5000))
        if decoder:
            decoder.terminate()
            try: decoder.wait(timeout=4)
            except subprocess.TimeoutExpired: decoder.kill(); decoder.wait()
        if transport and owned:
            try:
                after=exchange('hello_query')
                write('after.json',dict(device=DEVICE,saved_brightness=json.loads(remote('cat /opt/instrument/state/backlight.json'))['brightness'],
                    phase=after.get('phase'),diagnostics_active=after.get('diagnostics_active'),gate_enabled=after.get('gate_enabled'),
                    preserved_sha256=remote('sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json /opt/instrument/bin/instrument_app /userdata/rkipc.ini'),
                    preserved_match=remote('sha256sum /opt/instrument/config.json /opt/instrument/state/pair-v3.json /opt/instrument/bin/instrument_app /userdata/rkipc.ini')==preserved))
            finally: transport.close()
