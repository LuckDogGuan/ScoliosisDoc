"""Actual camera JPEG transfer and controlled recordings in an isolated backup root."""
import http.server, json, subprocess, threading, time
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parent
SERIAL='41eda5f2c5b00de1'
def adb(*args):
    return subprocess.check_output(['adb','-s',SERIAL,*args],timeout=30).decode().replace('\r','').replace('\x00','').strip()
def shell(cmd):return adb('shell',cmd)
assert shell('cat /proc/device-tree/serial-number')==SERIAL
assert json.loads(shell('cat /opt/instrument/config.json'))['device_id']=='CAM-'+SERIAL
assert json.loads(shell('cat /opt/instrument/state/active-v3.json'))=={}
assert not shell('find /opt/instrument/capture/writing -type f')
received=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path=='/api/v3/diagnostics/frame'
        assert self.headers['X-Device-Id']=='CAM-'+SERIAL
        assert self.headers['X-Diagnostics-Id']=='quality-acceptance'
        data=self.rfile.read(int(self.headers['Content-Length']))
        assert 4<len(data)<=4*1024*1024 and data[:2]==b'\xff\xd8' and data[-2:]==b'\xff\xd9'
        (ROOT/'diagnostic-quality95.jpg').write_bytes(data);received.append(len(data))
        payload=b'{"ok":true}'
        self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def log_message(self,*args):pass
server=http.server.HTTPServer(('0.0.0.0',49161),Handler)
worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
try:
    shell('/tmp/instrument-334-fixes/camera_check frame http://192.168.101.2:49161 quality-acceptance')
    assert received
    with Image.open(ROOT/'diagnostic-quality95.jpg') as photo:
        photo.load();assert photo.size==(1280,1080)
        print('PASS: actual JPEG 1280x1080, quality95; bytes='+str(received[0]),flush=True)
finally:server.shutdown();worker.join();server.server_close()
rows=[]
for duration in [2500,3200]:
    before=shell('find /video0 -maxdepth 1 -type f -name "*.mp4"')
    started=int(time.time()*1000)
    output=shell('/tmp/instrument-334-fixes/camera_check record '+str(duration)+' diagnostic-'+str(duration))
    result=json.loads(output.splitlines()[-1]);assert result['result']==0 and result['reason']==0,result
    assert abs(result['duration_ms']-duration)<200,result
    assert '+0800' in output
    assert shell('find /video0 -maxdepth 1 -type f -name "*.mp4"')==before
    remote='/opt/instrument/backups/capture-fixes-20261007-1791365275/camera-check/capture/pending/diagnostic-'+str(duration)+'.mp4'
    adb('pull',remote,str(ROOT/('diagnostic-'+str(duration)+'.mp4')))
    rows.append(dict(requested_ms=duration,result=result,started_at_utc_ms=started,output=output,remote=remote))
    print('PASS: actual controlled recording '+str(duration)+'ms, UTC+8 time, isolated evidence',flush=True)
(ROOT/'camera-board.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
