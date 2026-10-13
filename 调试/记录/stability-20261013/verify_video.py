"""Decode every frame of one test video and report its content identity."""
import hashlib
import json
import sys
from pathlib import Path

import cv2

path = Path(sys.argv[1]).resolve(strict=True)
digest = hashlib.sha256()
with path.open('rb') as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
capture = cv2.VideoCapture(str(path))
try:
    if not capture.isOpened():
        raise RuntimeError('video cannot be opened')
    fps = capture.get(cv2.CAP_PROP_FPS)
    expected = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = 0
    while True:
        ok, image = capture.read()
        if not ok:
            break
        if image is None or image.size == 0:
            raise RuntimeError('empty decoded frame')
        frames += 1
    if fps <= 0 or frames <= 0 or (expected > 0 and frames != expected):
        raise RuntimeError(f'incomplete decode: {frames}/{expected}, fps={fps}')
    print(json.dumps(dict(path=str(path), sha256=digest.hexdigest(),
                         bytes=path.stat().st_size, frames=frames,
                         expected_frames=expected, fps=fps,
                         decoded_duration_ms=round(frames / fps * 1000))))
finally:
    capture.release()
