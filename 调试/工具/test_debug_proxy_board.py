"""Run the real-board Flutter regression through the Python debug bridge."""
import http.server
import json
import logging
import logging.handlers
import os
from pathlib import Path
import subprocess
import threading

import instrument_debug_proxy as proxy

flutter_root = Path(__file__).resolve().parents[3] / 'ScoliosisFlutter'
evidence = Path(__file__).resolve().parents[1] / '记录/capture-upgrade-20261001-152212'
log_file = evidence / 'proxy-real-board.jsonl'
proxy.LOG.setLevel(logging.INFO)
proxy.LOG.addHandler(logging.handlers.RotatingFileHandler(
    log_file, maxBytes=4 * 1024 * 1024, backupCount=2, encoding='utf-8'))
proxy.Bridge.upstream = ('127.0.0.1', 8081)
server = http.server.ThreadingHTTPServer(('0.0.0.0', 18081), proxy.Bridge)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
before = set((flutter_root / 'build').glob('capture-v3-board-*'))
try:
    result = subprocess.run([
        r'D:\SoftWare\Flutter\flutter_windows_3.41.9-stable\flutter\bin\flutter.bat',
        'test', 'tool/capture_upgrade_board_test.dart', '--reporter', 'expanded'],
        cwd=flutter_root,
        env={**os.environ, 'UPGRADE_ROUNDS': '1',
             'INSTRUMENT_DEBUG_PROXY': 'http://127.0.0.1:18081'})
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    after = set((flutter_root / 'build').glob('capture-v3-board-*')) - before
    for root in after:
        proxy.restore_direct(root, 8081)
rows = [json.loads(line) for line in log_file.read_text(encoding='utf-8').splitlines()]
restored = any(row['direction'] == 'restore_direct' and row.get('ok') for row in rows)
videos = [row for row in rows if row['direction'] == 'board_http_to_pc' and row['path'] == '/api/v1/capture/file']
assert result.returncode == 0 and restored and videos
print(json.dumps(dict(passed=True, direct_restored=restored, video_posts=len(videos),
                      log=str(log_file), data_roots=[str(p) for p in after])))
