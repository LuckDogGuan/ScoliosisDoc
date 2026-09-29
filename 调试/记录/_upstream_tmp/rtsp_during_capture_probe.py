import glob
import os
import subprocess
import time

from rkipc_call import call


def invoke(name, *args, string=None):
    hello, result, _ = call(name, args, string)
    if hello != 0 or result[-1] != 0:
        raise RuntimeError((name, hello, result))


before = set(glob.glob('/userdata/video0/*.mp4'))
if os.path.exists(time.strftime('/userdata/video0/%Y%m%d%H%M%S.mp4')):
    raise RuntimeError('current-second filename already exists')
recording = False
try:
    invoke('rk_video_set_frame_rate', 0, string='60/2')
    invoke('rk_video_set_max_rate', 0, 4000)
    invoke('rk_video_set_gop', 0, 30)
    invoke('rk_storage_record_start')
    recording = True
    t0 = time.monotonic()
    time.sleep(1)
    try:
        result = subprocess.run(
            ['ffmpeg', '-nostdin', '-rtsp_transport', 'tcp', '-i',
             'rtsp://127.0.0.1:554/live/0', '-t', '1', '-c', 'copy',
             '-f', 'null', '-'],
            capture_output=True, text=True, timeout=4)
        print('rtsp_ffmpeg_exit', result.returncode, flush=True)
        print('rtsp_ffmpeg_tail', '\n'.join(result.stderr.splitlines()[-8:]), flush=True)
    except subprocess.TimeoutExpired as error:
        print('rtsp_ffmpeg_timeout', error.timeout, flush=True)
    remaining = 10 - (time.monotonic() - t0)
    if remaining > 0:
        time.sleep(remaining)
    invoke('rk_storage_record_stop')
    recording = False
    print('capture_elapsed', f'{time.monotonic() - t0:.3f}s', flush=True)
finally:
    if recording:
        invoke('rk_storage_record_stop')
    invoke('rk_video_set_frame_rate', 0, string='60/6')
    invoke('rk_video_set_max_rate', 0, 640)
    invoke('rk_video_set_gop', 0, 10)

print('new_files', sorted(set(glob.glob('/userdata/video0/*.mp4')) - before), flush=True)
