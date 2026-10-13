"""Read-only five-minute checks for an explicitly targeted finite board soak."""
import argparse,base64,hashlib,json,re,secrets,subprocess,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--serial',required=True);p.add_argument('--device',required=True)
p.add_argument('--evidence',type=Path,required=True);p.add_argument('--run-log',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--proxy',default='http://127.0.0.1:18085')
p.add_argument('--interval',type=int,default=300);p.add_argument('--minutes',type=int,default=70)
p.add_argument('--adb',default=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe')
args=p.parse_args()
if args.interval<1 or args.minutes<1:p.error('positive interval and duration required')
def adb(command):
 r=subprocess.run([args.adb,'-s',args.serial,'shell',command],check=True,capture_output=True,timeout=20)
 return r.stdout.decode('utf-8','replace').replace('\r','').strip().rstrip('\x00')
def hello():
 packet=dict(version=3,op='hello_query',device_id=args.device,host_id='stability-monitor-observer',
             sequence=0,nonce=secrets.token_hex(16))
 body=json.dumps(dict(packet=base64.b64encode(json.dumps(packet).encode()).decode(),port=37020,wait_ms=2000)).encode()
 with urllib.request.urlopen(urllib.request.Request(args.proxy+'/debug/udp',data=body,
       headers={'Content-Type':'application/json'}),timeout=7) as response:
  replies=json.load(response)['replies']
  if not replies:raise TimeoutError('read-only hello timed out')
  h=json.loads(base64.b64decode(replies[0]['packet']))
  if h.get('device_id')!=args.device or h.get('nonce')!=packet['nonce']:raise ValueError('identity mismatch')
  return h
def check():
 rows=[];issues=[]
 if args.evidence.exists():
  for line in args.evidence.read_text(encoding='utf-8-sig').splitlines():
   try:rows.append(json.loads(line))
   except json.JSONDecodeError:issues.append('incomplete evidence line')
 captures=[r for r in rows if r.get('check')=='capture_complete']
 preflight=next((r for r in rows if r.get('check')=='preflight'),None)
 allowed_boots={preflight['app_boot']} if preflight else set()
 for row in rows:
  if row.get('check')=='controlled_restart':allowed_boots.add(row['new_boot'])
 passed=any(r.get('check')=='passed' for r in rows)
 for i,row in enumerate(captures,1):
  v=row['video'];duration=row['duration_ms']
  if row['round']!=i or row['student_id']!='stability-'+str(i):issues.append('round/student mismatch')
  if not 3000<=duration<=65000 or abs(v['decoded_duration_ms']-duration)>=1000:issues.append('duration mismatch')
  if v['bytes']<=0 or v['frames']<=0 or v['frames']!=v['expected_frames'] or not re.fullmatch('[0-9a-f]{64}',v['sha256']):issues.append('video metadata invalid')
  if preflight and (row['app_boot'] not in allowed_boots or row['kernel_boot']!=preflight['kernel_boot']):issues.append('boot changed')
 if len({r['capture_id'] for r in captures})!=len(captures):issues.append('duplicate capture')
 state=None
 try:
  assert adb('cat /proc/device-tree/serial-number')==args.serial
  state=hello()
  if state['volume']!=10 or state['saved_volume']!=10:issues.append('volume is not 10')
  if preflight and (state['boot_id'] not in allowed_boots or state['system_boot_id']!=preflight['kernel_boot']):issues.append('live boot changed')
  if state.get('camera_fault'):issues.append('camera fault')
 except Exception as error:issues.append(type(error).__name__+': '+str(error))
 if captures and not passed:
  at=datetime.fromisoformat(captures[-1]['time']).timestamp()
  if time.time()-at>120:issues.append('no new complete capture in 120 seconds')
 if args.run_log.exists():
  log=args.run_log.read_text(encoding='utf-8-sig',errors='replace')
  if 'Some tests failed' in log:issues.append('test process failed')
 expected_fault=None
 policy_file=args.output.parent/'fault-policy.local.json'
 if policy_file.exists():
  try:
   f=json.loads(policy_file.read_text(encoding='utf-8-sig'))
   if f.get('serial')==args.serial and f.get('device_id')==args.device and f.get('expires_at',0)>time.time() and (f.get('block_http') or f.get('block_udp')):expected_fault=f.get('fault_id')
  except ValueError:pass
 result=dict(utc=datetime.now(timezone.utc).isoformat(),check='five_minute_health',
   status='injected_fault' if expected_fault else 'passed' if passed and not issues else 'attention' if issues else 'running' if preflight else 'starting',
   rounds=len(captures),last_duration_ms=captures[-1]['duration_ms'] if captures else None,
   elapsed_ms=captures[-1]['elapsed_ms'] if captures else 0,issues=sorted(set(issues)))
 if expected_fault:result['expected_fault']=expected_fault
 try:
  import importlib.util
  audio_path=args.output.parent/'windows_audio_fact_test.py'
  spec=importlib.util.spec_from_file_location('monitor_audio',audio_path);audio=importlib.util.module_from_spec(spec);spec.loader.exec_module(audio)
  endpoint=audio.Endpoint()
  try:result['windows_audio']=endpoint.state()
  finally:endpoint.close()
 except (OSError,ValueError):result['windows_audio']='unavailable'
 if state:result.update(device=args.device,volume=state['volume'],saved_volume=state['saved_volume'],
    phase=state['phase'],app_boot=state['boot_id'],kernel_boot=state['system_boot_id'],
    pending_count=state['metrics']['pending_count'],gate_enabled=state['gate_enabled'],
    lease_remaining_ms=state['lease_remaining_ms'])
 args.output.parent.mkdir(parents=True,exist_ok=True)
 with args.output.open('a',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
 print(json.dumps(result,ensure_ascii=False),flush=True)
 return passed
deadline=time.monotonic()+args.minutes*60
while True:
 if check():break
 remaining=deadline-time.monotonic()
 if remaining<=0:break
 time.sleep(min(args.interval,remaining))

