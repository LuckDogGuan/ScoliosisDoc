"""Fail on missing media time; measure frame PTS and decode every original file."""
import argparse
import csv
import hashlib
import json
import pathlib
import subprocess
from fractions import Fraction
from statistics import median

FFPROBE = r'D:\SoftWare\EVCapture\ffprobe.exe'
FFMPEG = r'D:\SoftWare\EVCapture\ffmpeg.exe'


def compare(pts, fps, reported_ms):
    if not pts or fps <= 0:
        raise ValueError('missing frames or invalid fps')
    if any(b <= a for a, b in zip(pts, pts[1:])):
        raise ValueError('non-increasing video PTS')
    media_ms = (pts[-1] - pts[0] + 1 / fps) * 1000
    allowed_ms = max(3 / fps * 1000, 100)
    difference_ms = abs(reported_ms - media_ms)
    return dict(media_ms=media_ms, reported_ms=reported_ms, difference_ms=difference_ms,
                allowed_ms=allowed_ms, passed=difference_ms <= allowed_ms,
                first_pts_s=pts[0], last_pts_s=pts[-1], frames=len(pts), fps=fps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=pathlib.Path)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    # Regression proves a one-second loss cannot be hidden by a decoder-only pass.
    assert not compare([i / 30 for i in range(45)], 30, 2500)['passed']
    assert compare([i / 30 for i in range(75)], 30, 2500)['passed']
    events = {}
    records = {}
    for state in args.root.rglob('状态.json'):
        data = json.loads(state.read_text(encoding='utf-8-sig'))
        for row in data.get('completionEvents', {}).values():
            events[row['captureId']] = row
    for record_file in args.root.rglob('记录.csv'):
        with record_file.open(encoding='utf-8-sig', newline='') as source:
            for row in csv.DictReader(source):
                records[row['文件名']] = row
    rows = []
    for file in sorted(args.root.rglob('*.mp4')):
        record = records.get(file.name)
        if not record or record['capture_id'] not in events:
            continue  # unknown-origin files are checked by their receipt, not a fabricated time
        event = events[record['capture_id']]
        probe = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'v:0',
                                '-show_frames', '-show_streams', '-of', 'json', str(file)],
                               capture_output=True, check=True)
        media = json.loads(probe.stdout)
        advertised_fps = float(Fraction(media['streams'][0]['r_frame_rate']))
        pts = [float(frame['best_effort_timestamp_time']) for frame in media['frames']]
        decode = subprocess.run([FFMPEG, '-v', 'error', '-i', str(file), '-f', 'null', '-'],
                                capture_output=True)
        if decode.returncode or decode.stderr:
            raise RuntimeError(f'incomplete decode: {file}: {decode.stderr.decode(errors="replace")}')
        fps = 1 / median(b - a for a, b in zip(pts, pts[1:])) if len(pts) > 1 else advertised_fps
        result = compare(pts, fps, event['durationMs'])
        result['advertised_fps'] = advertised_fps
        with file.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        result.update(capture_id=record['capture_id'], student_id=record['学生ID'],
                      result=event['result'], file=str(file.resolve()), size_bytes=file.stat().st_size,
                      sha256=digest, hash_matches=digest == record['SHA256'])
        rows.append(result)
    document = dict(videos=rows, passed=bool(rows) and all(row['passed'] and row['hash_matches'] for row in rows))
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(document, ensure_ascii=False))
    if not document['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
