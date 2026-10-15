"""Isolated ARM reader benchmark. No service restarts, camera controls or business captures."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--pgm', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    def shell(code, timeout=30):
        completed = subprocess.run(['adb','-s',args.serial,'shell','python3 -c '+shlex.quote(code)],
                                   capture_output=True,timeout=timeout,check=True)
        text = completed.stdout.decode('utf-8','replace').replace('\r','')
        return json.loads(text.strip())
    before = shell("""import json,hashlib,pathlib
paths=['/opt/instrument/state/active-v3.json','/opt/instrument/state/recording-v3.json','/opt/instrument/state/pair-v3.json','/opt/instrument/state/backlight.json']
active=json.load(open(paths[0]))
if active: raise SystemExit('Business activity exists; benchmark refused')
print(json.dumps({'active':active,'hashes':{p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths},'model':pathlib.Path('/proc/device-tree/model').read_text().strip('\\0'),'version':pathlib.Path('/opt/instrument/state/version').read_text().strip()}))
""")
    if before['model'] != 'Luckfox Pico Zero':
        raise RuntimeError('Unexpected board model')
    nonce = hashlib.sha256(args.binary.read_bytes()+args.profile.read_bytes()).hexdigest()[:16]
    remote = f'/tmp/ruler-vision-{nonce}'
    shell(f"import pathlib,json; p=pathlib.Path('{remote}'); p.mkdir(exist_ok=False); print(json.dumps({{'created':str(p)}}))")
    hashes = {}
    for source,name in [(args.binary,'reader'),(args.profile,'calibration.json'),(args.pgm,'input.pgm')]:
        subprocess.run(['adb','-s',args.serial,'push',str(source),f'{remote}/{name}'],check=True,capture_output=True,timeout=20)
        hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    code = f"""import os,json,hashlib,pathlib,subprocess,resource,time
root=pathlib.Path('{remote}')
expected={hashes!r}
assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in expected.items())
assert json.load(open('/opt/instrument/state/active-v3.json'))=={{}}
os.chmod(root/'reader',0o700)
start=time.monotonic()
done=subprocess.run([str(root/'reader'),str(root/'calibration.json'),'--benchmark',str(root/'input.pgm'),'300'],capture_output=True,timeout=20,check=True)
wall=time.monotonic()-start
rows=[json.loads(line.split(' ',1)[1]) for line in done.stdout.decode().splitlines()]
assert len(rows)==300
times=sorted(r['processing_ms'] for r in rows)
memory={{line.split(':')[0]:line.split(':')[1].strip() for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}}
print(json.dumps({{'iterations':len(rows),'native_ms_p50':times[len(times)//2],'native_ms_p95':times[int(len(times)*.95)],'native_ms_max':max(times),'wall_seconds_including_startup_and_output':wall,'child_peak_rss_kb':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'first_reading':rows[0],'memory_after':memory,'rkipc_running':bool(subprocess.getoutput('pidof rkipc').strip()),'capture_to_display_ms':None,'concurrent_recording_verified':False,'original_camera_images_used':False}}))
"""
    try:
        result=shell(code)
        after=shell("import json,hashlib,pathlib; paths="+repr(list(before['hashes']))+"; print(json.dumps({'hashes':{p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths},'active':json.load(open(paths[0]))}))")
        result.update(device_serial=args.serial,device_model=before['model'],firmware=before['version'],
                      source_sha256=hashes, business_files_unchanged=before['hashes']==after['hashes'],
                      transfer='ADB fallback; no trusted Wi-Fi SSH host configuration available',
                      interpretation='ARM-only calculation on a stored 640x480 reference frame; not live camera/recording/RTSP acceptance')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    finally:
        # Explicit individual diagnostic files only; never recursive cleanup.
        shell(f"import pathlib,json; p=pathlib.Path('{remote}/reader'); p.unlink(missing_ok=True); print(json.dumps({{'removed':str(p)}}))")
        shell(f"import pathlib,json; p=pathlib.Path('{remote}/calibration.json'); p.unlink(missing_ok=True); print(json.dumps({{'removed':str(p)}}))")
        shell(f"import pathlib,json; p=pathlib.Path('{remote}/input.pgm'); p.unlink(missing_ok=True); print(json.dumps({{'removed':str(p)}}))")
        shell(f"import pathlib,json; p=pathlib.Path('{remote}'); p.rmdir(); print(json.dumps({{'removed_empty_directory':str(p)}}))")


if __name__=='__main__':
    main()
