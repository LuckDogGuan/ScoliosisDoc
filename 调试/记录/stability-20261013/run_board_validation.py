"""Explicit-target runner. Board simulation setup/restoration stays with deployment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--serial', required=True)
parser.add_argument('--device', required=True)
parser.add_argument('--address', required=True)
parser.add_argument('--button-file', required=True)
parser.add_argument('--data-root', required=True)
parser.add_argument('--rounds', type=int, default=20)
parser.add_argument('--soak-minutes', type=int, default=60)
parser.add_argument('--http-port', type=int, default=8081)
parser.add_argument('--adb', default=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe')
parser.add_argument('--flutter', default=r'D:\SoftWare\Flutter\flutter_windows_3.41.9-stable\flutter\bin\flutter.bat')
parser.add_argument('--flutter-root', default=r'D:\code\Scoliosis\ScoliosisFlutter')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
root = Path(args.data_root).resolve()
if root.exists() and any(root.iterdir()):
    parser.error('--data-root must be a new or empty dedicated test directory')
if args.rounds < 20 or args.soak_minutes < 0:
    parser.error('at least 20 rounds, nonnegative soak duration required')
env = dict(os.environ, STABILITY_ADB=args.adb, STABILITY_SERIAL=args.serial,
           STABILITY_DEVICE=args.device, STABILITY_ADDRESS=args.address,
           STABILITY_BUTTON_FILE=args.button_file, STABILITY_DATA_ROOT=str(root),
           STABILITY_ROUNDS=str(args.rounds), STABILITY_SOAK_MINUTES=str(args.soak_minutes),
           STABILITY_HTTP_PORT=str(args.http_port), STABILITY_PYTHON=sys.executable,
           STABILITY_VIDEO_CHECK=str(Path(__file__).with_name('verify_video.py')))
command = [args.flutter, 'test', '--no-pub', 'tool/capture_stability_board_test.dart',
           '--reporter', 'expanded']
print(json.dumps(dict(command=command, target=dict(serial=args.serial,
                 device=args.device, address=args.address), rounds=args.rounds,
                 soak_minutes=args.soak_minutes, data_root=str(root),
                 dry_run=args.dry_run), ensure_ascii=False))
if not args.dry_run:
    raise SystemExit(subprocess.run(command, cwd=args.flutter_root, env=env).returncode)
