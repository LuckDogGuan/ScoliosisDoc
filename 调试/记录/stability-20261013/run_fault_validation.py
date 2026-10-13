"""Finite explicit-device fault campaign under real Windows mute, always restoring audio."""
import argparse,importlib.util,json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser()
for name in ('serial','device','button-file','data-root'):p.add_argument('--'+name,required=True)
p.add_argument('--soak-minutes',type=int,default=60);p.add_argument('--http-port',type=int,default=8081)
p.add_argument('--flutter',default=r'D:\SoftWare\Flutter\flutter_windows_3.41.9-stable\flutter\bin\flutter.bat')
p.add_argument('--flutter-root',default=r'D:\code\Scoliosis\ScoliosisFlutter')
p.add_argument('--adb',default=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe')
args=p.parse_args();r=Path(__file__).parent
assert args.soak_minutes>=0
spec=importlib.util.spec_from_file_location('audio_fact',r/'windows_audio_fact_test.py')
audio=importlib.util.module_from_spec(spec);spec.loader.exec_module(audio)
endpoint=audio.Endpoint();original=endpoint.state()
original_file=r/'fault-audio-original.local.json';original_file.write_text(json.dumps(original))
report=dict(utc=datetime.now(timezone.utc).isoformat(),original=original,states=[],restored=False)
env=dict(os.environ,INSTRUMENT_DEBUG_PROXY='http://127.0.0.1:18085',STABILITY_ADB=args.adb,
 STABILITY_SERIAL=args.serial,STABILITY_DEVICE=args.device,STABILITY_BUTTON_FILE=args.button_file,
 STABILITY_DATA_ROOT=str(Path(args.data_root).resolve()),STABILITY_PYTHON=sys.executable,
 STABILITY_HTTP_PORT=str(args.http_port),STABILITY_SOAK_MINUTES=str(args.soak_minutes),
 STABILITY_VIDEO_CHECK=str(r/'verify_video.py'),STABILITY_RESTART_HELPER=str(r/'crash_restart_for_test.py'),
 STABILITY_FAULT_CONFIG=str(r/'fault-policy.local.json'),STABILITY_FAULT_LOG=str(r/'fault-injections.jsonl'),
 STABILITY_AUDIO_RESTORE=str(r/'restore_test_sound.py'),STABILITY_AUDIO_STATE=str(original_file))
try:
 report['during']=endpoint.set(True,original['volume'])
 print('WINDOWS_BOARD_MUTE '+json.dumps(report['during']),flush=True)
 child=subprocess.Popen([args.flutter,'test','--no-pub','tool/capture_stability_fault_test.dart','--reporter','expanded'],cwd=args.flutter_root,env=env)
 next_check=time.monotonic()
 while child.poll() is None:
  if time.monotonic()>=next_check:
   state=dict(utc=datetime.now(timezone.utc).isoformat(),**endpoint.state())
   report['states'].append(state);print('WINDOWS_BOARD_AUDIO '+json.dumps(state),flush=True)
   next_check+=300
  time.sleep(1)
 report['exit_code']=child.returncode
finally:
 try:
  report['after']=endpoint.set(original['mute'],original['volume']);report['restored']=True
 finally:
  endpoint.close();(r/'windows-muted-board.json').write_text(json.dumps(report,indent=2))
 print('WINDOWS_BOARD_AUDIO_RESTORED '+json.dumps(report.get('after')),flush=True)
raise SystemExit(report['exit_code'])

