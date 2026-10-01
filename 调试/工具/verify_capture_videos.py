"""Decode every delivered MP4 with local OpenCV; retain all source videos."""
import argparse
import json
import pathlib

import cv2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=pathlib.Path)
    parser.add_argument('--expected', type=int)
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    files = sorted(args.root.rglob('*.mp4'))
    if args.expected is not None and len(files) != args.expected:
        raise RuntimeError(f'expected {args.expected} videos, found {len(files)}')
    rows = []
    for file in files:
        capture = cv2.VideoCapture(str(file))
        if not capture.isOpened():
            raise RuntimeError(f'cannot open {file}')
        fps = capture.get(cv2.CAP_PROP_FPS)
        advertised = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        count = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame.shape[:2] != (height, width):
                raise RuntimeError(f'inconsistent frame size: {file}')
            count += 1
        capture.release()
        if count == 0 or fps <= 0 or count != advertised:
            raise RuntimeError(f'incomplete decoding {file}: {count}/{advertised}, fps={fps}')
        rows.append(dict(file=str(file.resolve()), bytes=file.stat().st_size,
                         width=width, height=height, fps=fps,
                         decoded_frames=count, reported_frames=advertised,
                         duration_from_frames_s=count / fps))
    document = dict(decoder='OpenCV ' + cv2.__version__, videos=rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(document, ensure_ascii=False))


if __name__ == '__main__':
    main()
