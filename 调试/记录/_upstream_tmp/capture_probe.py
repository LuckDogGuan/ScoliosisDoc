import glob
import os
import time

from rkipc_call import call


def invoke(name, *args, string=None, replies=1):
    hello, result, seconds = call(name, args, string, replies)
    print(name, result, f"{seconds:.3f}s", flush=True)
    if hello != 0 or result[-1] != 0:
        raise RuntimeError(name)
    return result


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
    time.sleep(10)
    invoke('rk_storage_record_stop')
    recording = False
    print('elapsed', f'{time.monotonic() - t0:.3f}s', flush=True)
finally:
    if recording:
        invoke('rk_storage_record_stop')
    invoke('rk_video_set_frame_rate', 0, string='60/6')
    invoke('rk_video_set_max_rate', 0, 640)
    invoke('rk_video_set_gop', 0, 10)

after = set(glob.glob('/userdata/video0/*.mp4')) - before
print('new_files', sorted(after), flush=True)
if len(after) != 1:
    raise RuntimeError('expected exactly one new mp4')
